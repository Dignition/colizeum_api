# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from sqlalchemy import func
from sqlalchemy.ext.hybrid import hybrid_property

from ..extensions import db


D = lambda v: Decimal(str(v)) if v is not None else Decimal("0")


class CashierReport(db.Model):
    __tablename__ = "cashier_report"

    id = db.Column(db.Integer, primary_key=True)

    club_id = db.Column(db.Integer, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)

    shift_date = db.Column(db.Date, nullable=False, index=True)
    shift_type = db.Column(db.String(16), nullable=False, default="day")  # day|night (день|ночь)

    # продажи
    bar = db.Column(db.Numeric(12, 2), default=0)
    cash = db.Column(db.Numeric(12, 2), default=0)
    extended = db.Column(db.Numeric(12, 2), default=0)

    # разбивка «расширенной оплаты»
    sbp_acq = db.Column(db.Numeric(12, 2), default=0)  # СБП эквайринг
    sbp_cls = db.Column(db.Numeric(12, 2), default=0)  # CLS
    acquiring = db.Column(db.Numeric(12, 2), default=0)  # Эквайринг!

    # ИТОГО РАСХОДОВ за смену (хранится тут)
    acquiring_fee = db.Column(db.Numeric(12, 2), default=0)

    # возвраты
    refund_cash = db.Column(db.Numeric(12, 2), default=0)
    refund_noncash = db.Column(db.Numeric(12, 2), default=0)

    # инкассация
    encashment = db.Column(db.Numeric(12, 2), default=0)

    # детали расходов
    expenses_json = db.Column(db.Text)

    # прочее
    note = db.Column(db.Text)
    status = db.Column(db.String(24), default="draft")
    created_at = db.Column(db.DateTime, server_default=func.now())

    # связи (если в проекте есть модель user)
    user = db.relationship("User", backref="cashier_reports", lazy="joined", foreign_keys=[user_id])

    # --- вычисляемые поля ---

    @hybrid_property
    def z_report(self) -> Decimal:
        """Z‑отчёт = Наличные + Расширенная оплата"""
        return D(self.cash) + D(self.extended)

    @z_report.expression
    def z_report(cls):
        return func.coalesce(cls.cash, 0) + func.coalesce(cls.extended, 0)

    @hybrid_property
    def game_ps(self) -> Decimal:
        """Игровой PS = Z‑отчёт − Бар (по требованию)"""
        return D(self.cash) + D(self.extended) - D(self.bar)

    @game_ps.expression
    def game_ps(cls):
        return (func.coalesce(cls.cash, 0) + func.coalesce(cls.extended, 0) - func.coalesce(cls.bar, 0))

    @property
    def expenses_total(self) -> Decimal:
        """Сумма расходов (хранится в acquiring_fee)."""
        return D(self.acquiring_fee)

    @property
    def equal_ok(self) -> bool:
        """Расширенная оплата должна равняться сумме СБП + CLS + Эквайринг!"""
        diff = D(self.extended) - (D(self.sbp_acq) + D(self.sbp_cls) + D(self.acquiring))
        return abs(diff) < Decimal("0.01")

