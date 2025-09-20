
from ..extensions import db

class Club(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    timezone = db.Column(db.String(64), default="Europe/Moscow")
    is_active = db.Column(db.Boolean, default=True)
