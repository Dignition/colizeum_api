from __future__ import annotations

from flask import Blueprint, redirect, url_for
from flask_login import login_required

# Минимальный модуль долгов: просто перенаправляем на страницу операций
bp = Blueprint(
    "admin_debts",
    __name__,
    url_prefix="/debts",
)


@bp.route("/")
@login_required
def index():
    return redirect(url_for("debtops.index"))
