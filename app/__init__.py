# -*- coding: utf-8 -*-
import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for
from flask_login import login_required, current_user

from .config import Config, ensure_instance
from .extensions import db, migrate, login_manager

# блюпринты
from .auth import auth_bp
from .modules.cashier_report import bp as cashier_bp
from .modules.schedule import bp as schedule_bp
from .modules.payroll import bp as payroll_bp
from .modules.admin_debts import bp as debts_bp
from .modules.inventory import bp as inventory_bp
from .modules.debt_ops import bp as debtops_bp
from .admin import bp as admin_bp
from .admin_mgmt import bp as admin_mgmt_bp

# ACL
from .acl import clubs_for_toolbar, get_active_club_id, set_active_club_id


def create_app():
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(Config)
    ensure_instance(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # --- jinja-фильтры ---
    @app.template_filter("fmt_date")
    def fmt_date(value, fmt="%d.%m.%Y"):
        if value in (None, ""):
            return ""
        try:
            if isinstance(value, (datetime, date)):
                return value.strftime(fmt)
            s = str(value)
            try:
                return datetime.fromisoformat(s).strftime(fmt)
            except Exception:
                return date.fromisoformat(s[:10]).strftime(fmt)
        except Exception:
            return str(value)

    @app.template_filter("fmt_money")
    def fmt_money(v):
        try:
            x = float(v)
            # без знаков после запятой, с пробелами как разделителями тысяч
            if x.is_integer():
                return f"{int(x):,}".replace(",", " ")
            return f"{x:,.2f}".replace(",", " ")
        except Exception:
            return str(v)

    # alias для совместимости со старыми шаблонами
    @app.template_filter("fmt")
    def fmt(v):
        return fmt_money(v)

    @app.template_filter("dt_ru")
    def dt_ru(value):
        try:
            if value in (None, ""):
                return ""
            if not isinstance(value, (datetime, date)):
                try:
                    value = datetime.fromisoformat(str(value))
                except Exception:
                    return str(value)
            months = [
                "января","февраля","марта","апреля","мая","июня",
                "июля","августа","сентября","октября","ноября","декабря",
            ]
            m = months[(value.month - 1) % 12]
            return f"{value.day} {m} {value.year} {value.strftime('%H:%M')}"
        except Exception:
            return str(value)

    # --- глобальный контекст для селектора клубов ---
    @app.context_processor
    def inject_club_ctx():
        if not current_user.is_authenticated:
            return {}
        return {
            "toolbar_clubs": clubs_for_toolbar(current_user),
            "active_club_id": get_active_club_id(current_user),
        }

    # --- выбор активного клуба ---
    @app.post("/set-club")
    @login_required
    def set_club():
        cid_raw = request.form.get("club_id", "")
        try:
            cid = int(cid_raw)
        except Exception:
            cid = 0
        set_active_club_id(current_user, cid)
        return redirect(request.referrer or url_for("cashier.index"))

    # --- блюпринты ---
    app.register_blueprint(auth_bp)
    app.register_blueprint(cashier_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(debts_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(debtops_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(admin_mgmt_bp)

    # --- главная ---
    @app.route("/")
    @login_required
    def home():
        return render_template("dashboard.html")

    return app
