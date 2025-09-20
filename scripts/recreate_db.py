# -*- coding: utf-8 -*-
"""
Полный ресет SQLite-БД и базовое наполнение с подробными логами.

Запуск из корня проекта:
  python scripts/recreate_db.py
"""

from __future__ import annotations
import sys, traceback
from pathlib import Path
from typing import Optional
from sqlalchemy import text

# --- путь к проекту ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print(f"[recreate] ROOT={ROOT}")
if not (ROOT / "app").exists():
    raise SystemExit("[recreate] ошибка: папка app не найдена рядом со scripts/")
if not (ROOT / "app" / "__init__.py").exists():
    raise SystemExit("[recreate] ошибка: app/__init__.py отсутствует")

# --- импорт приложения/ORM ---
print("[recreate] импорт приложения…")
from app import create_app  # type: ignore
from app.extensions import db  # type: ignore

# модели
print("[recreate] импорт моделей…")
from app.models.user import User  # type: ignore
from app.models.club import Club  # type: ignore

# ACL утилиты
from app.acl import _ensure_user_club_table  # type: ignore


def _db_path_from_uri(uri: str) -> Optional[Path]:
    if uri.startswith("sqlite:///"):
        return Path(uri.replace("sqlite:///", "")).resolve()
    return None


def _set_password(u: User, plain: str) -> None:
    try:
        u.set_password(plain)  # type: ignore[attr-defined]
        return
    except Exception:
        pass
    from werkzeug.security import generate_password_hash
    if hasattr(u, "password_hash"):
        setattr(u, "password_hash", generate_password_hash(plain))
    elif hasattr(u, "password"):
        setattr(u, "password", generate_password_hash(plain))
    else:
        raise RuntimeError("У модели User нет ни set_password, ни password_hash/password")


def _cnt(table: str) -> int:
    try:
        return int(db.session.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
    except Exception:
        return -1


def main() -> int:
    print("[recreate] create_app()…")
    app = create_app()
    with app.app_context():
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        print(f"[recreate] SQLALCHEMY_DATABASE_URI = {uri}")

        db_path = _db_path_from_uri(uri)
        if db_path:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            if db_path.exists():
                print(f"[recreate] удаляю файл БД: {db_path}")
                db_path.unlink()
            else:
                print(f"[recreate] файл БД ещё не существует: {db_path}")
        else:
            print("[recreate] БД не sqlite, пропускаю удаление файла")

        print("[recreate] создаю таблицы по моделям…")
        db.create_all()
        print("[recreate] готово")

        print("[recreate] гарантирую наличие ACL-таблицы user_club…")
        _ensure_user_club_table()
        print(f"[recreate] user_club OK (rows={_cnt('user_club')})")

        # --- базовые клубы ---
        print("[recreate] добавляю клубы…")
        moscow = Club(name="COLIZEUM Moscow", timezone="Europe/Moscow", is_active=True)  # type: ignore[arg-type]
        vienna = Club(name="COLIZEUM Vienna", timezone="Europe/Vienna", is_active=True)  # type: ignore[arg-type]
        db.session.add_all([moscow, vienna])
        db.session.commit()
        print(f"[recreate] club rows={_cnt('club')}  -> Moscow id={moscow.id}, Vienna id={vienna.id}")

        # --- пользователи ---
        print("[recreate] создаю пользователей…")
        superadmin = User(username="superadmin", role="superadmin")  # type: ignore[call-arg]
        _set_password(superadmin, "admin")
        owner = User(username="owner", role="owner")
        _set_password(owner, "owner")
        club_admin = User(username="admin1", role="user")
        _set_password(club_admin, "admin1")

        db.session.add_all([superadmin, owner, club_admin])
        db.session.commit()
        print(
            f"[recreate] user rows={_cnt('user')}  -> "
            f"superadmin id={superadmin.id}, owner id={owner.id}, admin1 id={club_admin.id}"
        )

        # --- членства ---
        print("[recreate] назначаю членства и роли внутри клубов…")
        db.session.execute(
            text('INSERT OR IGNORE INTO "user_club"(user_id, club_id, role) VALUES (:u,:c,:r)'),
            [
                {"u": owner.id, "c": moscow.id, "r": "owner"},
                {"u": owner.id, "c": vienna.id, "r": "owner"},
                {"u": club_admin.id, "c": moscow.id, "r": "club_admin"},
            ],
        )
        db.session.commit()
        print(f"[recreate] user_club rows={_cnt('user_club')}")

        print("\n[recreate] Готово.")
        print("Логины:")
        print("  superadmin / admin")
        print("  owner      / owner")
        print("  admin1     / admin1")
        if db_path:
            print(f"\nФайл БД: {db_path}")
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\n[recreate] ОШИБКА:")
        traceback.print_exc()
        sys.exit(1)
