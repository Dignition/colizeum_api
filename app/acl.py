# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict, Any, Set
from flask import session
from sqlalchemy import text
from .extensions import db

# — создание таблицы членств при первом обращении —
def _ensure_user_club_table() -> None:
    cols = {r[1] for r in db.session.execute(text('PRAGMA table_info("user_club")')).all()}
    if cols:
        return
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS "user_club"(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          club_id INTEGER NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('owner','club_admin','staff')),
          UNIQUE(user_id, club_id)
        );
    """))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_user_club_user ON "user_club"(user_id);'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_user_club_club ON "user_club"(club_id);'))
    db.session.commit()

# — выборки клубов —
def _all_active_clubs() -> List[Dict[str, Any]]:
    sql = 'SELECT id, name FROM "club" WHERE is_active=1 ORDER BY name'
    return list(db.session.execute(text(sql)).mappings().all())

def _user_memberships(user_id: int) -> List[Dict[str, Any]]:
    _ensure_user_club_table()
    sql = """
      SELECT c.id AS id, c.name AS name, uc.role AS role
      FROM "user_club" uc
      JOIN "club" c ON c.id = uc.club_id
      WHERE uc.user_id = :uid AND c.is_active=1
      ORDER BY c.name
    """
    return list(db.session.execute(text(sql), {"uid": user_id}).mappings().all())

def clubs_for_toolbar(user) -> List[Dict[str, Any]]:
    if getattr(user, "role", "") == "superadmin":
        return _all_active_clubs()
    return _user_memberships(getattr(user, "id", 0))

def allowed_club_ids(user) -> Set[int]:
    if getattr(user, "role", "") == "superadmin":
        return {row["id"] for row in _all_active_clubs()}
    return {row["id"] for row in _user_memberships(getattr(user, "id", 0))}

# — активный клуб в сессии —
_SESSION_KEY = "club_id"

def get_active_club_id(user) -> int | None:
    ids = list(allowed_club_ids(user))
    if not ids:
        return None
    try:
        cur = int(session.get(_SESSION_KEY) or 0)
    except Exception:
        cur = 0
    if cur in ids:
        return cur
    cur = sorted(ids)[0]
    session[_SESSION_KEY] = cur
    return cur

def set_active_club_id(user, club_id: int) -> None:
    ids = allowed_club_ids(user)
    if club_id in ids:
        session[_SESSION_KEY] = int(club_id)

# — право редактировать отчёт —
def can_edit_report(user, report_club_id: int) -> bool:
    if getattr(user, "role", "") == "superadmin":
        return True
    if report_club_id not in allowed_club_ids(user):
        return False
    row = db.session.execute(
        text('SELECT role FROM "user_club" WHERE user_id=:u AND club_id=:c'),
        {"u": getattr(user, "id", 0), "c": report_club_id},
    ).first()
    return bool(row and row[0] in ("owner", "club_admin"))
