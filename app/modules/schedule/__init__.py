# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime, timedelta
from collections import defaultdict

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text

from ...extensions import db
from ...models import User
from ...models.schedule import Shift
from ...models.report import CashierReport
from ...acl import get_active_club_id, allowed_club_ids

bp = Blueprint(
    "schedule",
    __name__,
    url_prefix="/schedule",
    template_folder="../../templates/schedule",
)

def _month_bounds(m: str | None):
    today = date.today()
    if m:
        try:
            y, mm = map(int, m.split("-"))
        except Exception:
            y, mm = today.year, today.month
    else:
        y, mm = today.year, today.month
    start = date(y, mm, 1)
    end = date(y + (1 if mm == 12 else 0), 1 if mm == 12 else mm + 1, 1)
    return start, end, f"{y:04d}-{mm:02d}"

def _display_name(u: User) -> str:
    fio = f"{getattr(u, 'last_name', '')} {getattr(u, 'first_name', '')}".strip()
    for v in (
        fio,
        getattr(u, "full_name", None),
        getattr(u, "name", None),
        getattr(u, "username", None),
        getattr(u, "email", None),
        f"#{getattr(u, 'id', 0)}",
    ):
        if v:
            return v
    return "—"

def _sorted(users):
    return sorted(users, key=lambda x: _display_name(x).lower())

@bp.route("/")
@login_required
def index():
    # активный клуб
    cid = get_active_club_id(current_user)
    if not cid:
        flash("Нет доступного клуба.", "warning")
        return redirect(url_for("home"))

    m = request.args.get("m")
    d1, d2, m_str = _month_bounds(m)
    days = [d1 + timedelta(days=i) for i in range((d2 - d1).days)]

    # отчёты месяца ТОЛЬКО этого клуба
    reports = (
        db.session.query(CashierReport)
        .filter(
            CashierReport.shift_date >= d1,
            CashierReport.shift_date < d2,
            CashierReport.club_id == cid,
        )
        .all()
    )

    # пользователи клуба из user_club + авторы отчётов этого клуба
    member_ids = {
        r[0]
        for r in db.session.execute(
            text('SELECT user_id FROM "user_club" WHERE club_id=:c AND role IN ("owner","club_admin","staff")'),
            {"c": cid},
        ).all()
    }
    report_ids = {r.user_id for r in reports}
    staff_ids = member_ids | report_ids
    if staff_ids:
        staff = _sorted(User.query.filter(User.id.in_(staff_ids)).all())
    else:
        staff = []

    # объединяем день/ночь в сутки по отчётам этого клуба
    kinds = defaultdict(set)  # (user_id, date) -> {'day','night'}
    for r in reports:
        kinds[(r.user_id, r.shift_date)].add(r.shift_type or "")

    prefill: dict[str, dict[str, str | int]] = {}
    for (uid, dt), tset in kinds.items():
        both = int("day" in tset and "night" in tset)
        if both:
            start_t, end_t = "10:00", "10:00"
        elif "day" in tset:
            start_t, end_t = "10:00", "22:00"
        elif "night" in tset:
            start_t, end_t = "22:00", "10:00"
        else:
            continue
        prefill[f"{uid}:{dt.isoformat()}"] = {"start": start_t, "end": end_t, "both": both}

    # Override with saved shifts if present for this month/club
    saved = (
        db.session.query(Shift)
        .filter(
            Shift.club_id == cid,
            Shift.start_ts >= datetime(d1.year, d1.month, 1),
            Shift.start_ts < datetime(d2.year, d2.month, 1),
        )
        .all()
    )
    for s in saved:
        day = s.start_ts.date()
        key = f"{s.user_id}:{day.isoformat()}"
        both = int(s.end_ts.date() != day)
        prefill[key] = {
            "start": s.start_ts.strftime("%H:%M"),
            "end": s.end_ts.strftime("%H:%M"),
            "both": both,
        }

    # editor capabilities for current user
    my_uid = getattr(current_user, "id", 0)
    my_mrole = db.session.execute(
        text('SELECT role FROM "user_club" WHERE user_id=:u AND club_id=:c'),
        {"u": my_uid, "c": cid},
    ).scalar() or ""
    editable_all = (getattr(current_user, "role", "") == "superadmin") or (my_mrole == "owner")
    editable_self_only = (not editable_all) and (my_mrole == "club_admin")

    return render_template(
        "schedule/index.html",
        month_str=m_str,
        days=days,
        staff=staff,
        prefill=prefill,
        active_club_id=cid,
        editable_all=editable_all,
        editable_self_only=editable_self_only,
        my_uid=my_uid,
    )


def _membership_role(user_id: int, club_id: int) -> str | None:
    row = db.session.execute(
        text('SELECT role FROM "user_club" WHERE user_id=:u AND club_id=:c'),
        {"u": int(user_id), "c": int(club_id)},
    ).first()
    return (row[0] if row else None) or None


def _can_edit_row(target_user_id: int, club_id: int) -> bool:
    # superadmin: full access
    if getattr(current_user, "role", "") == "superadmin":
        return True
    # must belong to this club at least somehow
    if club_id not in allowed_club_ids(current_user):
        return False
    # owner of club may edit anyone in their club
    mrole = _membership_role(getattr(current_user, "id", 0), club_id)
    if mrole == "owner":
        return True
    # club_admin may edit only their own row
    if mrole == "club_admin":
        return int(getattr(current_user, "id", 0)) == int(target_user_id)
    # others (staff/cashier) cannot edit anyone
    return False


@bp.post("/save-one")
@login_required
def save_one():
    cid = get_active_club_id(current_user)
    if not cid:
        return jsonify({"ok": False, "error": "no_active_club"}), 400

    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    try:
        uid = int(payload.get("user_id") or 0)
    except Exception:
        uid = 0
    date_str = (payload.get("date") or "").strip()
    start = (payload.get("start") or "").strip()
    end = (payload.get("end") or "").strip()
    both = int(payload.get("both") or 0)

    if not uid or not date_str:
        return jsonify({"ok": False, "error": "bad_request"}), 400
    if not _can_edit_row(uid, cid):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    # ensure table exists
    try:
        db.session.execute(text('SELECT 1 FROM "shift" LIMIT 1'))
    except Exception:
        db.create_all()

    # delete any previous record for this day
    del_res = db.session.execute(
        text('DELETE FROM "shift" WHERE club_id=:c AND user_id=:u AND date(start_ts)=:d'),
        {"c": cid, "u": uid, "d": date_str},
    )

    # insert if provided
    if start and end and start.upper() not in ("B", "В", "OFF") and end.upper() not in ("B", "В", "OFF"):
        try:
            y, m, d = map(int, date_str.split("-"))
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
        except Exception:
            return jsonify({"ok": False, "error": "bad_time"}), 400
        start_ts = datetime(y, m, d, sh, sm)
        if both and (eh*60+em) >= (sh*60+sm):
            end_ts = datetime(y, m, d, eh, em) + timedelta(days=1)
        else:
            end_ts = datetime(y, m, d, eh, em)
            if (eh*60+em) <= (sh*60+sm):
                end_ts = end_ts + timedelta(days=1)
        db.session.execute(
            text('INSERT INTO "shift"(club_id,user_id,start_ts,end_ts) VALUES (:c,:u,:s,:e)'),
            {"c": cid, "u": uid, "s": start_ts.isoformat(sep=" "), "e": end_ts.isoformat(sep=" ")},
        )
        db.session.commit()
        return jsonify({"ok": True, "action": "upsert"})

    # if reached here, treat deletion as success if something was removed
    db.session.commit()
    if (getattr(del_res, "rowcount", 0) or 0) > 0:
        return jsonify({"ok": True, "action": "delete"})
    return jsonify({"ok": False, "error": "no_change"})


@bp.post("/save")
@login_required
def save():
    cid = get_active_club_id(current_user)
    if not cid:
        return jsonify({"ok": False, "error": "no_active_club"}), 400

    # Request payload
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    m = payload.get("month") or request.args.get("m")
    d1, d2, _ = _month_bounds(m)

    # Ensure table exists (first run)
    try:
        db.session.execute(text('SELECT 1 FROM "shift" LIMIT 1'))
    except Exception:
        db.create_all()

    # Delete existing for month+club (simple upsert strategy)
    db.session.execute(
        text('DELETE FROM "shift" WHERE club_id=:c AND date(start_ts)>=:d1 AND date(start_ts)<:d2'),
        {"c": cid, "d1": d1.isoformat(), "d2": d2.isoformat()},
    )

    rows = payload.get("rows") or []
    ins: list[dict] = []
    for r in rows:
        try:
            uid = int(r.get("user_id") or 0)
        except Exception:
            uid = 0
        days_map = r.get("days") or {}
        if not uid or not isinstance(days_map, dict):
            continue
        for d_str, rec in days_map.items():
            try:
                y, mm, dd = map(int, d_str.split("-"))
                day = date(y, mm, dd)
            except Exception:
                continue
            start = (rec.get("start") or "").strip()
            end = (rec.get("end") or "").strip()
            both = int(rec.get("both") or 0)
            if not start or not end or start.upper() in ("B","В","OFF") or end.upper() in ("B","В","OFF"):
                continue
            try:
                sh, sm = map(int, start.split(":"))
                eh, em = map(int, end.split(":"))
            except Exception:
                continue
            start_ts = datetime(day.year, day.month, day.day, sh, sm)
            # End timestamp
            if both and (eh*60+em) >= (sh*60+sm):
                end_ts = datetime(day.year, day.month, day.day, eh, em) + timedelta(days=1)
            else:
                end_ts = datetime(day.year, day.month, day.day, eh, em)
                if (eh*60+em) <= (sh*60+sm):
                    end_ts = end_ts + timedelta(days=1)
            ins.append({
                "club_id": cid,
                "user_id": uid,
                "start_ts": start_ts.isoformat(sep=" "),
                "end_ts": end_ts.isoformat(sep=" "),
            })

    if ins:
        db.session.execute(
            text('INSERT INTO "shift"(club_id,user_id,start_ts,end_ts) VALUES (:club_id,:user_id,:start_ts,:end_ts)'),
            ins,
        )
    db.session.commit()
    return jsonify({"ok": True, "saved": len(ins)})
