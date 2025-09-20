"""
Актуализация схемы БД (без удаления данных).

Создаёт недостающие таблицы, объявленные в моделях, не трогая существующие
данные. Полезно, чтобы привести файл instance/colizeum.db в порядок перед
импортом товаров/штрих‑кодов.

Запуск:
  python scripts/ensure_schema.py
"""

from __future__ import annotations

import sys
from typing import Iterable
from sqlalchemy import text

from pathlib import Path

print("[ensure] Загружаю приложение...")
from pathlib import Path
import sys

# Гарантируем, что корень проекта есть в sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # type: ignore
from app.extensions import db  # type: ignore


def _tables(conn) -> set[str]:
    rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    return {r[0] for r in rows}


def main() -> int:
    app = create_app()
    with app.app_context():
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        print(f"[ensure] SQLALCHEMY_DATABASE_URI = {uri}")

        # Что есть «до»
        before = _tables(db.session)
        print(f"[ensure] Таблиц до: {len(before)}")

        # Импортируем пакет моделей, чтобы они зарегистрировались в метаданных
        print("[ensure] Импорт моделей...")
        from app import models  # noqa: F401

        # Создаём только недостающие таблицы
        print("[ensure] Создание недостающих таблиц (если есть)...")
        db.create_all()

        after = _tables(db.session)
        created = sorted(list(after - before))
        if created:
            print(f"[ensure] Созданы таблицы: {', '.join(created)}")
        else:
            print("[ensure] Новых таблиц не потребовалось.")

        # Подсказки
        interesting = [
            "product",
            "product_barcode",
            "stock",
            "stock_move",
            "inventory_session",
            "inventory_count",
        ]
        present = [t for t in interesting if t in after]
        if present:
            print(f"[ensure] Таблицы учёта есть: {', '.join(present)}")
        print("[ensure] Готово.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
