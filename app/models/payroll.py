
from ..extensions import db


class PayrollEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM
    base_salary = db.Column(db.Numeric(12, 2), default=0)
    bonuses = db.Column(db.Numeric(12, 2), default=0)
    fines = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    status = db.Column(db.String(16), default="draft")  # draft|approved|paid


class PayrollHour(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, index=True)
    hours = db.Column(db.Numeric(6, 2), default=0)
    __table_args__ = (db.UniqueConstraint("club_id", "user_id", "day", name="uq_payroll_day"),)
