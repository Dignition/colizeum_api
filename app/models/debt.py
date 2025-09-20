
from datetime import date
from ..extensions import db

class AdminDebt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    reason = db.Column(db.String(255), default="")
    created_on = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(16), default="open")  # open|settled|written_off


class DebtTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    qty = db.Column(db.Integer, nullable=False, default=1)
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    kind = db.Column(db.String(16), default="normal")  # normal|defect (reserved)
    reason = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
