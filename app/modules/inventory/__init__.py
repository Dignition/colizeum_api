# -*- coding: utf-8 -*-
from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
from flask_login import login_required, current_user
from sqlalchemy import text

from ...extensions import db
from ...acl import get_active_club_id, allowed_club_ids
from ...security import roles_required
from ...models.inventory import Product, InventorySession, InventoryCount

bp = Blueprint("inventory", __name__, url_prefix="/inventory", template_folder="../../templates/inventory")


def _ensure_tables():
    try:
        db.session.execute(text('SELECT 1 FROM "inventory_session" LIMIT 1'))
    except Exception:
        db.create_all()


def _active_session(cid: int) -> InventorySession | None:
    _ensure_tables()
    s = (
        db.session.query(InventorySession)
        .filter(InventorySession.club_id == cid, InventorySession.closed_at.is_(None))
        .order_by(InventorySession.started_at.desc())
        .first()
    )
    return s


@bp.route("/", methods=["GET", "POST"])
@login_required
@roles_required("superadmin", "owner")
def index():
    cid_param = request.args.get("club_id")
    try:
        # Не выбираем активный клуб по умолчанию — требуем явного выбора в UI
        cid = int(cid_param) if cid_param else 0
    except Exception:
        cid = 0

    if not cid or cid not in allowed_club_ids(current_user):
        if request.method == 'POST':
            flash('Сначала выберите клуб.', 'warning')
        return render_template('inventory/index.html', clubs=_list_clubs(), club_id=0, items=[], debts={}, has_session=False)

    # POST: импорт файла
    if request.method == 'POST':
        f = request.files.get('file')
        if not f:
            flash('Выберите файл .xlsx/.csv', 'warning')
            return redirect(url_for('inventory.index', club_id=cid))
        filename = (getattr(f, 'filename', '') or '').lower()
        content = f.read()
        rows = []
        import io, csv
        errors: list[str] = []

        def parse_expected(x):
            try:
                return int(float(str(x).replace(',', '.')))
            except Exception:
                return 0

        if filename.endswith('.xlsx'):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
                ws = wb.active
                it = ws.iter_rows(values_only=True)
                try: next(it)
                except Exception: pass
                headers = list(next(it, []) or [])
                idx = {str(headers[i]).strip(): i for i in range(len(headers))}
                name_i = idx.get('Название')
                qty_i = idx.get('Ост. на складе') or idx.get('Остаток на складе') or idx.get('Остаток')
                for r in it:
                    if not r: continue
                    name = (str(r[name_i]).strip() if name_i is not None and name_i < len(r) and r[name_i] is not None else '')
                    expected = parse_expected(r[qty_i]) if (qty_i is not None and qty_i < len(r)) else 0
                    rows.append({'name': name, 'expected_qty': expected})
            except Exception as e:
                flash(f'Не удалось прочитать XLSX: {e}', 'danger')
                return redirect(url_for('inventory.index', club_id=cid))
        else:
            try:
                text_data = content.decode('utf-8-sig')
            except Exception:
                text_data = content.decode(errors='ignore')
            reader = csv.DictReader(io.StringIO(text_data), delimiter=';')
            if not reader.fieldnames:
                reader = csv.DictReader(io.StringIO(text_data))
            for row in reader:
                name = (row.get('name') or row.get('Название') or '').strip()
                expected = parse_expected(row.get('expected_qty') or row.get('Ост. на складе') or row.get('Остаток') or 0)
                rows.append({'name': name, 'expected_qty': expected})

        if not rows:
            flash('Пустой файл импорта.', 'warning')
            return redirect(url_for('inventory.index', club_id=cid))

        sess = _active_session(cid)
        if not sess:
            sess = InventorySession(club_id=cid)
            db.session.add(sess); db.session.flush()

        existing = {ic.product_id: ic for ic in db.session.query(InventoryCount).filter_by(session_id=sess.id).all()}

        imported = 0
        for row in rows:
            name = row['name']
            if not name:
                errors.append('Пропущена строка: отсутствует название'); continue
            raw_expected = row.get('expected_qty') if isinstance(row, dict) else None
            try:
                expected = int(raw_expected or 0)
            except Exception:
                expected = 0
            p = Product.query.filter_by(name=name).first()
            if not p:
                if expected <= 0:
                    continue
                errors.append(f'Не найден товар: "{name}"'); continue
            ic = existing.get(p.id)
            if not ic:
                ic = InventoryCount(session_id=sess.id, product_id=p.id, expected_qty=expected, counted_qty=0)
                db.session.add(ic); existing[p.id] = ic
            else:
                ic.expected_qty = expected
            imported += 1

        db.session.commit()
        if errors:
            flash('Импорт завершён с ошибками (часть строк пропущена).', 'warning')
        flash(f'Импортировано позиций: {imported}.', 'primary')
        items = _items_for_session(cid, sess.id)
        debts_map = _debts_qty(cid)
        admin_stats, shortage_value = _admin_stats(cid, sess, items, debts_map)
        return render_template('inventory/index.html', clubs=_list_clubs(), club_id=cid,
                               items=items, debts=debts_map, import_errors=errors,
                               admin_stats=admin_stats, shortage_value=shortage_value,
                               price_map=_purchase_prices_map(cid), has_session=True)

    sess = _active_session(cid)
    items = _items_for_session(cid, sess.id) if sess else []
    debts_map = _debts_qty(cid)
    admin_stats, shortage_value = _admin_stats(cid, sess, items, debts_map)
    return render_template('inventory/index.html', clubs=_list_clubs(), club_id=cid, items=items, debts=debts_map,
                           admin_stats=admin_stats, shortage_value=shortage_value,
                           price_map=_purchase_prices_map(cid), has_session=bool(sess))


def _list_clubs():
    rows = db.session.execute(text('SELECT id,name FROM "club" WHERE COALESCE(is_active,1)=1 ORDER BY name')).mappings().all()
    return rows


def _items_for_session(cid: int, sess_id: int):
    q = db.session.execute(text('''
        SELECT ic.product_id AS id, p.name AS name, ic.expected_qty, COALESCE(ic.counted_qty,0) AS counted
        FROM inventory_count ic JOIN product p ON p.id = ic.product_id
        WHERE ic.session_id = :s
        ORDER BY p.name
    '''), {'s': sess_id}).mappings().all()
    return list(q)


def _debts_qty(cid: int) -> dict[int, int]:
    rows = db.session.execute(text('''
        SELECT product_id, COALESCE(SUM(qty),0) AS q
        FROM debt_transaction
        WHERE club_id = :c
        GROUP BY product_id
    '''), {'c': cid}).all()
    return {int(r[0]): int(r[1]) for r in rows}


def _month_bounds_from_session(sess: InventorySession | None):
    from datetime import date
    from calendar import monthrange
    if sess and getattr(sess, 'started_at', None):
        d = getattr(sess.started_at, 'date', lambda: None)() or sess.started_at.date()
        y, m = d.year, d.month
    else:
        today = date.today(); y, m = today.year, today.month
    d1 = date(y, m, 1)
    d2 = date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
    total_shifts_in_month = monthrange(y, m)[1] * 2
    return d1, d2, total_shifts_in_month


def _purchase_prices_map(cid: int) -> dict[int, float]:
    rows = db.session.execute(text('''
        SELECT p.id, COALESCE(MAX(cb.purchase_price), COALESCE(p.purchase_price,0)) AS pp
        FROM product p
        LEFT JOIN club_product_barcode cb ON cb.product_id = p.id AND cb.club_id = :c
        GROUP BY p.id
    '''), {'c': cid}).all()
    return {int(r[0]): float(r[1] or 0) for r in rows}


def _admin_stats(cid: int, sess: InventorySession | None, items: list[dict], debts_map: dict[int, int]) -> tuple[list[dict], float]:
    d1, d2, total_shifts = _month_bounds_from_session(sess)
    price_map = _purchase_prices_map(cid)
    shortage_value = 0.0
    for it in items:
        pid = int(it['id'])
        expected = int(it.get('expected_qty') or 0)
        counted = int(it.get('counted') or 0)
        debt_q = int(debts_map.get(pid, 0) or 0)
        # Суммируем с учетом знака: излишки (отрицательная недосдача) уменьшают общую сумму
        shortage_units = (expected - counted - debt_q)
        shortage_value += shortage_units * float(price_map.get(pid, 0.0))

    # Учитываем владельцев и администраторов клуба, а также superadmin,
    # если он выходил на смены в этом клубе в выбранном месяце.
    rows = db.session.execute(text('''
        SELECT u.id, COALESCE(u.full_name,u.username) AS name, COUNT(s.id) AS shifts
        FROM "user" u
        LEFT JOIN "user_club" m ON m.user_id = u.id AND m.club_id = :c
        LEFT JOIN shift s ON s.user_id = u.id AND s.club_id = :c AND date(s.start_ts) >= :d1 AND date(s.start_ts) < :d2
        WHERE (m.role IN ('owner','club_admin'))
           OR (u.role = 'superadmin' AND EXISTS (
                SELECT 1 FROM shift sx
                WHERE sx.user_id = u.id AND sx.club_id = :c AND date(sx.start_ts) >= :d1 AND date(sx.start_ts) < :d2
           ))
        GROUP BY u.id, name
        ORDER BY name
    '''), {'c': cid, 'd1': d1.isoformat(), 'd2': d2.isoformat()}).mappings().all()

    stats: list[dict] = []
    for r in rows:
        cnt = int(r['shifts'] or 0)
        share = (cnt / float(total_shifts)) if total_shifts else 0.0
        allocated = round(shortage_value * share, 2)
        stats.append({'user_id': int(r['id']), 'name': r['name'], 'shifts': cnt, 'share': share, 'allocated': allocated})
    return stats, round(shortage_value, 2)


@bp.post('/save')
@login_required
@roles_required("superadmin", "owner")
def save():
    cid = get_active_club_id(current_user)
    if not cid or cid not in allowed_club_ids(current_user):
        return jsonify({'ok': False, 'error': 'forbidden'}), 403
    sess = _active_session(cid)
    if not sess:
        return jsonify({'ok': False, 'error': 'no_session'}), 400

    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    rows = payload.get('rows') or []
    saved = 0
    for r in rows:
        try:
            pid = int(r.get('product_id') or 0)
            fridge = int(r.get('fridge') or 0)
            store = int(r.get('store') or 0)
        except Exception:
            continue
        total = max(fridge, 0) + max(store, 0)
        db.session.execute(text('UPDATE "inventory_count" SET counted_qty=:q WHERE session_id=:s AND product_id=:p'),
                           {'q': total, 's': sess.id, 'p': pid})
        saved += 1
    db.session.commit()
    return jsonify({'ok': True, 'saved': saved})


@bp.post('/reset-session')
@login_required
@roles_required("superadmin", "owner")
def reset_session():
    try:
        cid = int(request.form.get('club_id') or request.args.get('club_id') or 0)
    except Exception:
        cid = 0
    if not cid or cid not in allowed_club_ids(current_user):
        flash('Недостаточно прав для действия.', 'warning')
        return redirect(url_for('inventory.index', club_id=cid or None))
    sess = _active_session(cid)
    if not sess:
        flash('Нет активной сессии для очистки.', 'warning')
        return redirect(url_for('inventory.index', club_id=cid))
    db.session.execute(text('DELETE FROM "inventory_count" WHERE session_id=:s'), {'s': sess.id})
    db.session.commit()
    flash('Текущая сессия очищена.', 'primary')
    return redirect(url_for('inventory.index', club_id=cid))


@bp.post('/close-session')
@login_required
@roles_required("superadmin", "owner")
def close_session():
    try:
        cid = int(request.form.get('club_id') or request.args.get('club_id') or 0)
    except Exception:
        cid = 0
    if not cid or cid not in allowed_club_ids(current_user):
        flash('Недостаточно прав для действия.', 'warning')
        return redirect(url_for('inventory.index', club_id=cid or None))
    sess = _active_session(cid)
    if not sess:
        flash('Нет активной сессии.', 'warning')
        return redirect(url_for('inventory.index', club_id=cid))
    sess.closed_at = datetime.utcnow()
    db.session.add(sess)
    db.session.commit()
    flash('Сессия закрыта. Создайте новую импортом файла.', 'primary')
    return redirect(url_for('inventory.index', club_id=cid))
