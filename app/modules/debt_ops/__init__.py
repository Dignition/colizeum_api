# -*- coding: utf-8 -*-
from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text

from ...extensions import db
from ...acl import get_active_club_id, allowed_club_ids, _ensure_user_club_table
from ...models.debt import DebtTransaction
from ...models.user import User
from ...models.inventory import (
    Product,
    ProductBarcode,            # глобальные штрих‑коды (оставляем импорт по требованиям)
    ClubProductBarcode,        # клубные соответствия (используются здесь)
    ensure_club_barcode_price_column,
)


PLACEHOLDER_PREFIX = "__AUTO_EMPTY_BARCODE__"

bp = Blueprint(
    "debtops",
    __name__,
    url_prefix="/debts/ops",
    template_folder="../../templates/admin_debts",
)


def _is_owner_of_club(user: User, club_id: int) -> bool:
    row = db.session.execute(
        text('SELECT 1 FROM "user_club" WHERE user_id=:u AND club_id=:c AND role="owner"'),
        {"u": getattr(user, "id", 0), "c": club_id},
    ).first()
    return bool(row)


def _can_delete_ops(user: User, club_id: int) -> bool:
    if getattr(user, "role", "") == "superadmin":
        return True
    return _is_owner_of_club(user, club_id)


def _users_for_club(cid: int):
    _ensure_user_club_table()
    sql = (
        'SELECT u.id, COALESCE(u.full_name,u.username) AS name '
        'FROM "user_club" m JOIN "user" u ON u.id=m.user_id '
        'WHERE m.club_id=:c AND m.role IN ("owner","club_admin","staff") '
        'ORDER BY COALESCE(u.full_name,u.username)'
    )
    return db.session.execute(text(sql), {"c": cid}).mappings().all()


def _member_ids(cid: int) -> set[int]:
    rows = db.session.execute(text('SELECT user_id FROM "user_club" WHERE club_id=:c'), {"c": cid}).all()
    return {r[0] for r in rows}


@bp.get("/")
@login_required
def index():
    cid = get_active_club_id(current_user)
    if not cid or cid not in allowed_club_ids(current_user):
        abort(403)

    base_q = (
        db.session.query(DebtTransaction, User, Product)
        .join(User, User.id == DebtTransaction.user_id)
        .join(Product, Product.id == DebtTransaction.product_id)
        .filter(DebtTransaction.club_id == cid)
    )

    role = getattr(current_user, "role", "")
    if role not in ("superadmin", "owner"):
        base_q = base_q.filter(DebtTransaction.user_id == getattr(current_user, "id", 0))

    # Разделяем обычные операции и акты списания (дефект)
    rows = (
        base_q.filter(DebtTransaction.kind == "normal")
        .order_by(DebtTransaction.created_at.desc(), DebtTransaction.id.desc())
        .limit(200)
        .all()
    )

    defects = (
        base_q.filter(DebtTransaction.kind == "defect")
        .order_by(DebtTransaction.created_at.desc(), DebtTransaction.id.desc())
        .limit(200)
        .all()
    )

    can_choose_user = getattr(current_user, "role", "") in ("superadmin", "owner")
    sums_sql = (
        'SELECT u.id AS user_id, COALESCE(u.full_name,u.username) AS name, '
        '       ROUND(COALESCE(SUM(dt.price*dt.qty),0),2) AS total '
        'FROM "debt_transaction" dt '
        'JOIN "user" u ON u.id = dt.user_id '
        'WHERE dt.club_id=:c AND COALESCE(dt.kind,\'normal\')=\'normal\' '
        + ('' if can_choose_user else ' AND dt.user_id=:u ')
        + 'GROUP BY u.id, name '
        + 'ORDER BY name'
    )
    sums_params = {"c": cid}
    if not can_choose_user:
        sums_params["u"] = getattr(current_user, "id", 0)
    sums = db.session.execute(text(sums_sql), sums_params).mappings().all()

    members = _users_for_club(cid) if can_choose_user else []

    # Локальные сообщения
    local_msg = None
    local_kind = "primary"
    if (request.args.get("ok") or "") == "1":
        local_msg, local_kind = "Операция выполнена.", "primary"
    elif (request.args.get("del") or "") == "1":
        local_msg, local_kind = "Операция удалена.", "primary"
    elif (request.args.get("reset") or "") == "1":
        local_msg, local_kind = "Операции очищены.", "primary"
    elif (request.args.get("err") or "") == "bad_user":
        local_msg, local_kind = "Некорректный сотрудник.", "warning"
    elif (request.args.get("err") or "") == "no_product":
        local_msg, local_kind = "Товар не найден (скан/ID).", "warning"
    elif (request.args.get("err") or "") == "no_reason":
        local_msg, local_kind = "Укажите причину брака.", "warning"

    return render_template(
        "admin_debts/ops.html",
        items=rows,
        defects=defects,
        sums=sums,
        can_delete=_can_delete_ops(current_user, cid),
        can_choose_user=can_choose_user,
        members=members,
        local_msg=local_msg,
        local_kind=local_kind,
    )


@bp.get("/products")
@login_required
def products():
    """Ссылка-алиас на страницу управления товарами долгов (админка)."""
    return redirect(url_for("admin.debts_products"))


@bp.get("/api/lookup")
@login_required
def ops_lookup():
    cid = get_active_club_id(current_user)
    if not cid or cid not in allowed_club_ids(current_user):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    barcode = (request.args.get("barcode") or "").strip()
    if not barcode:
        return jsonify({"ok": False, "error": "barcode required"}), 400
    ensure_club_barcode_price_column()
    mp = ClubProductBarcode.query.filter_by(club_id=cid, barcode=barcode).first()
    if not mp:
        return jsonify({"ok": True, "found": False})
    p = Product.query.get(mp.product_id)
    cost = float((getattr(mp, 'purchase_price', None) or 0) or (p.purchase_price or 0))
    price = round(cost * 1.10, 2)
    role = getattr(current_user, "role", "")
    payload = {
        "ok": True,
        "found": True,
        "product": {
            "id": p.id,
            "name": p.name,
            "price": price,
        }
    }
    # Для администраторов показываем только цену с наценкой; себестоимость не возвращаем
    if role not in ("superadmin", "owner"):
        payload["product"]["cost_price"] = cost
    return jsonify(payload)


@bp.get("/api/search")
@login_required
def ops_search():
    cid = get_active_club_id(current_user)
    if not cid or cid not in allowed_club_ids(current_user):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    q = (request.args.get("q") or "").strip()
    items = []
    if q:
        like = f"%{q}%"
        try:
            limit = int(request.args.get("limit") or 200)
        except Exception:
            limit = 200
        base_sql = (
            "SELECT p.id, p.name, COALESCE(MAX(cb.purchase_price), COALESCE(p.purchase_price,0)) AS purchase_price, "
            "GROUP_CONCAT(CASE WHEN cb.barcode LIKE :placeholder THEN NULL ELSE cb.barcode END, ', ') AS barcodes "
            "FROM club_product_barcode cb JOIN product p ON p.id = cb.product_id "
            "WHERE cb.club_id = :c AND (p.name LIKE :like OR cb.barcode LIKE :like) "
            "GROUP BY p.id, p.name ORDER BY p.name "
        )
        if limit and limit > 0:
            base_sql += f"LIMIT {int(limit)}"
        sql = text(base_sql)
        items = [dict(row) for row in db.session.execute(sql, {"c": cid, "like": like, "placeholder": f"{PLACEHOLDER_PREFIX}%"}).mappings().all()]
    return jsonify({"ok": True, "items": items})


@bp.post("/assign")
@login_required
def ops_assign():
    cid = get_active_club_id(current_user)
    if not cid or cid not in allowed_club_ids(current_user):
        abort(403)

    role = getattr(current_user, "role", "")
    if role in ("superadmin", "owner"):
        try:
            target_user_id = int(request.form.get("user_id") or 0)
        except Exception:
            target_user_id = 0
        if not target_user_id or target_user_id not in _member_ids(cid):
            return redirect(url_for("debtops.index", err="bad_user"))
    else:
        target_user_id = getattr(current_user, "id", 0)

    ensure_club_barcode_price_column()
    barcode = (request.form.get("barcode") or "").strip()
    product_id = None
    if barcode:
        mp = ClubProductBarcode.query.filter_by(club_id=cid, barcode=barcode).first()
        if mp:
            product_id = mp.product_id
    if not product_id:
        try:
            product_id = int(request.form.get("product_id") or 0)
        except Exception:
            product_id = 0
    p = Product.query.get(product_id) if product_id else None
    if not p:
        return redirect(url_for("debtops.index", err="no_product"))

    try:
        qty = max(int(request.form.get("qty") or 1), 1)
    except Exception:
        qty = 1

    club_map = (locals().get("mp") or None) or ClubProductBarcode.query.filter_by(club_id=cid, product_id=p.id).first()
    cost = float((getattr(club_map, 'purchase_price', None) or 0) or (p.purchase_price or 0))
    reason = (request.form.get("reason") or "").strip()

    rec = DebtTransaction(
        club_id=cid,
        user_id=target_user_id,
        product_id=p.id,
        qty=qty,
        cost_price=cost,
        price=round(cost * 1.10, 2),
        reason=reason,
        kind="normal",
    )
    db.session.add(rec)
    db.session.commit()
    return redirect(url_for("debtops.index", ok=1))


@bp.post("/<int:op_id>/delete")
@login_required
def ops_delete(op_id: int):
    rec = db.session.get(DebtTransaction, op_id)
    if not rec:
        return redirect(url_for("debtops.index"))
    if not _can_delete_ops(current_user, int(rec.club_id)):
        abort(403)
    db.session.delete(rec)
    db.session.commit()
    return redirect(url_for("debtops.index", **{"del": 1}))


@bp.post("/reset")
@login_required
def ops_reset():
    cid = get_active_club_id(current_user)
    if not cid or not _can_delete_ops(current_user, cid):
        abort(403)
    db.session.execute(text('DELETE FROM "debt_transaction" WHERE club_id=:c'), {"c": cid})
    db.session.commit()
    return redirect(url_for("debtops.index", reset=1))


@bp.post("/defect")
@login_required
def ops_defect():
    """Списание по браку (без начисления цены сотруднику)."""
    cid = get_active_club_id(current_user)
    if not cid or cid not in allowed_club_ids(current_user):
        abort(403)

    role = getattr(current_user, "role", "")
    if role in ("superadmin", "owner"):
        try:
            target_user_id = int(request.form.get("user_id") or 0)
        except Exception:
            target_user_id = 0
        if not target_user_id or target_user_id not in _member_ids(cid):
            return redirect(url_for("debtops.index", err="bad_user"))
    else:
        target_user_id = getattr(current_user, "id", 0)

    ensure_club_barcode_price_column()
    barcode = (request.form.get("barcode") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        return redirect(url_for("debtops.index", err="no_reason"))

    product_id = None
    mp = None
    if barcode:
        mp = ClubProductBarcode.query.filter_by(club_id=cid, barcode=barcode).first()
        if mp:
            product_id = mp.product_id
    if not product_id:
        try:
            product_id = int(request.form.get("product_id") or 0)
        except Exception:
            product_id = 0
    p = Product.query.get(product_id) if product_id else None
    if not p:
        return redirect(url_for("debtops.index", err="no_product"))

    try:
        qty = max(int(request.form.get("qty") or 1), 1)
    except Exception:
        qty = 1

    club_map = mp or ClubProductBarcode.query.filter_by(club_id=cid, product_id=p.id).first()
    rec = DebtTransaction(
        club_id=cid,
        user_id=target_user_id,
        product_id=p.id,
        qty=qty,
        cost_price=float((getattr(club_map, 'purchase_price', None) or 0) or (p.purchase_price or 0)),
        price=0.0,
        reason=reason,
        kind="defect",
    )
    db.session.add(rec)
    db.session.commit()
    return redirect(url_for("debtops.index", ok=1))
