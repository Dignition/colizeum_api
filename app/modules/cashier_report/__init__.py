# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime, timedelta
from calendar import monthrange
from typing import Any

from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from ...extensions import db
from ...acl import get_active_club_id, allowed_club_ids, can_edit_report
from ...models.report import CashierReport

bp = Blueprint("cashier", __name__, url_prefix="/cashier", template_folder="templates")

MONTHS_RU = [
    "Январь","Февраль","Март","Апрель","Май","Июнь",
    "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"
]


# ------------ helpers ---------------------------------------------------------
def _month_bounds(qs: str | None) -> tuple[date, date, int]:
    today = date.today()
    if qs:
        try:
            y, m = map(int, qs.split("-"))
            first = date(y, m, 1)
        except Exception:
            first = date(today.year, today.month, 1)
    else:
        first = date(today.year, today.month, 1)
    days = monthrange(first.year, first.month)[1]
    last = date(first.year, first.month, days)
    # end — первый день следующего месяца
    end = date(last.year + (1 if last.month == 12 else 0), 1 if last.month == 12 else last.month + 1, 1)
    return first, end, days


def _to_date(x) -> date:
    if isinstance(x, date):
        return x
    y, m, d = map(int, str(x)[:10].split("-"))
    return date(y, m, d)


def _delta(values: dict[str, Any]) -> float:
    """Δ = extended - (sbp_acq + sbp_cls + acquiring)"""
    try:
        ext = float(values.get("extended", 0) or 0)
        ssum = float(values.get("sbp_acq", 0) or 0) + float(values.get("sbp_cls", 0) or 0) + float(values.get("acquiring", 0) or 0)
        return round(ext - ssum, 2)
    except Exception:
        return 0.0


def _load_expenses_list(report_id: int) -> list[dict]:
    row = db.session.execute(text('SELECT expenses_json FROM "cashier_report" WHERE id=:id'), {"id": report_id}).first()
    if not row or not row[0]:
        return []
    import json
    try:
        v = json.loads(row[0])
        return v if isinstance(v, list) else []
    except Exception:
        return []


# ------------ list ------------------------------------------------------------
@bp.route("/", methods=["GET"])
@login_required
def index():
    m = request.args.get("m")
    start, end, days_in_month = _month_bounds(m)

    cid = get_active_club_id(current_user)
    if not cid:
        flash("Нет доступных клубов.", "warning")
        return redirect(url_for("home"))

    # ORM-выборка: отчёты клуба + пользователь (для ФИО в шаблоне)
    reports = (
        CashierReport.query.options(joinedload(CashierReport.user))
        .filter(
            CashierReport.shift_date >= start,
            CashierReport.shift_date < end,
            CashierReport.club_id == cid,
        )
        .order_by(CashierReport.shift_date.asc(), CashierReport.shift_type.asc())
        .all()
    )

    # индекс (date, 'day'|'night') -> ORM-объект отчёта
    bykey: dict[tuple[date, str], CashierReport] = {}
    for r in reports:
        bykey[(_to_date(r.shift_date), r.shift_type)] = r

    # календарь
    days = [start + timedelta(days=i) for i in range(days_in_month)]
    full_days_count = sum(1 for d in days if ((d, "day") in bykey and (d, "night") in bykey))

    # агрегаты по месяцу
    totals = db.session.execute(
        text(
            """
        SELECT
          COALESCE(SUM(bar),0)            AS bar,
          COALESCE(SUM(cash),0)           AS cash,
          COALESCE(SUM(extended),0)       AS extended,
          COALESCE(SUM(sbp_acq),0)        AS sbp_acq,
          COALESCE(SUM(sbp_cls),0)        AS sbp_cls,
          COALESCE(SUM(acquiring),0)      AS acquiring,
          COALESCE(SUM(acquiring_fee),0)  AS acquiring_fee,
          COALESCE(SUM(refund_cash),0)    AS refund_cash,
          COALESCE(SUM(refund_noncash),0) AS refund_noncash,
          COALESCE(SUM(encashment),0)     AS encashment
        FROM "cashier_report"
        WHERE shift_date >= :start AND shift_date < :end AND club_id = :cid
        """
        ),
        {"start": start.isoformat(), "end": end.isoformat(), "cid": cid},
    ).mappings().first()

    return render_template(
        "cashier_report/index.html",
        bykey=bykey,
        days=days,
        full_days_count=full_days_count,
        month_str=start.strftime("%Y-%m"),
        month_date=start.strftime("%Y-%m-%d"),
        month_label=f"{MONTHS_RU[start.month-1]} {start.year}",
        active_club_id=cid,
        tips={},  # безопасный дефолт
        totals=totals,
    )


# ------------ create ----------------------------------------------------------
@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    cid = get_active_club_id(current_user)
    if not cid:
        abort(403)

    if request.method == "GET":
        # префил из query: d/t
        d = request.args.get("d") or request.args.get("date") or request.args.get("shift_date")
        t = request.args.get("t") or request.args.get("shift") or request.args.get("type")
        preset = {}
        if d:
            preset["shift_date"] = d
        if t in ("day", "night"):
            preset["shift_type"] = t
        return render_template("cashier_report/form.html", item=None, active_club_id=cid, preset=preset)

    f = request.form
    shift_date = f.get("shift_date")
    shift_type = f.get("shift_type")

    # защита от дубля в пределах клуба
    exists = db.session.execute(
        text('SELECT id FROM "cashier_report" WHERE club_id=:c AND shift_date=:d AND shift_type=:t'),
        {"c": cid, "d": shift_date, "t": shift_type},
    ).first()
    if exists:
        flash("Отчёт уже существует. Открываю для редактирования.", "info")
        return redirect(url_for("cashier.edit", report_id=int(exists[0])))

    fields: dict[str, Any] = {
        "club_id": cid,
        "user_id": current_user.id,
        "shift_date": shift_date,
        "shift_type": shift_type,
        "bar": f.get("bar") or 0,
        "cash": f.get("cash") or 0,
        "extended": f.get("extended") or 0,
        "sbp_acq": f.get("sbp_acq") or 0,
        "sbp_cls": f.get("sbp_cls") or 0,
        "acquiring": f.get("acquiring") or 0,
        "acquiring_fee": f.get("acquiring_fee") or 0,
        "refund_cash": f.get("refund_cash") or 0,
        "refund_noncash": f.get("refund_noncash") or 0,
        "encashment": f.get("encashment") or 0,
        "expenses_json": f.get("expenses_json") or "[]",
        "note": f.get("note") or "",
        "status": "ok",
        "created_at": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
    }

    # мягкая проверка Δ — не блокируем сохранение
    dlt = _delta(fields)
    if abs(dlt) > 0.01:
        fields["status"] = "warn"
        reason = (f.get("mismatch_reason") or "").strip()
        extra = f"\n[Δ={dlt:+}]"
        if reason:
            extra += f" причина: {reason}"
        fields["note"] = (fields["note"] + extra).strip()

    cols = ", ".join(fields.keys())
    params = ", ".join([f":{k}" for k in fields.keys()])
    new_id = db.session.execute(text(f'INSERT INTO "cashier_report" ({cols}) VALUES ({params}) RETURNING id'), fields).first()[0]
    db.session.commit()
    return redirect(url_for("cashier.view", report_id=int(new_id)))


# ------------ view ------------------------------------------------------------
@bp.route("/<int:report_id>", methods=["GET"])
@login_required
def view(report_id: int):
    r = (
        CashierReport.query.options(joinedload(CashierReport.user))
        .filter(CashierReport.id == report_id)
        .first()
    )
    if not r:
        abort(404)
    if r.club_id not in allowed_club_ids(current_user):
        abort(403)
    return render_template("cashier_report/view.html", r=r, item=r, expenses_list=_load_expenses_list(report_id))


# ------------ edit ------------------------------------------------------------
@bp.route("/<int:report_id>/edit", methods=["GET", "POST"])
@login_required
def edit(report_id: int):
    r = (
        CashierReport.query.options(joinedload(CashierReport.user))
        .filter(CashierReport.id == report_id)
        .first()
    )
    if not r:
        abort(404)
    if not can_edit_report(current_user, int(r.club_id)):
        abort(403)

    if request.method == "GET":
        return render_template("cashier_report/form.html", item=r, active_club_id=r.club_id)

    f = request.form
    upd = {
        "bar": f.get("bar") or 0,
        "cash": f.get("cash") or 0,
        "extended": f.get("extended") or 0,
        "sbp_acq": f.get("sbp_acq") or 0,
        "sbp_cls": f.get("sbp_cls") or 0,
        "acquiring": f.get("acquiring") or 0,
        "acquiring_fee": f.get("acquiring_fee") or 0,
        "refund_cash": f.get("refund_cash") or 0,
        "refund_noncash": f.get("refund_noncash") or 0,
        "encashment": f.get("encashment") or 0,
        "expenses_json": f.get("expenses_json") or "[]",
        "note": f.get("note") or "",
        "status": "ok",
    }

    # мягкая проверка Δ — не блокируем сохранение
    dlt = _delta(upd)
    if abs(dlt) > 0.01:
        upd["status"] = "warn"
        reason = (f.get("mismatch_reason") or "").strip()
        extra = f"\n[Δ={dlt:+}]"
        if reason:
            extra += f" причина: {reason}"
        upd["note"] = (upd["note"] + extra).strip()

    # апдейт
    sets = ", ".join([f'{k}=:{k}' for k in upd.keys()])
    upd["id"] = report_id
    db.session.execute(text(f'UPDATE "cashier_report" SET {sets} WHERE id=:id'), upd)
    db.session.commit()
    return redirect(url_for("cashier.view", report_id=report_id))
