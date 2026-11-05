"""ShelfWise automated tests (T01-T35 in the test matrix).

Run:   python -m unittest -v
By default the tests use a temporary SQLite database, so they work on any
computer. To run them on MySQL instead (uses a separate "shelfwise_test"
database, never your real one):
       set SHELFWISE_TEST_ENGINE=mysql      (Windows)
       export SHELFWISE_TEST_ENGINE=mysql   (Mac / Linux)
"""
import os
import re
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta

import config
from shelfwise import create_app, stock
from shelfwise.auth import hash_password
from shelfwise.db import Database, create_tables

ENGINE = os.environ.get("SHELFWISE_TEST_ENGINE", "sqlite")
MANAGER = ("manager@test.local", "Manager123!")
STAFF = ("staff@test.local", "Staff123!")


def test_settings():
    settings = {"DB_ENGINE": ENGINE, "MYSQL_HOST": config.MYSQL_HOST, "MYSQL_PORT": config.MYSQL_PORT,
                "MYSQL_USER": config.MYSQL_USER, "MYSQL_PASSWORD": config.MYSQL_PASSWORD,
                "MYSQL_DATABASE": "shelfwise_test", "SQLITE_FILE": ""}
    if ENGINE == "sqlite":
        fd, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        settings["SQLITE_FILE"] = path
    return settings


def build_fixture(settings):
    """Small, known data so every expected answer can be worked out by hand."""
    db = create_tables(settings)
    db.run("INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
           ("Test Manager", MANAGER[0], hash_password(MANAGER[1]), "manager"))
    db.run("INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
           ("Test Staff", STAFF[0], hash_password(STAFF[1]), "staff"))
    db.run("INSERT INTO categories (category_name) VALUES (%s)", ("Laptops",))
    db.run("INSERT INTO categories (category_name) VALUES (%s)", ("Parts & Components",))
    db.run("INSERT INTO suppliers (supplier_name) VALUES (%s)", ("Test Supplier",))
    db.commit()
    products = [
        ("LAP-001", "Refurbished Laptop", "Dell", 1, "Refurbished", 200, 300, 2, 12, 10),
        ("PRT-001", "500GB SSD", "Samsung", 2, "New", 40, 55, 3, 60, 8),
        ("KEY-001", "Used Keyboard", "Logitech", 2, "Used", 10, 20, 1, 3, 5),
    ]
    for sku, name, brand, cat, cond, cost, price, reorder, warranty, qty in products:
        stock.add_product(db, {"sku": sku, "product_name": name, "brand": brand, "category_id": cat,
                               "item_condition": cond, "cost_price": cost, "sell_price": price,
                               "reorder_level": reorder, "warranty_months": warranty}, 1, qty)
    return db


class ShelfWiseTest(unittest.TestCase):
    def setUp(self):
        self.settings = test_settings()
        self.db = build_fixture(self.settings)
        self.app = create_app({**self.settings, "TESTING": True, "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.db.close()
        if ENGINE == "sqlite":
            os.remove(self.settings["SQLITE_FILE"])

    # helpers
    def token(self, page="/login"):
        html = self.client.get(page).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([0-9a-f]+)"', html).group(1)

    def login(self, who=MANAGER):
        return self.client.post("/login", data={"email": who[0], "password": who[1], "csrf_token": self.token()},
                                follow_redirects=True)

    def post(self, url, data):
        data = dict(data)
        data["csrf_token"] = self.token("/")
        return self.client.post(url, data=data, follow_redirects=True)

    def qty(self, product_id):
        self.db.commit()      # see the latest data written by the web pages
        return self.db.value("SELECT quantity FROM products WHERE product_id = %s", (product_id,))


class T_Security(ShelfWiseTest):
    def test_T01_valid_login_opens_dashboard(self):
        html = self.login(STAFF).get_data(as_text=True)
        self.assertIn("Dashboard", html)
        self.assertIn("Test Staff", html)

    def test_T02_wrong_password_is_rejected(self):
        html = self.login((STAFF[0], "wrong123")).get_data(as_text=True)
        self.assertIn("Email or password is wrong", html)
        self.assertNotIn("Sign out", html)

    def test_T03_pages_need_sign_in(self):
        response = self.client.get("/products")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_T04_sign_out_ends_session(self):
        self.login(STAFF)
        self.post("/logout", {})
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_T05_passwords_are_hashed(self):
        stored = self.db.value("SELECT password_hash FROM users WHERE email = %s", (STAFF[0],))
        self.assertNotEqual(stored, STAFF[1])
        self.assertTrue(stored.startswith(("scrypt:", "pbkdf2:")))

    def test_T06_form_without_token_is_rejected(self):
        self.login(STAFF)
        response = self.client.post("/sales/new", data={"product_id": 1, "quantity": 1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.qty(1), 10)


class T_Products(ShelfWiseTest):
    def form(self, **changes):
        data = {"sku": "MON-001", "product_name": "24in Monitor", "brand": "Dell", "category_id": "1",
                "item_condition": "Refurbished", "cost_price": "60", "sell_price": "99",
                "reorder_level": "3", "warranty_months": "12", "opening_stock": "6"}
        data.update(changes)
        return data

    def test_T07_manager_adds_product_with_opening_stock(self):
        self.login()
        html = self.post("/products/new", self.form()).get_data(as_text=True)
        self.assertIn("24in Monitor added", html)
        self.db.commit()
        row = self.db.one("SELECT quantity, item_condition FROM products WHERE sku = %s", ("MON-001",))
        self.assertEqual((row["quantity"], row["item_condition"]), (6, "Refurbished"))

    def test_T08_duplicate_sku_is_rejected(self):
        self.login()
        html = self.post("/products/new", self.form(sku="LAP-001")).get_data(as_text=True)
        self.assertIn("SKU LAP-001 is already used", html)

    def test_T09_bad_product_data_is_rejected(self):
        self.login()
        html = self.post("/products/new", self.form(product_name="", sell_price="-5", item_condition="Broken")).get_data(as_text=True)
        self.assertIn("Product name is required", html)
        self.assertIn("Selling price cannot be negative", html)
        self.assertIn("Please choose a condition", html)
        self.assertEqual(self.db.value("SELECT COUNT(*) AS n FROM products"), 3)

    def test_T10_edit_keeps_stock_the_same(self):
        self.login()
        self.post("/products/1/edit", self.form(sku="LAP-001", product_name="Latitude 5420", sell_price="349"))
        self.db.commit()
        row = self.db.one("SELECT product_name, sell_price, quantity FROM products WHERE product_id = 1")
        self.assertEqual((row["product_name"], row["sell_price"], row["quantity"]), ("Latitude 5420", 349, 10))

    def test_T11_search_by_name_brand_and_sku(self):
        self.login(STAFF)
        self.assertIn("500GB SSD", self.client.get("/products?q=samsung").get_data(as_text=True))
        html = self.client.get("/products?q=KEY-001").get_data(as_text=True)
        self.assertIn("Used Keyboard", html)
        self.assertNotIn("500GB SSD", html)

    def test_T12_filter_by_condition(self):
        self.login(STAFF)
        html = self.client.get("/products?condition=Used").get_data(as_text=True)
        self.assertIn("Used Keyboard", html)
        self.assertNotIn("Refurbished Laptop", html)

    def test_T13_hidden_product_cannot_be_sold(self):
        self.login()
        self.post("/products/2/toggle", {})
        self.db.commit()
        with self.assertRaises(stock.StockError):
            stock.record_sale(self.db, 2, 1, 2)


class T_Stock(ShelfWiseTest):
    def test_T14_receive_stock_with_supplier(self):
        self.login(STAFF)
        self.post("/stock/receive", {"product_id": 2, "quantity": 12, "supplier_id": 1, "note": "Invoice 1"})
        self.assertEqual(self.qty(2), 20)
        row = self.db.one("SELECT supplier_id, movement_type FROM stock_movements ORDER BY movement_id DESC LIMIT 1")
        self.assertEqual((row["supplier_id"], row["movement_type"]), (1, "IN"))

    def test_T15_sale_reduces_stock_and_totals_correctly(self):
        self.login(STAFF)
        html = self.post("/sales/new", {"product_id": 2, "quantity": 3, "payment_method": "Cash"}).get_data(as_text=True)
        self.assertIn("Total £165.00", html)
        self.assertEqual(self.qty(2), 5)

    def test_T15b_recent_sales_newest_first(self):
        # Regression test for defect D01: recent sales were sorted by ID, not by date.
        stock.record_sale(self.db, 2, 1, 2, when=datetime.now())
        stock.record_sale(self.db, 3, 1, 2, when=datetime.now() - timedelta(days=2))
        self.login(STAFF)
        html = self.client.get("/sales/new").get_data(as_text=True)
        recent = html[html.index("Recent sales"):]
        self.assertLess(recent.index("500GB SSD"), recent.index("Used Keyboard"))

    def test_T16_sale_above_stock_is_blocked(self):
        self.login(STAFF)
        html = self.post("/sales/new", {"product_id": 3, "quantity": 6, "payment_method": "Card"}).get_data(as_text=True)
        self.assertIn("Not enough stock: only 5 Used Keyboard left", html)
        self.assertEqual(self.qty(3), 5)
        self.assertEqual(self.db.value("SELECT COUNT(*) AS n FROM sales"), 0)

    def test_T17_bad_quantities_are_rejected(self):
        for bad in ("0", "-1", "abc", ""):
            with self.assertRaises(stock.StockError):
                stock.record_sale(self.db, 1, bad, 2)
            with self.assertRaises(stock.StockError):
                stock.receive_stock(self.db, 1, bad, 2)
        self.assertEqual(self.qty(1), 10)

    def test_T18_sale_saves_cost_for_profit(self):
        sale_id, total = stock.record_sale(self.db, 1, 2, 2)
        row = self.db.one("SELECT unit_price, unit_cost, total FROM sales WHERE sale_id = %s", (sale_id,))
        self.assertEqual((row["unit_price"], row["unit_cost"], row["total"]), (300, 200, 600))

    def test_T19_payment_method_must_be_card_or_cash(self):
        with self.assertRaises(stock.StockError):
            stock.record_sale(self.db, 1, 1, 2, "Bitcoin")

    def test_T20_waste_with_reason(self):
        self.login(STAFF)
        html = self.post("/waste/new", {"product_id": 1, "quantity": 1, "reason": "Faulty",
                                             "note": "No display"}).get_data(as_text=True)
        self.assertIn("Waste record saved", html)
        self.assertEqual(self.qty(1), 9)
        row = self.db.one("SELECT quantity, reason, unit_cost FROM waste_records")
        self.assertEqual((row["quantity"], row["reason"], row["unit_cost"]), (1, "Faulty", 200))

    def test_T21_waste_above_stock_is_blocked(self):
        with self.assertRaises(stock.StockError):
            stock.record_waste(self.db, 3, 6, "Damaged", 2)
        self.assertEqual(self.qty(3), 5)

    def test_T22_waste_needs_valid_reason(self):
        for reason in ("", "Bored of it"):
            with self.assertRaises(stock.StockError):
                stock.record_waste(self.db, 1, 1, reason, 2)

    def test_T23_reconciliation_10_plus_5_minus_3_minus_2(self):
        stock.receive_stock(self.db, 1, 5, 2, 1)
        stock.record_sale(self.db, 1, 3, 2)
        stock.record_waste(self.db, 1, 2, "Damaged", 2)
        stored, history, ok = stock.reconcile(self.db, 1)
        self.assertEqual((stored, history, ok), (10, 10, True))
        self.assertEqual(self.db.value("SELECT COUNT(*) AS n FROM stock_movements WHERE product_id = 1"), 4)

    def test_T24_stock_count_cannot_go_below_zero(self):
        with self.assertRaises(stock.StockError):
            stock.stock_count(self.db, 2, -1, 1, "Count")
        stock.stock_count(self.db, 2, 7, 1, "Monthly count")
        self.assertEqual(self.qty(2), 7)
        self.assertTrue(stock.reconcile(self.db, 2)[2])


    def test_T45_whole_shop_stock_count_saves_only_changed_rows(self):
        self.login(MANAGER)
        page = self.client.get("/stock/count").get_data(as_text=True)
        self.assertIn("Check shelf quantities", page)
        before_1, before_2 = self.qty(1), self.qty(2)
        html = self.post("/stock/count", {"reason": "Monthly shelf count", "count_1": before_1,
                                          "count_2": before_2 - 2}).get_data(as_text=True)
        self.assertIn("1 product(s) changed", html)
        self.assertEqual(self.qty(1), before_1)            # unchanged row: no movement saved
        self.assertEqual(self.qty(2), before_2 - 2)
        self.assertEqual(self.db.value("SELECT COUNT(*) AS v FROM stock_movements WHERE movement_type = 'ADJUST'"), 1)
        self.assertTrue(stock.reconcile(self.db, 2)[2])
        self.post("/logout", {})
        self.login(STAFF)
        self.assertEqual(self.client.get("/stock/count").status_code, 403)   # managers only

    def test_T46_stock_history_search(self):
        names = {r["product_id"]: r["product_name"] for r in self.db.all("SELECT product_id, product_name FROM products")}
        sku_2 = self.db.value("SELECT sku AS v FROM products WHERE product_id = 2")
        stock.record_sale(self.db, 1, 1, 2)
        stock.record_sale(self.db, 2, 1, 2)
        self.login(STAFF)
        html = self.client.get(f"/history?q={sku_2}").get_data(as_text=True)
        self.assertIn(names[2], html)
        self.assertNotIn(names[1], html)
        html = self.client.get("/history?type=SALE").get_data(as_text=True)
        self.assertIn(names[1], html)
        self.assertIn(names[2], html)

    def test_T47_low_stock_alert_when_level_is_reached(self):
        # Example from the shop: alert level 4. Stock above 4 -> a sale takes it to 4 -> the manager is alerted.
        self.db.run("UPDATE products SET reorder_level = 4 WHERE product_id = 2")
        self.db.commit()
        start = self.qty(2)
        stock.record_sale(self.db, 2, start - 5, 2)                  # leave 5 in stock: no alert yet
        self.assertEqual(self.qty(2), 5)
        self.login(STAFF)
        html = self.post("/sales/new", {"product_id": 2, "quantity": 1, "payment_method": "Card"}).get_data(as_text=True)
        self.assertIn("Low stock alert: only 4", html)                # 5 -> 4: alert
        html = self.post("/sales/new", {"product_id": 2, "quantity": 1, "payment_method": "Card"}).get_data(as_text=True)
        self.assertNotIn("Low stock alert", html)                     # 4 -> 3: already alerted, no second alert
        self.post("/logout", {})
        self.login(MANAGER)
        page = self.client.get("/alerts").get_data(as_text=True)
        name = self.db.value("SELECT product_name AS v FROM products WHERE product_id = 2")
        self.assertIn(name, page)
        self.assertIn("5 → <strong>4</strong>", page)                 # alert history shows the fall
        self.assertEqual(len(stock.alert_history(self.db)), 1)

    def test_T48_manager_sees_alert_badge_and_banner(self):
        self.db.run("UPDATE products SET reorder_level = quantity WHERE product_id = 1")   # product 1 is now at its level
        self.db.commit()
        self.login(MANAGER)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Low stock alert:", html)
        self.assertIn('class="nav-count"', html)
        self.post("/logout", {})
        self.login(STAFF)
        self.assertNotIn('class="nav-count"', self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get("/alerts").status_code, 403)

class T_Reports(ShelfWiseTest):
    def test_T25_low_stock_at_reorder_level(self):
        self.assertNotIn("PRT-001", [r["sku"] for r in stock.low_stock(self.db)])
        stock.record_sale(self.db, 2, 5, 2)          # 8 -> 3 = reorder level
        self.assertIn("PRT-001", [r["sku"] for r in stock.low_stock(self.db)])

    def test_T26_smart_reorder_calculation(self):
        # 15 sold in 30 days = 0.5 a day. Stock 4 lasts 8 days.
        # Order for 28 days = 14, which is more than 2 x reorder level (6). 14 - 4 = 10.
        result = stock.smart_reorder({"quantity": 4, "reorder_level": 3}, 15)
        self.assertEqual(result, {"per_day": 0.5, "days_left": 8, "suggested_order": 10})
        no_sales = stock.smart_reorder({"quantity": 1, "reorder_level": 3}, 0)
        self.assertEqual((no_sales["days_left"], no_sales["suggested_order"]), (None, 5))

    def test_T27_slow_moving_rule(self):
        stock.record_sale(self.db, 1, 1, 2, when=datetime.now() - timedelta(days=40))
        stock.record_sale(self.db, 2, 1, 2)
        slow = [r["sku"] for r in stock.slow_moving(self.db, 30)]
        self.assertIn("LAP-001", slow)       # last sold 40 days ago
        self.assertIn("KEY-001", slow)       # never sold
        self.assertNotIn("PRT-001", slow)    # sold today

    def test_T28_sales_and_profit_by_condition(self):
        stock.record_sale(self.db, 1, 2, 2)  # Refurbished: 600 revenue, 200 profit
        stock.record_sale(self.db, 2, 4, 2)  # New: 220 revenue, 60 profit
        stock.record_sale(self.db, 3, 1, 2)  # Used: 20 revenue, 10 profit
        today = date.today().isoformat()
        rows = {r["label"]: (r["revenue"], r["profit"]) for r in stock.sales_summary(self.db, today, today, "condition")}
        self.assertEqual(rows, {"Refurbished": (600, 200), "New": (220, 60), "Used": (20, 10)})

    def test_T29_waste_totals(self):
        stock.record_waste(self.db, 1, 1, "Faulty", 2)     # 200
        stock.record_waste(self.db, 2, 2, "Damaged", 2)    # 80
        stock.record_waste(self.db, 3, 1, "Faulty", 2)     # 10
        today = date.today().isoformat()
        rows = {r["label"]: (int(r["units"]), r["cost"]) for r in stock.waste_summary(self.db, today, today, "reason")}
        self.assertEqual(rows, {"Faulty": (2, 210), "Damaged": (2, 80)})

    def test_T30_stock_value_by_condition(self):
        rows = {r["label"]: r["value"] for r in stock.stock_by_condition(self.db)}
        self.assertEqual(rows, {"Refurbished": 2000, "New": 320, "Used": 50})

    def test_T31_csv_export(self):
        self.login()
        stock.record_sale(self.db, 1, 1, 2)
        response = self.client.get("/reports/sales.csv")
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn("label,units,revenue,profit,sales", response.get_data(as_text=True))


class T_Roles(ShelfWiseTest):
    def test_T32_staff_cannot_open_manager_pages(self):
        self.login(STAFF)
        for url in ("/reports", "/users", "/suppliers", "/products/new", "/products/1/edit", "/products/1/count"):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_T33_manager_adds_user_and_weak_password_rejected(self):
        self.login()
        html = self.post("/users", {"full_name": "New Person", "email": "new@test.local", "role": "staff",
                                    "password": "Welcome123"}).get_data(as_text=True)
        self.assertIn("Account created", html)
        html = self.post("/users", {"full_name": "Weak", "email": "weak@test.local", "role": "staff",
                                    "password": "short"}).get_data(as_text=True)
        self.assertIn("at least 8 characters", html)

    def test_T34_manager_adds_supplier(self):
        self.login()
        html = self.post("/suppliers", {"supplier_name": "PC Parts Direct", "phone": "0123"}).get_data(as_text=True)
        self.assertIn("PC Parts Direct added", html)
        html = self.post("/suppliers", {"supplier_name": "PC Parts Direct"}).get_data(as_text=True)
        self.assertIn("already exists", html)


class T_EditUsers(ShelfWiseTest):
    def test_T38_manager_edits_name_email_and_password(self):
        self.login()
        staff_id = self.db.value("SELECT user_id FROM users WHERE email = %s", (STAFF[0],))
        html = self.post(f"/users/{staff_id}/edit", {"full_name": "Jacob Thomas Winters", "email": "jacob@test.local",
                                                     "role": "staff", "password": "NewPass123"}).get_data(as_text=True)
        self.assertIn("Account saved for Jacob Thomas Winters", html)
        self.db.commit()
        row = self.db.one("SELECT full_name, email, role FROM users WHERE user_id = %s", (staff_id,))
        self.assertEqual((row["full_name"], row["email"], row["role"]), ("Jacob Thomas Winters", "jacob@test.local", "staff"))
        self.post("/logout", {})
        self.assertIn("Dashboard", self.login(("jacob@test.local", "NewPass123")).get_data(as_text=True))

    def test_T39_edit_rules_and_staff_blocked(self):
        self.login()
        manager_id = self.db.value("SELECT user_id FROM users WHERE email = %s", (MANAGER[0],))
        html = self.post(f"/users/{manager_id}/edit", {"full_name": "Boss", "email": STAFF[0], "role": "staff",
                                                       "password": "short"}).get_data(as_text=True)
        self.assertIn("cannot remove your own manager role", html)
        self.assertIn("already used by another account", html)
        self.assertIn("at least 8 characters", html)
        self.db.commit()
        self.assertEqual(self.db.value("SELECT full_name FROM users WHERE user_id = %s", (manager_id,)), "Test Manager")
        self.post("/logout", {})
        self.login(STAFF)
        self.assertEqual(self.client.get(f"/users/{manager_id}/edit").status_code, 403)


class T_ForgotPassword(ShelfWiseTest):
    def setUp(self):
        super().setUp()
        from shelfwise import auth
        self.auth = auth
        self.real_make_code = auth.make_code
        auth.make_code = lambda: "123456"          # a known code, so the test can type it

    def tearDown(self):
        self.auth.make_code = self.real_make_code
        super().tearDown()

    def ask_code(self, email):
        return self.client.post("/forgot", data={"email": email, "csrf_token": self.token("/forgot")},
                                follow_redirects=True).get_data(as_text=True)

    def reset(self, email, code, password, confirm=None):
        return self.client.post("/reset", data={"email": email, "code": code, "password": password,
                                                "confirm": confirm or password, "csrf_token": self.token("/forgot")},
                                follow_redirects=True).get_data(as_text=True)

    def test_T40_forgot_password_full_flow(self):
        self.assertIn("Forgot password?", self.client.get("/login").get_data(as_text=True))
        self.assertIn("reset code is now shown", self.ask_code(STAFF[0]))
        stored = self.db.value("SELECT code_hash FROM password_resets ORDER BY reset_id DESC LIMIT 1")
        self.assertNotEqual(stored, "123456")                       # only a hash is stored
        self.assertIn("Password changed", self.reset(STAFF[0], "123456", "BrandNew123"))
        self.assertIn("Dashboard", self.login((STAFF[0], "BrandNew123")).get_data(as_text=True))
        self.post("/logout", {})
        self.assertIn("Email or password is wrong", self.login(STAFF).get_data(as_text=True))   # old password gone
        self.assertIn("expired or is not valid", self.reset(STAFF[0], "123456", "Another123"))  # code used once only

    def test_T41_wrong_codes_and_unknown_email(self):
        html = self.ask_code("nobody@test.local")
        self.assertIn("reset code is now shown", html)                  # same message: email not revealed
        self.assertEqual(self.db.value("SELECT COUNT(*) AS n FROM password_resets"), 0)
        self.ask_code(STAFF[0])
        self.assertIn("do not match", self.reset(STAFF[0], "123456", "BrandNew123", "Different123"))
        self.assertIn("at least 8 characters", self.reset(STAFF[0], "123456", "short"))
        self.assertIn("4 tries left", self.reset(STAFF[0], "000000", "BrandNew123"))
        for _ in range(4):
            self.reset(STAFF[0], "000000", "BrandNew123")
        self.assertIn("expired or is not valid", self.reset(STAFF[0], "123456", "BrandNew123"))  # locked after 5

    def test_T42_expired_code_is_rejected(self):
        self.ask_code(STAFF[0])
        self.db.run("UPDATE password_resets SET expires_at = %s", ("2000-01-01 00:00:00",))
        self.db.commit()
        self.assertIn("expired or is not valid", self.reset(STAFF[0], "123456", "BrandNew123"))

    def test_T43_reset_table_added_to_older_database(self):
        from shelfwise.db import add_reset_table, table_names
        self.db.run("DROP TABLE password_resets")
        self.db.commit()
        self.assertNotIn("password_resets", table_names(self.db))
        add_reset_table(self.db)
        self.assertIn("password_resets", table_names(self.db))


class T_Database(ShelfWiseTest):
    def drop_users_table(self):
        """Pretend the database is an old one by removing a table (links between tables switched off first)."""
        self.db.run("SET FOREIGN_KEY_CHECKS = 0" if ENGINE == "mysql" else "PRAGMA foreign_keys = OFF")
        self.db.run("DROP TABLE users")

    def test_T44_old_write_offs_table_is_renamed(self):
        # The team's final ERD renamed write_offs to waste_records. Older databases are upgraded, keeping the data.
        from shelfwise.db import missing_parts, rename_old_tables, table_names
        stock.record_waste(self.db, 1, 1, "Faulty", 2, "test")
        self.db.run("ALTER TABLE waste_records RENAME COLUMN waste_id TO write_off_id")
        self.db.run("ALTER TABLE waste_records RENAME COLUMN waste_date TO write_off_date")
        self.db.run("RENAME TABLE waste_records TO write_offs" if ENGINE == "mysql" else "ALTER TABLE waste_records RENAME TO write_offs")
        self.db.commit()
        self.assertEqual(missing_parts(self.db), ["waste_records"])
        rename_old_tables(self.db)
        self.assertNotIn("write_offs", table_names(self.db))
        self.assertEqual(missing_parts(self.db), [])
        row = self.db.one("SELECT waste_id, reason, waste_date FROM waste_records")
        self.assertEqual(row["reason"], "Faulty")

    def test_T36_old_database_is_detected(self):
        # Regression test for defect D08: an older 'products' table must not be mistaken for ShelfWise's.
        from shelfwise.db import missing_parts
        self.assertEqual(missing_parts(self.db), [])
        self.drop_users_table()
        self.db.commit()
        self.assertEqual(missing_parts(self.db), ["users"])

    def test_T37_friendly_page_instead_of_internal_server_error(self):
        # Regression test for defect D08: a database problem shows a helpful page, not a blank error.
        self.drop_users_table()
        self.db.commit()
        self.app.config["PROPAGATE_EXCEPTIONS"] = False   # behave like the real app, not test mode
        response = self.client.post("/login", data={"email": MANAGER[0], "password": MANAGER[1],
                                                    "csrf_token": self.token()})
        self.assertEqual(response.status_code, 500)
        html = response.get_data(as_text=True)
        self.assertIn("Something went wrong", html)
        self.assertIn("start ShelfWise again", html)


class T_Performance(unittest.TestCase):
    def test_T35_pages_are_fast_with_35_days_of_data(self):
        import seed
        settings = test_settings()
        try:
            seed.seed(settings, quiet=True)
            app = create_app({**settings, "TESTING": True, "SECRET_KEY": "test"})
            client = app.test_client()
            html = client.get("/login").get_data(as_text=True)
            tok = re.search(r'name="csrf_token" value="([0-9a-f]+)"', html).group(1)
            client.post("/login", data={"email": "manager@shelfwise.test", "password": "Manager123!", "csrf_token": tok})
            for url in ("/", "/products", "/reports?view=sales", "/reports?view=low", "/history"):
                start = time.perf_counter()
                for _ in range(5):
                    self.assertEqual(client.get(url).status_code, 200)
                self.assertLess((time.perf_counter() - start) / 5 * 1000, 500, url)
        finally:
            if ENGINE == "sqlite":
                os.remove(settings["SQLITE_FILE"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
