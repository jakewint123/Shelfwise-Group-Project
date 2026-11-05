"""ShelfWise business rules.

Every change to stock goes through this file, so the same rules are
used by the web pages, the sample-data script and the tests:
  1. stock can never go below zero
  2. every change is saved in stock_movements (the audit trail)
  3. if anything goes wrong, nothing is saved (rollback)
"""
import math
from datetime import date, datetime, timedelta

CONDITIONS = ["New", "Refurbished", "Used"]
WASTE_REASONS = ["Damaged", "Faulty", "Obsolete", "Lost or stolen", "Sent for recycling"]
PAYMENT_METHODS = ["Card", "Cash"]
SLOW_MOVING_DAYS = 30      # no sale for 30 days = slow-moving
COVER_DAYS = 28            # smart reorder: order enough stock for 4 weeks


class StockError(ValueError):
    """A rule was broken. The message is shown to the user."""


# ------------------------------------------------------------------ small helpers
def now_text(when=None):
    return (when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def whole_number(value, label="Quantity"):
    """Check the value is a whole number above zero."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise StockError(f"{label} must be a whole number.")
    if number <= 0:
        raise StockError(f"{label} must be more than zero.")
    return number


def get_product(db, product_id):
    return db.one(
        "SELECT p.*, c.category_name FROM products p "
        "JOIN categories c ON c.category_id = p.category_id WHERE p.product_id = %s",
        (product_id,),
    )


def active_product(db, product_id):
    product = get_product(db, product_id)
    if product is None:
        raise StockError("Please choose a product.")
    if not product["is_active"]:
        raise StockError(f"{product['product_name']} is no longer sold.")
    return product


def save_movement(db, product_id, user_id, kind, change, note, when, supplier_id=None):
    """Change the stock level and write one row to the audit trail."""
    product = db.one("SELECT quantity FROM products WHERE product_id = %s", (product_id,))
    new_balance = product["quantity"] + change
    if new_balance < 0:
        raise StockError("This would make stock go below zero.")
    db.run("UPDATE products SET quantity = %s WHERE product_id = %s", (new_balance, product_id))
    db.run(
        "INSERT INTO stock_movements (product_id, user_id, supplier_id, movement_type, "
        "quantity_change, balance_after, note, movement_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (product_id, user_id, supplier_id, kind, change, new_balance, note, when),
    )
    return new_balance


# ------------------------------------------------------------------ products
def check_product_form(form):
    """Check the add / edit product form. Returns (data, errors)."""
    errors = []
    data = {
        "sku": form.get("sku", "").strip().upper(),
        "product_name": form.get("product_name", "").strip(),
        "brand": form.get("brand", "").strip(),
        "item_condition": form.get("item_condition", ""),
    }
    if not data["sku"]:
        errors.append("SKU is required.")
    if not data["product_name"]:
        errors.append("Product name is required.")
    if data["item_condition"] not in CONDITIONS:
        errors.append("Please choose a condition: New, Refurbished or Used.")
    try:
        data["category_id"] = int(form.get("category_id", ""))
    except ValueError:
        errors.append("Please choose a category.")
    for field, label in (("cost_price", "Cost price"), ("sell_price", "Selling price")):
        try:
            data[field] = round(float(form.get(field, "")), 2)
            if data[field] < 0:
                errors.append(f"{label} cannot be negative.")
        except ValueError:
            errors.append(f"{label} must be a number.")
    for field, label in (("reorder_level", "Reorder level"), ("warranty_months", "Warranty")):
        try:
            data[field] = int(form.get(field, "") or 0)
            if data[field] < 0:
                errors.append(f"{label} cannot be negative.")
        except ValueError:
            errors.append(f"{label} must be a whole number.")
    return data, errors


def add_product(db, data, user_id, opening_stock=0, when=None):
    when = now_text(when)
    if db.one("SELECT product_id FROM products WHERE sku = %s", (data["sku"],)):
        raise StockError(f"SKU {data['sku']} is already used.")
    try:
        cur = db.run(
            "INSERT INTO products (sku, product_name, brand, category_id, item_condition, cost_price, "
            "sell_price, quantity, reorder_level, warranty_months, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)",
            (data["sku"], data["product_name"], data["brand"], data["category_id"], data["item_condition"],
             data["cost_price"], data["sell_price"], data["reorder_level"], data["warranty_months"], when),
        )
        product_id = cur.lastrowid
        if opening_stock:
            save_movement(db, product_id, user_id, "IN", whole_number(opening_stock, "Opening stock"),
                          "Opening stock", when)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return product_id


def update_product(db, product_id, data):
    if db.one("SELECT product_id FROM products WHERE sku = %s AND product_id <> %s", (data["sku"], product_id)):
        raise StockError(f"SKU {data['sku']} is already used.")
    db.run(
        "UPDATE products SET sku = %s, product_name = %s, brand = %s, category_id = %s, item_condition = %s, "
        "cost_price = %s, sell_price = %s, reorder_level = %s, warranty_months = %s WHERE product_id = %s",
        (data["sku"], data["product_name"], data["brand"], data["category_id"], data["item_condition"],
         data["cost_price"], data["sell_price"], data["reorder_level"], data["warranty_months"], product_id),
    )
    db.commit()


def set_active(db, product_id, active):
    db.run("UPDATE products SET is_active = %s WHERE product_id = %s", (1 if active else 0, product_id))
    db.commit()


# ------------------------------------------------------------------ stock changes
def receive_stock(db, product_id, quantity, user_id, supplier_id=None, note="Delivery", when=None):
    """A delivery arrives: stock goes up."""
    quantity = whole_number(quantity)
    active_product(db, product_id)
    try:
        balance = save_movement(db, product_id, user_id, "IN", quantity, note or "Delivery",
                                now_text(when), supplier_id or None)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return balance


def record_sale(db, product_id, quantity, user_id, payment_method="Card", when=None):
    """Sell ONE product (any quantity). Stock goes down. Returns (sale_id, total)."""
    quantity = whole_number(quantity)
    if payment_method not in PAYMENT_METHODS:
        raise StockError("Please choose Card or Cash.")
    product = active_product(db, product_id)
    if quantity > product["quantity"]:
        raise StockError(
            f"Not enough stock: only {product['quantity']} {product['product_name']} left, "
            f"you asked for {quantity}."
        )
    when = now_text(when)
    total = round(product["sell_price"] * quantity, 2)
    try:
        cur = db.run(
            "INSERT INTO sales (product_id, user_id, quantity, unit_price, unit_cost, total, payment_method, sale_date) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (product_id, user_id, quantity, product["sell_price"], product["cost_price"], total, payment_method, when),
        )
        sale_id = cur.lastrowid
        save_movement(db, product_id, user_id, "SALE", -quantity, f"Sale #{sale_id}", when)
        db.commit()
    except Exception:
        db.rollback()          # nothing is saved if any step fails
        raise
    return sale_id, total


def record_waste(db, product_id, quantity, reason, user_id, note="", when=None):
    """Remove stock that cannot be sold, with a reason."""
    quantity = whole_number(quantity)
    if reason not in WASTE_REASONS:
        raise StockError("Please choose a reason.")
    product = active_product(db, product_id)
    if quantity > product["quantity"]:
        raise StockError(f"Cannot record waste of {quantity}: only {product['quantity']} in stock.")
    when = now_text(when)
    try:
        cur = db.run(
            "INSERT INTO waste_records (product_id, user_id, quantity, reason, note, unit_cost, waste_date) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (product_id, user_id, quantity, reason, note.strip() or None, product["cost_price"], when),
        )
        save_movement(db, product_id, user_id, "WRITE_OFF", -quantity, f"Waste record #{cur.lastrowid} ({reason})", when)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return cur.lastrowid


def stock_count(db, product_id, counted, user_id, reason, when=None):
    """Manager only: after counting the shelf, set stock to the counted number."""
    try:
        counted = int(str(counted).strip())
    except (TypeError, ValueError):
        raise StockError("Counted quantity must be a whole number.")
    if counted < 0:
        raise StockError("Counted quantity cannot be negative.")
    if not reason.strip():
        raise StockError("Please give a reason for the stock count.")
    product = get_product(db, product_id)
    if product is None:
        raise StockError("Product not found.")
    change = counted - product["quantity"]
    if change == 0:
        raise StockError("The count is the same as the system stock. Nothing to change.")
    try:
        save_movement(db, product_id, user_id, "ADJUST", change, f"Stock count: {reason.strip()}", now_text(when))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return counted


# ------------------------------------------------------------------ reports
def days_ago(days, today=None):
    return ((today or date.today()) - timedelta(days=days)).isoformat()


def smart_reorder(product, sold_last_30):
    """'Smart' part: use the last 30 days of sales to estimate how long stock will last."""
    per_day = sold_last_30 / 30
    days_left = round(product["quantity"] / per_day) if per_day > 0 else None
    target = max(math.ceil(per_day * COVER_DAYS), product["reorder_level"] * 2)
    return {"per_day": round(per_day, 2), "days_left": days_left,
            "suggested_order": max(target - product["quantity"], 0)}


def low_stock(db, today=None):
    rows = db.all(
        "SELECT p.*, c.category_name, "
        "(SELECT COALESCE(SUM(s.quantity), 0) FROM sales s WHERE s.product_id = p.product_id "
        " AND s.sale_date >= %s) AS sold_30 "
        "FROM products p JOIN categories c ON c.category_id = p.category_id "
        "WHERE p.is_active = 1 AND p.quantity <= p.reorder_level ORDER BY p.quantity, p.product_name",
        (days_ago(30, today),),
    )
    for r in rows:
        r.update(smart_reorder(r, r["sold_30"]))
    return rows


def low_stock_alert(db, product_id, before):
    """Call this after stock goes down. If the product has just reached its low stock alert level
    (its reorder level), return a message for the screen and show the alert in the ShelfWise window.
    Example: reorder level 4, stock goes from 5 to 4 -> alert. From 4 to 3 -> no new alert."""
    product = get_product(db, product_id)
    if product is None or not (before > product["reorder_level"] >= product["quantity"]):
        return None
    message = (f"Low stock alert: only {product['quantity']} {product['product_name']} left "
               f"(alert level {product['reorder_level']}). The manager has been alerted.")
    print(f"\n*** LOW STOCK ALERT: {product['sku']} {product['product_name']} - "
          f"{product['quantity']} left (alert level {product['reorder_level']}) ***\n", flush=True)
    return message


def alert_history(db, days=30, today=None):
    """Every time a product fell to or below its alert level, worked out from the audit trail."""
    return db.all(
        "SELECT m.movement_id, m.movement_date, m.movement_type, m.quantity_change, m.balance_after, "
        "m.balance_after - m.quantity_change AS before_qty, p.product_id, p.product_name, p.sku, p.reorder_level, "
        "u.full_name FROM stock_movements m JOIN products p ON p.product_id = m.product_id "
        "JOIN users u ON u.user_id = m.user_id "
        "WHERE m.quantity_change < 0 AND m.balance_after <= p.reorder_level "
        "AND m.balance_after - m.quantity_change > p.reorder_level AND DATE(m.movement_date) >= %s "
        "ORDER BY m.movement_date DESC, m.movement_id DESC",
        (days_ago(days, today),),
    )


def slow_moving(db, days=SLOW_MOVING_DAYS, today=None):
    return db.all(
        "SELECT p.*, c.category_name, "
        "(SELECT MAX(s.sale_date) FROM sales s WHERE s.product_id = p.product_id) AS last_sale "
        "FROM products p JOIN categories c ON c.category_id = p.category_id "
        "WHERE p.is_active = 1 AND p.quantity > 0 AND NOT EXISTS "
        "(SELECT 1 FROM sales s WHERE s.product_id = p.product_id AND s.sale_date >= %s) "
        "ORDER BY p.quantity * p.cost_price DESC",
        (days_ago(days, today),),
    )


GROUPS = {"product": "p.product_name", "category": "c.category_name", "condition": "p.item_condition"}


def sales_summary(db, start, end, group="product"):
    """Units, revenue and profit between two dates, grouped by product, category or condition."""
    label = GROUPS.get(group, "p.product_name")
    return db.all(
        f"SELECT {label} AS label, SUM(s.quantity) AS units, ROUND(SUM(s.total), 2) AS revenue, "
        f"ROUND(SUM(s.total - s.quantity * s.unit_cost), 2) AS profit, COUNT(*) AS sales "
        f"FROM sales s JOIN products p ON p.product_id = s.product_id "
        f"JOIN categories c ON c.category_id = p.category_id "
        f"WHERE DATE(s.sale_date) BETWEEN %s AND %s GROUP BY {label} ORDER BY revenue DESC",
        (start, end),
    )


def waste_summary(db, start, end, group="reason"):
    label = {"reason": "w.reason", "product": "p.product_name", "condition": "p.item_condition"}.get(group, "w.reason")
    return db.all(
        f"SELECT {label} AS label, SUM(w.quantity) AS units, ROUND(SUM(w.quantity * w.unit_cost), 2) AS cost, "
        f"COUNT(*) AS records FROM waste_records w JOIN products p ON p.product_id = w.product_id "
        f"WHERE DATE(w.waste_date) BETWEEN %s AND %s GROUP BY {label} ORDER BY cost DESC",
        (start, end),
    )


def stock_by_condition(db):
    return db.all(
        "SELECT item_condition AS label, COUNT(*) AS products, SUM(quantity) AS units, "
        "ROUND(SUM(quantity * cost_price), 2) AS value FROM products WHERE is_active = 1 "
        "GROUP BY item_condition ORDER BY value DESC"
    )


def daily_sales(db, days=14, today=None):
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    rows = db.all(
        "SELECT DATE(sale_date) AS day, ROUND(SUM(total), 2) AS revenue FROM sales "
        "WHERE sale_date >= %s GROUP BY DATE(sale_date)", (start.isoformat(),)
    )
    by_day = {str(r["day"])[:10]: r["revenue"] for r in rows}
    return [{"day": (start + timedelta(days=i)).isoformat(),
             "revenue": by_day.get((start + timedelta(days=i)).isoformat(), 0)} for i in range(days)]


def reconcile(db, product_id):
    """Check: stock in the products table = total of all its movements."""
    stored = db.value("SELECT quantity FROM products WHERE product_id = %s", (product_id,))
    history = db.value("SELECT COALESCE(SUM(quantity_change), 0) AS total FROM stock_movements "
                       "WHERE product_id = %s", (product_id,))
    return int(stored), int(history), int(stored) == int(history)
