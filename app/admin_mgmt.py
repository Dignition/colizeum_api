# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from .extensions import db
from .models.user import User
from .models.club import Club
from .acl import _ensure_user_club_table

bp = Blueprint("admin_mgmt", __name__)

# ---------- guard ----------
def _sa_only():
    if getattr(current_user, "role", "") != "superadmin":
        abort(403)

# ---------- helpers ----------
def _user_columns() -> set[str]:
    rows = db.session.execute(text('PRAGMA table_info("user")')).mappings().all()
    return {r["name"] for r in rows}

def _fio_sql_expr_dynamic() -> str:
    cols = _user_columns()
    if "full_name" in cols:
        return "COALESCE(u.full_name,'')"
    if "first_name" in cols or "last_name" in cols:
        fn = "COALESCE(u.first_name,'')" if "first_name" in cols else "''"
        ln = "COALESCE(u.last_name,'')"  if "last_name"  in cols else "''"
        return f"TRIM({fn}||CASE WHEN {ln}='' THEN '' ELSE ' ' END||{ln})"
    if "name" in cols: return "COALESCE(u.name,'')"
    if "fio"  in cols: return "COALESCE(u.fio,'')"
    return "''"

def _set_password(u: User, plain: str) -> None:
    try:
        u.set_password(plain)  # type: ignore[attr-defined]
    except Exception:
        if hasattr(u, "password_hash"):
            u.password_hash = generate_password_hash(plain)  # type: ignore[attr-defined]
        elif hasattr(u, "password"):
            u.password = generate_password_hash(plain)       # type: ignore[attr-defined]
        else:
            raise RuntimeError("User: нет поля пароля")

def _set_fio(u: User, fio: str) -> None:
    fio = (fio or "").strip()
    if not fio: return
    cols = _user_columns()
    if "full_name" in cols and hasattr(u, "full_name"):
        setattr(u, "full_name", fio); return
    if ("first_name" in cols or "last_name" in cols) and (hasattr(u,"first_name") or hasattr(u,"last_name")):
        parts = fio.split()
        first = parts[0]
        last  = " ".join(parts[1:]) if len(parts)>1 else ""
        if "first_name" in cols and hasattr(u,"first_name"): setattr(u,"first_name",first)
        if "last_name"  in cols and hasattr(u,"last_name"):  setattr(u,"last_name",last)

def _find_user_by_login(login: str) -> Optional[dict]:
    row = db.session.execute(
        text('SELECT id, username, COALESCE(role,"user") AS role FROM "user" WHERE username=:u'),
        {"u": (login or "").strip()},
    ).mappings().first()
    return dict(row) if row else None

def _already_member(user_id: int, club_id: int) -> bool:
    sql = 'SELECT 1 FROM "user_club" WHERE user_id=:u AND club_id=:c'
    return db.session.execute(text(sql), {"u": user_id, "c": club_id}).first() is not None

# ---------- timezones ----------
TZ_RU = [
    {"id":"Europe/Moscow","label":"Европа / Москва (UTC+3)"},
    {"id":"Europe/Kaliningrad","label":"Европа / Калининград (UTC+2)"},
    {"id":"Europe/Samara","label":"Европа / Самара (UTC+4)"},
    {"id":"Europe/Volgograd","label":"Европа / Волгоград (UTC+3)"},
    {"id":"Asia/Yekaterinburg","label":"Азия / Екатеринбург (UTC+5)"},
    {"id":"Asia/Omsk","label":"Азия / Омск (UTC+6)"},
    {"id":"Asia/Novosibirsk","label":"Азия / Новосибирск (UTC+7)"},
    {"id":"Asia/Tomsk","label":"Азия / Томск (UTC+7)"},
    {"id":"Asia/Krasnoyarsk","label":"Азия / Красноярск (UTC+7)"},
    {"id":"Asia/Irkutsk","label":"Азия / Иркутск (UTC+8)"},
    {"id":"Asia/Chita","label":"Азия / Чита (UTC+9)"},
    {"id":"Asia/Yakutsk","label":"Азия / Якутск (UTC+9)"},
    {"id":"Asia/Vladivostok","label":"Азия / Владивосток (UTC+10)"},
    {"id":"Asia/Sakhalin","label":"Азия / Сахалин (UTC+11)"},
    {"id":"Asia/Magadan","label":"Азия / Магадан (UTC+11)"},
    {"id":"Asia/Kamchatka","label":"Азия / Камчатка (UTC+12)"},
    {"id":"Europe/Vienna","label":"Европа / Вена (UTC+1)"},
    {"id":"Europe/Berlin","label":"Европа / Берлин (UTC+1)"},
    {"id":"Europe/Paris","label":"Европа / Париж (UTC+1)"},
    {"id":"Europe/Warsaw","label":"Европа / Варшава (UTC+1)"},
    {"id":"Europe/Prague","label":"Европа / Прага (UTC+1)"},
    {"id":"Europe/London","label":"Европа / Лондон (UTC+0)"},
    {"id":"Asia/Almaty","label":"Азия / Алматы (UTC+6)"},
    {"id":"Asia/Tashkent","label":"Азия / Ташкент (UTC+5)"},
    {"id":"Asia/Bishkek","label":"Азия / Бишкек (UTC+6)"},
    {"id":"Asia/Tbilisi","label":"Азия / Тбилиси (UTC+4)"},
    {"id":"Asia/Yerevan","label":"Азия / Ереван (UTC+4)"},
    {"id":"Asia/Baku","label":"Азия / Баку (UTC+4)"},
    {"id":"Asia/Dubai","label":"Азия / Дубай (UTC+4)"},
    {"id":"America/Los_Angeles","label":"Америка / Лос-Анджелес (UTC−8)"},
    {"id":"America/Denver","label":"Америка / Денвер (UTC−7)"},
    {"id":"America/Chicago","label":"Америка / Чикаго (UTC−6)"},
    {"id":"America/New_York","label":"Америка / Нью-Йорк (UTC−5)"},
    {"id":"UTC","label":"UTC (UTC+0)"},
]

# ---------- clubs ----------
@bp.route("/admin/clubs", methods=["GET","POST"])
@login_required
def clubs():
    _sa_only()
    if request.method == "POST":
        op = request.form.get("op")
        if op == "create":
            name = (request.form.get("name") or "").strip()
            if name and not name.upper().startswith("COLIZEUM"):
                name = f"COLIZEUM {name}"
            tz = (request.form.get("timezone") or "Europe/Moscow").strip()
            active = request.form.get("is_active") == "1"
            c = Club(name=name, timezone=tz, is_active=active)  # type: ignore[arg-type]
            db.session.add(c); db.session.commit(); flash("Клуб создан","primary")
        elif op == "update":
            cid = int(request.form.get("id") or 0)
            c = db.session.get(Club, cid)
            if c:
                name = (request.form.get("name") or c.name).strip()
                if name and not name.upper().startswith("COLIZEUM"):
                    name = f"COLIZEUM {name}"
                c.name = name
                c.timezone = (request.form.get("timezone") or c.timezone).strip()  # type: ignore[attr-defined]
                c.is_active = request.form.get("is_active") == "1"                 # type: ignore[attr-defined]
                db.session.commit(); flash("Клуб обновлён","primary")
        elif op == "delete":
            cid = int(request.form.get("id") or 0)
            has_reports = db.session.execute(
                text('SELECT 1 FROM "cashier_report" WHERE club_id=:c LIMIT 1'),{"c":cid}
            ).first()
            if has_reports:
                flash("Есть данные. Снимите активность вместо удаления.","warning")
            else:
                db.session.execute(text('DELETE FROM "user_club" WHERE club_id=:c'), {"c": cid})
                c = db.session.get(Club, cid)
                if c: db.session.delete(c)
                db.session.commit(); flash("Клуб удалён","primary")
        return redirect(url_for("admin_mgmt.clubs"))

    clubs = db.session.execute(
        text('SELECT id,name,timezone,COALESCE(is_active,1) AS is_active FROM "club" ORDER BY name')
    ).mappings().all()
    return render_template("admin/clubs.html", clubs=clubs, tz_opts=TZ_RU)

# ---------- users ----------
@bp.route("/admin/users", methods=["GET","POST"])
@login_required
def users():
    _sa_only()
    _ensure_user_club_table()
    if request.method == "POST":
        op = request.form.get("op")

        if op == "create":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            fio      = (request.form.get("fio") or "").strip()
            club_id  = request.form.get("club_id")
            club_role= (request.form.get("club_role") or "club_admin").strip()
            if not username or not password or not club_id:
                flash("Логин, пароль и клуб обязательны","warning")
                return redirect(url_for("admin_mgmt.users"))
            u = User(username=username, role="user")  # type: ignore[call-arg]
            _set_password(u, password); _set_fio(u, fio)
            db.session.add(u); db.session.commit()
            db.session.execute(
                text('INSERT OR IGNORE INTO "user_club"(user_id,club_id,role) VALUES (:u,:c,:r)'),
                {"u":u.id,"c":int(club_id),"r":club_role}
            )
            db.session.commit(); flash("Пользователь создан","primary")
            return redirect(url_for("admin_mgmt.users"))

        if op == "create_superadmin":
            username = (request.form.get("sa_username") or "").strip()
            password = request.form.get("sa_password") or ""
            fio      = (request.form.get("sa_fio") or "").strip()
            if not username or not password:
                flash("Логин и пароль обязательны","warning")
                return redirect(url_for("admin_mgmt.users"))
            u = User(username=username, role="superadmin")  # type: ignore[call-arg]
            _set_password(u, password); _set_fio(u, fio)
            db.session.add(u); db.session.commit()
            flash("Superadmin создан","primary")
            return redirect(url_for("admin_mgmt.users"))

        if op == "update_user":
            uid = int(request.form.get("user_id") or 0)
            u = db.session.get(User, uid)
            if not u:
                flash("Пользователь не найден","warning")
                return redirect(url_for("admin_mgmt.users"))
            new_username = (request.form.get("username") or "").strip()
            new_fio      = (request.form.get("fio") or "").strip()
            new_pass     = request.form.get("new_password") or ""
            if new_username: setattr(u,"username",new_username)
            _set_fio(u, new_fio)
            if new_pass: _set_password(u, new_pass)
            db.session.commit(); flash("Пользователь обновлён","primary")
            return redirect(url_for("admin_mgmt.users"))

        if op == "delete_user":
            uid = int(request.form.get("user_id") or 0)
            rep_cnt = db.session.execute(
                text('SELECT COUNT(1) FROM "cashier_report" WHERE user_id=:u'), {"u":uid}
            ).scalar() or 0
            if rep_cnt:
                flash("Нельзя удалить: есть отчёты кассира.","warning")
                return redirect(url_for("admin_mgmt.users"))
            db.session.execute(text('DELETE FROM "user_club" WHERE user_id=:u'), {"u": uid})
            u = db.session.get(User, uid)
            if not u:
                flash("Пользователь не найден","warning")
            else:
                db.session.delete(u)
            db.session.commit()
            flash("Пользователь удалён","primary")
            return redirect(url_for("admin_mgmt.users"))

        return redirect(url_for("admin_mgmt.users"))

    fio_expr = _fio_sql_expr_dynamic()
    users = db.session.execute(
        text(f'SELECT u.id, u.username, COALESCE(u.role,"user") AS role, {fio_expr} AS fio FROM "user" u ORDER BY u.id')
    ).mappings().all()

    memberships = db.session.execute(text("""
        SELECT m.user_id, c.name AS club_name, m.role
        FROM "user_club" m
        LEFT JOIN "club" c ON c.id = m.club_id
        ORDER BY m.user_id, c.name
    """)).mappings().all()
    per_user: dict[int, list[dict]] = {}
    for r in memberships:
        club_name = r["club_name"] or "удалённый клуб"
        per_user.setdefault(r["user_id"], []).append({"club": club_name, "role": r["role"]})

    clubs = db.session.execute(
        text('SELECT id,name FROM "club" WHERE COALESCE(is_active,1)=1 ORDER BY name')
    ).mappings().all()
    return render_template("admin/users.html", users=users, clubs=clubs, per_user=per_user)

# ---------- memberships ----------
@bp.route("/admin/memberships", methods=["GET","POST"])
@login_required
def memberships():
    _sa_only()
    _ensure_user_club_table()

    if request.method == "POST":
        op = request.form.get("op")
        try:
            cid = int(request.form.get("club_id") or 0)
        except Exception:
            cid = 0

        if op == "del_member":
            mid = int(request.form.get("id") or 0)
            db.session.execute(text('DELETE FROM "user_club" WHERE id=:id'), {"id": mid})
            db.session.commit(); flash("Доступ удалён","primary")
            return redirect(url_for("admin_mgmt.memberships"))

        if op in ("add_owner", "add_admin"):
            role = "owner" if op == "add_owner" else "club_admin"

            uid = request.form.get("user_id")
            login = (request.form.get("owner_login") or request.form.get("admin_login")
                     or request.form.get("login") or "").strip()

            user = None
            if uid:
                try:
                    user = db.session.execute(
                        text('SELECT id, username, COALESCE(role,"user") AS role FROM "user" WHERE id=:id'),
                        {"id": int(uid)}
                    ).mappings().first()
                except Exception:
                    user = None
            if not user and login:
                user = _find_user_by_login(login)

            if not cid or not user:
                flash("Укажите клуб и пользователя (id или логин).","warning")
                return redirect(url_for("admin_mgmt.memberships"))

            if user["role"] == "superadmin":
                flash("Superadmin не привязывается к клубам","warning")
                return redirect(url_for("admin_mgmt.memberships"))

            if _already_member(user["id"], cid):
                flash("У пользователя уже есть доступ к этому клубу","info")
                return redirect(url_for("admin_mgmt.memberships"))

            # запрет смешивать типы ролей по клубам
            existing_roles = set(db.session.execute(
                text('SELECT DISTINCT role FROM "user_club" WHERE user_id=:u'),
                {"u": user["id"]}
            ).scalars().all())
            existing_roles = {r for r in existing_roles if r in ("owner", "club_admin")}
            if existing_roles and (existing_roles - {role}):
                human = "Собственник" if role == "owner" else "Админ клуба"
                human_have = "Собственник" if "owner" in existing_roles else "Админ клуба"
                flash(f"Нельзя выдать роль «{human}». Уже есть роль «{human_have}» в других клубах.","warning")
                return redirect(url_for("admin_mgmt.memberships"))

            db.session.execute(
                text('INSERT OR IGNORE INTO "user_club"(user_id,club_id,role) VALUES (:u,:c,:r)'),
                {"u": user["id"], "c": cid, "r": role},
            )
            db.session.commit(); flash("Доступ выдан","primary")
            return redirect(url_for("admin_mgmt.memberships"))

        return redirect(url_for("admin_mgmt.memberships"))

    # GET
    clubs = db.session.execute(
        text('SELECT id,name FROM "club" WHERE COALESCE(is_active,1)=1 ORDER BY name')
    ).mappings().all()
    fio_expr = _fio_sql_expr_dynamic()

    user_flags = db.session.execute(text(f"""
        SELECT u.id,
               COALESCE(u.role,'user') AS sys_role,
               EXISTS(SELECT 1 FROM "user_club" m WHERE m.user_id=u.id AND m.role='owner')      AS has_owner,
               EXISTS(SELECT 1 FROM "user_club" m WHERE m.user_id=u.id AND m.role='club_admin') AS has_admin,
               u.username, {fio_expr} AS fio
        FROM "user" u
        ORDER BY u.username
    """)).mappings().all()

    # текущие членства
    rows = db.session.execute(text(f"""
        SELECT m.id, m.user_id, m.club_id, m.role, u.username, {fio_expr} AS fio
        FROM "user_club" m
        JOIN "user" u ON u.id = m.user_id
        ORDER BY m.club_id, m.role, u.username
    """)).mappings().all()

    by_club: dict[int, dict[str, list[dict]]] = {}
    for r in rows:
        d = by_club.setdefault(r["club_id"], {"owner": [], "club_admin": []})
        if r["role"] in ("owner", "club_admin"):
            d[r["role"]].append(r)

    # кандидаты:
    #  - не superadmin
    #  - для владельцев: пользователи, у которых уже есть роль owner ИЛИ вообще нет ролей
    #  - для админов: пользователи, у которых уже есть роль club_admin ИЛИ вообще нет ролей
    add_choices: dict[int, dict[str, list[dict]]] = {}
    for c in clubs:
        cur = by_club.get(c["id"], {"owner": [], "club_admin": []})
        owners_ids = {x["user_id"] for x in cur.get("owner", [])}
        admins_ids = {x["user_id"] for x in cur.get("club_admin", [])}

        def no_roles(u): return not (u["has_owner"] or u["has_admin"])

        owner_pool = [u for u in user_flags if u["sys_role"] != "superadmin" and (u["has_owner"] or no_roles(u))]
        admin_pool = [u for u in user_flags if u["sys_role"] != "superadmin" and (u["has_admin"] or no_roles(u))]

        add_choices[c["id"]] = {
            "owner": [u for u in owner_pool if u["id"] not in owners_ids],
            "club_admin": [u for u in admin_pool if u["id"] not in admins_ids],
        }

    return render_template("admin/memberships.html",
                           clubs=clubs, by_club=by_club, add_choices=add_choices)
