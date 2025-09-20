from datetime import datetime
from ..extensions import db

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    sku = db.Column(db.String(64), unique=True, nullable=True)
    purchase_price = db.Column(db.Numeric(12,2), default=0)
    sell_price = db.Column(db.Numeric(12,2), default=0)
    is_active = db.Column(db.Boolean, default=True)

class ProductBarcode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    barcode = db.Column(db.String(64), nullable=False, index=True, unique=True)

class ClubProductBarcode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    barcode = db.Column(db.String(64), nullable=False, index=True)
    purchase_price = db.Column(db.Numeric(12,2), default=0)
    __table_args__ = (
        db.UniqueConstraint('club_id', 'barcode', name='uq_club_barcode'),
    )

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    qty = db.Column(db.Integer, default=0)

class StockMove(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty_delta = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(64), default="adjust")  # sale|purchase|adjust|transfer
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InventorySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)

class InventoryCount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("inventory_session.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    expected_qty = db.Column(db.Integer, default=0)
    counted_qty = db.Column(db.Integer, default=0)

# Небольшая «самолечащаяся» миграция: добавляет колонку purchase_price
# в таблицу club_product_barcode, если её ещё нет (SQLite).

def ensure_club_barcode_price_column():
    try:
        rows = db.session.execute(db.text('PRAGMA table_info("club_product_barcode")')).mappings().all()
        cols = {r['name'] for r in rows}
        if 'purchase_price' not in cols:
            db.session.execute(db.text('ALTER TABLE "club_product_barcode" ADD COLUMN purchase_price NUMERIC(12,2) DEFAULT 0'))
            db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
