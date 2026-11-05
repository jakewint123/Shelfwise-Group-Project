"""All the web pages of ShelfWise."""
import csv
import io
from datetime import date, timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from . import stock
from .auth import hash_password, login_required, manager_required
from .db import get_db

bp = Blueprint("main", __name__)


# ------------------------------------------------------------------ helpers
@bp.app_context_processor
def low_stock_count():
    """Number of products at or below their alert level - shown as a badge in the manager's menu."""
    if getattr(g, "user", None) and g.user["role"] == "manager":
        return {"low_alert_count": get_db().value(
            "SELECT COUNT(*) AS v FROM products WHERE is_active = 1 AND quantity <= reorder_level")}
    return {"low_alert_count": 0}


def stock_before(product_id):
    product = stock.get_product(get_db(), product_id)
    return product["quantity"] if product else 0


def alert_if_low(product_id, before):
    message = stock.low_stock_alert(get_db(), product_id, before)
    if message:
        flash(message, "warning")
def categories():
    return get_db().all("SELECT * FROM categories ORDER BY category_name")


def suppliers():
    return get_db().all("SELECT * FROM suppliers ORDER BY supplier_name")


def products_for_forms():
    return get_db().all(
        "SELECT product_id, sku, product_name, item_condition, quantity, sell_price "
        "FROM products WHERE is_active = 1 ORDER BY product_name"
    )


def date_range():
    """Read ?start= and ?end= from the address bar. Default: the last 30 days."""
    try:
        end = date.fromisoformat(request.args.get("end", ""))
    except ValueError:
        end = date.today()
    try:
        start = date.fromisoformat(request.args.get("start", ""))
    except ValueError:
        start = end - timedelta(days=29)
    if start > end:
        start, end = end, start
    return start.isoformat(), end.isoformat()


# ------------------------------------------------------------------ dashboard
@bp.route("/")
@login_required
def dashboard():
    db = get_db()
    week = stock.days_ago(6)
    kpi = {
        "sales_week": db.value("SELECT COALESCE(SUM(total), 0) AS v FROM sales WHERE DATE(sale_date) >= %s", (week,)),
        "profit_week": db.value("SELECT COALESCE(SUM(total - quantity * unit_cost), 0) AS v FROM sales "
                                "WHERE DATE(sale_date) >= %s", (week,)),
        "stock_value": db.value("SELECT COALESCE(SUM(quantity * cost_price), 0) AS v FROM products WHERE is_active = 1"),
        "products": db.value("SELECT COUNT(*) AS v FROM products WHERE is_active = 1"),
        "second_life": db.value(
            "SELECT COALESCE(SUM(s.quantity), 0) AS v FROM sales s JOIN products p ON p.product_id = s.product_id "
            "WHERE p.item_condition IN ('Refurbished', 'Used') AND DATE(s.sale_date) >= %s", (stock.days_ago(29),)),
    }
    low = stock.low_stock(db)
    days = stock.daily_sales(db, 14)
    top = db.all(
        "SELECT p.product_name, p.item_condition, SUM(s.quantity) AS units, ROUND(SUM(s.total), 2) AS revenue "
        "FROM sales s JOIN products p ON p.product_id = s.product_id WHERE DATE(s.sale_date) >= %s "
        "GROUP BY p.product_id, p.product_name, p.item_condition ORDER BY revenue DESC LIMIT 5", (week,))
    by_condition = stock.sales_summary(db, stock.days_ago(29), date.today().isoformat(), "condition")
    return render_template("dashboard.html", kpi=kpi, low=low[:6], low_count=len(low), days=days,
                           chart_max=max([d["revenue"] for d in days] + [1]), top=top, by_condition=by_condition,
                           slow_count=len(stock.slow_moving(db)), last_sale=db.value("SELECT MAX(sale_date) AS v FROM sales"))


# ------------------------------------------------------------------ products
@bp.route("/products")
@login_required
def products():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    condition = request.args.get("condition", "")
    show = request.args.get("show", "active")
    sql = ("SELECT p.*, c.category_name FROM products p JOIN categories c ON c.category_id = p.category_id "
           "WHERE 1 = 1")
    params = []
    if q:
        sql += " AND (p.product_name LIKE %s OR p.sku LIKE %s OR p.brand LIKE %s)"
        params += [f"%{q}%"] * 3
    if category.isdigit():
        sql += " AND p.category_id = %s"
        params.append(int(category))
    if condition in stock.CONDITIONS:
        sql += " AND p.item_condition = %s"
        params.append(condition)
    if show == "active":
        sql += " AND p.is_active = 1"
    elif show == "low":
        sql += " AND p.is_active = 1 AND p.quantity <= p.reorder_level"
    elif show == "inactive":
        sql += " AND p.is_active = 0"
    sql += " ORDER BY p.product_name"
    rows = get_db().all(sql, params)
    return render_template("products.html", products=rows, categories=categories(), conditions=stock.CONDITIONS,
                           q=q, category=category, condition=condition, show=show)


@bp.route("/products/new", methods=["GET", "POST"])
@manager_required
def product_new():
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        data, errors = stock.check_product_form(request.form)
        opening = request.form.get("opening_stock", "").strip() or "0"
        if not opening.isdigit():
            errors.append("Opening stock must be 0 or a whole number.")
        if not errors:
            try:
                product_id = stock.add_product(get_db(), data, g.user["user_id"], int(opening))
                flash(f"{data['product_name']} added.", "success")
                return redirect(url_for("main.product_detail", product_id=product_id))
            except stock.StockError as e:
                errors.append(str(e))
        for e in errors:
            flash(e, "error")
    return render_template("product_form.html", product=None, form=form, categories=categories(),
                           conditions=stock.CONDITIONS)


@bp.route("/products/<int:product_id>")
@login_required
def product_detail(product_id):
    db = get_db()
    product = stock.get_product(db, product_id)
    if product is None:
        abort(404)
    history = db.all(
        "SELECT m.*, u.full_name, s.supplier_name FROM stock_movements m "
        "JOIN users u ON u.user_id = m.user_id LEFT JOIN suppliers s ON s.supplier_id = m.supplier_id "
        "WHERE m.product_id = %s ORDER BY m.movement_date DESC, m.movement_id DESC LIMIT 50", (product_id,))
    sold_30 = db.value("SELECT COALESCE(SUM(quantity), 0) AS v FROM sales WHERE product_id = %s AND sale_date >= %s",
                       (product_id, stock.days_ago(30)))
    stored, total, ok = stock.reconcile(db, product_id)
    return render_template("product_detail.html", product=product, history=history,
                           smart=stock.smart_reorder(product, sold_30), sold_30=sold_30,
                           check={"stored": stored, "total": total, "ok": ok})


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@manager_required
def product_edit(product_id):
    db = get_db()
    product = stock.get_product(db, product_id)
    if product is None:
        abort(404)
    form = request.form if request.method == "POST" else product
    if request.method == "POST":
        data, errors = stock.check_product_form(request.form)
        if not errors:
            try:
                stock.update_product(db, product_id, data)
                flash("Product saved.", "success")
                return redirect(url_for("main.product_detail", product_id=product_id))
            except stock.StockError as e:
                errors.append(str(e))
        for e in errors:
            flash(e, "error")
    return render_template("product_form.html", product=product, form=form, categories=categories(),
                           conditions=stock.CONDITIONS)


@bp.route("/products/<int:product_id>/toggle", methods=["POST"])
@manager_required
def product_toggle(product_id):
    db = get_db()
    product = stock.get_product(db, product_id)
    if product is None:
        abort(404)
    stock.set_active(db, product_id, not product["is_active"])
    flash(f"{product['product_name']} {'hidden from sale' if product['is_active'] else 'back on sale'}.", "success")
    return redirect(url_for("main.product_detail", product_id=product_id))


@bp.route("/products/<int:product_id>/count", methods=["GET", "POST"])
@manager_required
def product_count(product_id):
    db = get_db()
    product = stock.get_product(db, product_id)
    if product is None:
        abort(404)
    if request.method == "POST":
        try:
            before = product["quantity"]
            stock.stock_count(db, product_id, request.form.get("counted"), g.user["user_id"],
                              request.form.get("reason", ""))
            flash("Stock count saved.", "success")
            alert_if_low(product_id, before)
            return redirect(url_for("main.product_detail", product_id=product_id))
        except stock.StockError as e:
            flash(str(e), "error")
    return render_template("stock_count.html", product=product)


@bp.route("/stock/count", methods=["GET", "POST"])
@manager_required
def stock_count_all():
    """Count the whole shop at once. Only products whose counted number is different are saved."""
    db = get_db()
    products = db.all("SELECT product_id, sku, product_name, quantity FROM products WHERE is_active = 1 ORDER BY sku")
    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        changed, problems = 0, []
        for p in products:
            counted = request.form.get(f"count_{p['product_id']}", "").strip()
            if counted == "" or counted == str(p["quantity"]):
                continue
            try:
                stock.stock_count(db, p["product_id"], counted, g.user["user_id"], reason)
                changed += 1
                alert_if_low(p["product_id"], p["quantity"])
            except stock.StockError as e:
                problems.append(f"{p['sku']}: {e}")
        for problem in problems:
            flash(problem, "error")
        if changed or not problems:
            flash(f"Stock count saved: {changed} product(s) changed." if changed else "No differences found, so nothing was changed.",
                  "success")
        return redirect(url_for("main.stock_count_all"))
    return render_template("stock_count_all.html", products=products)


@bp.route("/alerts")
@manager_required
def alerts():
    """Low stock alerts: what needs ordering now, and when each product fell to its alert level."""
    db = get_db()
    return render_template("alerts.html", low=stock.low_stock(db), history=stock.alert_history(db, 30),
                           cover_days=stock.COVER_DAYS)


# ------------------------------------------------------------------ daily tasks
@bp.route("/stock/receive", methods=["GET", "POST"])
@login_required
def receive():
    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id") or 0)
            supplier_id = int(request.form.get("supplier_id") or 0) or None
            balance = stock.receive_stock(get_db(), product_id, request.form.get("quantity"), g.user["user_id"],
                                          supplier_id, request.form.get("note", "").strip() or "Delivery")
            flash(f"Delivery saved. Stock is now {balance}.", "success")
            return redirect(url_for("main.receive"))
        except stock.StockError as e:
            flash(str(e), "error")
    return render_template("receive.html", products=products_for_forms(), suppliers=suppliers(),
                           selected=request.values.get("product_id", ""))


@bp.route("/sales/new", methods=["GET", "POST"])
@login_required
def sale_new():
    db = get_db()
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id") or 0)
            before = stock_before(product_id)
            sale_id, total = stock.record_sale(db, product_id, request.form.get("quantity"), g.user["user_id"],
                                               request.form.get("payment_method", "Card"))
            flash(f"Sale #{sale_id} saved. Total £{total:,.2f}.", "success")
            alert_if_low(product_id, before)
            return redirect(url_for("main.sale_new"))
        except stock.StockError as e:
            flash(str(e), "error")
    recent = db.all(
        "SELECT s.*, p.product_name FROM sales s JOIN products p ON p.product_id = s.product_id "
        "ORDER BY s.sale_date DESC, s.sale_id DESC LIMIT 8")
    return render_template("sale_form.html", products=products_for_forms(), recent=recent, form=form,
                           methods=stock.PAYMENT_METHODS)


@bp.route("/waste/new", methods=["GET", "POST"])
@login_required
def waste_new():
    db = get_db()
    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id") or 0)
            before = stock_before(product_id)
            stock.record_waste(db, product_id, request.form.get("quantity"), request.form.get("reason", ""),
                               g.user["user_id"], request.form.get("note", ""))
            flash("Waste record saved.", "success")
            alert_if_low(product_id, before)
            return redirect(url_for("main.waste_new"))
        except stock.StockError as e:
            flash(str(e), "error")
    recent = db.all(
        "SELECT w.*, p.product_name FROM waste_records w JOIN products p ON p.product_id = w.product_id "
        "ORDER BY w.waste_date DESC, w.waste_id DESC LIMIT 8")
    return render_template("waste.html", products=products_for_forms(), reasons=stock.WASTE_REASONS,
                           recent=recent, selected=request.values.get("product_id", ""))


@bp.route("/history")
@login_required
def history():
    kind = request.args.get("type", "")
    q = request.args.get("q", "").strip()
    sql = ("SELECT m.*, p.product_name, p.sku, u.full_name FROM stock_movements m "
           "JOIN products p ON p.product_id = m.product_id JOIN users u ON u.user_id = m.user_id WHERE 1 = 1")
    params = []
    if kind in ("IN", "SALE", "WRITE_OFF", "ADJUST"):
        sql += " AND m.movement_type = %s"
        params.append(kind)
    if q:
        sql += " AND (p.product_name LIKE %s OR p.sku LIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY m.movement_date DESC, m.movement_id DESC LIMIT 200"
    return render_template("history.html", rows=get_db().all(sql, params), kind=kind, q=q)


# ------------------------------------------------------------------ reports (manager)
REPORTS = {"low": "Low stock + smart reorder", "slow": "Slow-moving", "sales": "Sales and profit",
           "waste": "Waste", "condition": "Stock by condition"}


def report_rows(view, start, end, group):
    db = get_db()
    if view == "low":
        return stock.low_stock(db)
    if view == "slow":
        return stock.slow_moving(db)
    if view == "sales":
        return stock.sales_summary(db, start, end, group)
    if view == "waste":
        return stock.waste_summary(db, start, end, group)
    if view == "condition":
        return stock.stock_by_condition(db)
    abort(404)


@bp.route("/reports")
@manager_required
def reports():
    view = request.args.get("view", "low")
    if view not in REPORTS:
        view = "low"
    start, end = date_range()
    group = request.args.get("group", "product" if view == "sales" else "reason")
    rows = report_rows(view, start, end, group)
    totals = {}
    for key in ("units", "revenue", "profit", "cost", "value", "suggested_order"):
        if rows and key in rows[0]:
            totals[key] = round(sum(r[key] or 0 for r in rows), 2)
    db = get_db()
    summary = {
        "sales": db.value("SELECT COUNT(*) AS v FROM sales"),
        "revenue": db.value("SELECT COALESCE(SUM(total), 0) AS v FROM sales"),
        "first_sale": db.value("SELECT MIN(sale_date) AS v FROM sales"),
        "waste_records": db.value("SELECT COUNT(*) AS v FROM waste_records"),
        "waste_cost": db.value("SELECT COALESCE(SUM(quantity * unit_cost), 0) AS v FROM waste_records"),
    }
    return render_template("reports.html", view=view, reports=REPORTS, rows=rows, start=start, end=end, summary=summary,
                           group=group, totals=totals, slow_days=stock.SLOW_MOVING_DAYS, cover_days=stock.COVER_DAYS)


@bp.route("/reports/<view>.csv")
@manager_required
def report_csv(view):
    if view not in REPORTS:
        abort(404)
    start, end = date_range()
    rows = report_rows(view, start, end, request.args.get("group", "product" if view == "sales" else "reason"))
    out = io.StringIO()
    writer = csv.writer(out)
    if rows:
        writer.writerow(rows[0].keys())
        for r in rows:
            writer.writerow(r.values())
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=shelfwise_{view}_{date.today()}.csv"})


# ------------------------------------------------------------------ suppliers and users (manager)
@bp.route("/suppliers", methods=["GET", "POST"])
@manager_required
def supplier_list():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("supplier_name", "").strip()
        if not name:
            flash("Supplier name is required.", "error")
        elif db.one("SELECT supplier_id FROM suppliers WHERE supplier_name = %s", (name,)):
            flash("That supplier already exists.", "error")
        else:
            db.run("INSERT INTO suppliers (supplier_name, phone, email) VALUES (%s, %s, %s)",
                   (name, request.form.get("phone", "").strip() or None, request.form.get("email", "").strip() or None))
            db.commit()
            flash(f"{name} added.", "success")
            return redirect(url_for("main.supplier_list"))
    rows = db.all(
        "SELECT s.*, (SELECT COALESCE(SUM(m.quantity_change), 0) FROM stock_movements m "
        "WHERE m.supplier_id = s.supplier_id) AS units_supplied FROM suppliers s ORDER BY s.supplier_name")
    return render_template("suppliers.html", suppliers=rows)


@bp.route("/users", methods=["GET", "POST"])
@manager_required
def users():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "staff")
        password = request.form.get("password", "")
        errors = []
        if not name or "@" not in email:
            errors.append("Name and a valid email are required.")
        if role not in ("staff", "manager"):
            errors.append("Role must be staff or manager.")
        if len(password) < 8 or password.isalpha() or password.isdigit():
            errors.append("Password must be at least 8 characters with letters and numbers.")
        if db.one("SELECT user_id FROM users WHERE email = %s", (email,)):
            errors.append("That email is already used.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db.run("INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                   (name, email, hash_password(password), role))
            db.commit()
            flash(f"Account created for {name}.", "success")
            return redirect(url_for("main.users"))
    return render_template("users.html", users=db.all("SELECT * FROM users ORDER BY role, full_name"))


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@manager_required
def user_edit(user_id):
    """Manager changes a person's name, email, role or password."""
    db = get_db()
    user = db.one("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if user is None:
        abort(404)
    form = request.form if request.method == "POST" else user
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", user["role"])
        password = request.form.get("password", "")
        errors = []
        if not name or "@" not in email:
            errors.append("Name and a valid email are required.")
        if role not in ("staff", "manager"):
            errors.append("Role must be staff or manager.")
        if user_id == g.user["user_id"] and role != "manager":
            errors.append("You cannot remove your own manager role.")
        if db.one("SELECT user_id FROM users WHERE email = %s AND user_id <> %s", (email, user_id)):
            errors.append("That email is already used by another account.")
        if password and (len(password) < 8 or password.isalpha() or password.isdigit()):
            errors.append("New password must be at least 8 characters with letters and numbers.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db.run("UPDATE users SET full_name = %s, email = %s, role = %s WHERE user_id = %s",
                   (name, email, role, user_id))
            if password:      # only change the password if a new one was typed
                db.run("UPDATE users SET password_hash = %s WHERE user_id = %s", (hash_password(password), user_id))
            db.commit()
            flash(f"Account saved for {name}.", "success")
            return redirect(url_for("main.users"))
    return render_template("user_edit.html", user=user, form=form)


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@manager_required
def user_toggle(user_id):
    if user_id == g.user["user_id"]:
        flash("You cannot switch off your own account.", "error")
        return redirect(url_for("main.users"))
    db = get_db()
    user = db.one("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if user is None:
        abort(404)
    db.run("UPDATE users SET is_active = %s WHERE user_id = %s", (0 if user["is_active"] else 1, user_id))
    db.commit()
    flash(f"{user['full_name']} {'switched off' if user['is_active'] else 'switched on'}.", "success")
    return redirect(url_for("main.users"))
