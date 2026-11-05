"""Create the ShelfWise tables and fill them with MADE-UP demo data.

Usage:   python seed.py
It uses the database settings in config.py (MySQL by default).
WARNING: this deletes any data already in the ShelfWise tables.

The shop data is synthetic (invented) for testing and the viva. Product
names are real models so the demo looks realistic, but the prices,
stock levels and sales are not real.
"""
import math
import random
import sys
from datetime import date, datetime, time, timedelta

from werkzeug.security import generate_password_hash

import config
from shelfwise import stock
from shelfwise.db import create_tables

CATEGORIES = ["Laptops", "Desktop Computers", "Monitors", "Keyboards & Mice",
              "Parts & Components", "Accessories & Cables", "Networking"]

SUPPLIERS = [  # made-up companies
    ("TechSource UK Ltd", "0161 555 0101", "orders@techsource.example"),
    ("ReNew IT Refurbishers", "0113 555 0202", "sales@renewit.example"),
    ("Northern Components Ltd", "0191 555 0303", "trade@northcomp.example"),
    ("Second Byte Trade-ins", "0151 555 0404", "hello@secondbyte.example"),
]

# sku, name, brand, category, condition, cost, price, reorder, warranty months, sales per day, supplier number
PRODUCTS = [
    ("LAP-001", "Latitude 5420 14in i5 16GB 256GB SSD", "Dell", "Laptops", "Refurbished", 260, 399, 2, 12, 0.25, 2),
    ("LAP-002", "ThinkPad T14 Gen 3 i5 16GB 512GB SSD", "Lenovo", "Laptops", "New", 720, 949, 1, 24, 0.08, 1),
    ("LAP-003", "EliteBook 840 G6 i5 8GB 256GB SSD", "HP", "Laptops", "Used", 150, 249, 2, 3, 0.20, 4),
    ("LAP-004", "MacBook Air M1 13in 8GB 256GB", "Apple", "Laptops", "Refurbished", 420, 579, 1, 12, 0.12, 2),
    ("LAP-005", "Aspire 5 15.6in Ryzen 5 8GB 512GB SSD", "Acer", "Laptops", "New", 380, 499, 2, 24, 0.15, 1),
    ("DES-001", "OptiPlex 7070 SFF i5 8GB 256GB SSD", "Dell", "Desktop Computers", "Refurbished", 140, 229, 2, 12, 0.20, 2),
    ("DES-002", "ProDesk 400 G7 i5 8GB 512GB SSD", "HP", "Desktop Computers", "New", 430, 579, 1, 12, 0.06, 1),
    ("DES-003", "ThinkCentre M720q Tiny i3 8GB", "Lenovo", "Desktop Computers", "Used", 85, 149, 2, 3, 0.15, 4),
    ("MON-001", "P2419H 24in Full HD Monitor", "Dell", "Monitors", "Refurbished", 60, 99, 3, 12, 0.30, 2),
    ("MON-002", "S27R350 27in IPS Monitor", "Samsung", "Monitors", "New", 105, 149, 2, 24, 0.15, 1),
    ("MON-003", "P222va 22in Monitor", "HP", "Monitors", "Used", 30, 55, 2, 3, 0.03, 4),
    ("KEY-001", "K120 USB Keyboard", "Logitech", "Keyboards & Mice", "New", 8, 15, 5, 24, 0.60, 1),
    ("KEY-002", "MK270 Wireless Keyboard and Mouse", "Logitech", "Keyboards & Mice", "New", 18, 29.99, 4, 24, 0.40, 1),
    ("KEY-003", "Wired Optical Mouse", "Microsoft", "Keyboards & Mice", "New", 6, 12, 5, 12, 0.50, 1),
    ("KEY-004", "K55 RGB Gaming Keyboard", "Corsair", "Keyboards & Mice", "Used", 15, 25, 1, 3, 0.0, 4),
    ("PRT-001", "8GB DDR4 3200 Laptop RAM", "Kingston", "Parts & Components", "New", 14, 24.99, 4, 36, 0.35, 3),
    ("PRT-002", "870 EVO 500GB SATA SSD", "Samsung", "Parts & Components", "New", 38, 54.99, 3, 60, 0.30, 3),
    ("PRT-003", "65W USB-C Laptop Charger", "Lenovo", "Parts & Components", "New", 16, 29.99, 4, 12, 0.35, 3),
    ("PRT-004", "Replacement Battery for Latitude 5420", "Dell", "Parts & Components", "New", 35, 59, 2, 12, 0.10, 3),
    ("PRT-005", "4GB DDR3 Desktop RAM", "Crucial", "Parts & Components", "Used", 3, 8, 3, 1, 0.02, 4),
    ("PRT-006", "1TB 7200rpm Hard Drive", "Seagate", "Parts & Components", "Refurbished", 18, 32, 2, 6, 0.12, 2),
    ("PRT-007", "CX550 550W Power Supply", "Corsair", "Parts & Components", "Refurbished", 28, 45, 1, 6, 0.06, 2),
    ("ACC-001", "7-in-1 USB-C Hub", "Anker", "Accessories & Cables", "New", 17, 29.99, 3, 18, 0.25, 1),
    ("ACC-002", "HDMI Cable 2m", "Belkin", "Accessories & Cables", "New", 2.5, 7.99, 8, 12, 0.60, 3),
    ("ACC-003", "15.6in Laptop Bag", "Targus", "Accessories & Cables", "New", 11, 22, 3, 12, 0.15, 1),
    ("NET-001", "Archer AX23 Wi-Fi 6 Router", "TP-Link", "Networking", "New", 42, 64.99, 2, 36, 0.08, 1),
    ("NET-002", "Cat6 Ethernet Cable 5m", "Belkin", "Networking", "New", 2, 6.99, 6, 12, 0.30, 3),
]

DAYS = 35


def at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute))


def settings_from_config():
    return {k: getattr(config, k) for k in ("DB_ENGINE", "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER",
                                             "MYSQL_PASSWORD", "MYSQL_DATABASE", "SQLITE_FILE")}


def seed(settings, today=None, days=DAYS, quiet=False, fresh_database=False):
    rng = random.Random(6)          # fixed seed: the same data every time (repeatable)
    today = today or date.today()
    db = create_tables(settings, fresh_database)

    # Users (made-up people). Passwords are stored as hashes only.
    db.run("INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
           ("Priya Shah", "manager@shelfwise.test", generate_password_hash("Manager123!"), "manager"))
    db.run("INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
           ("Tom Reed", "staff@shelfwise.test", generate_password_hash("Staff123!"), "staff"))
    manager = db.value("SELECT user_id FROM users WHERE email = %s", ("manager@shelfwise.test",))
    staff = db.value("SELECT user_id FROM users WHERE email = %s", ("staff@shelfwise.test",))

    category_ids = {}
    for name in CATEGORIES:
        category_ids[name] = db.run("INSERT INTO categories (category_name) VALUES (%s)", (name,)).lastrowid
    supplier_ids = []
    for name, phone, email in SUPPLIERS:
        supplier_ids.append(db.run("INSERT INTO suppliers (supplier_name, phone, email) VALUES (%s, %s, %s)",
                                   (name, phone, email)).lastrowid)
    db.commit()

    start = today - timedelta(days=days - 1)
    info = {}
    for sku, name, brand, cat, cond, cost, price, reorder, warranty, rate, sup in PRODUCTS:
        data = {"sku": sku, "product_name": name, "brand": brand, "category_id": category_ids[cat],
                "item_condition": cond, "cost_price": cost, "sell_price": price,
                "reorder_level": reorder, "warranty_months": warranty}
        opening = max(reorder * 3, math.ceil(rate * 14) + reorder)
        pid = stock.add_product(db, data, manager, opening, when=at(start - timedelta(days=1), 17))
        info[pid] = {"rate": rate, "reorder": reorder, "opening": opening, "supplier": supplier_ids[sup - 1]}

    for offset in range(days):
        day = start + timedelta(days=offset)
        weekend = day.weekday() >= 5
        # Deliveries arrive on Mondays and Thursdays for anything low on stock
        if day.weekday() in (0, 3):
            for pid, p in info.items():
                product = stock.get_product(db, pid)
                if p["rate"] > 0.02 and product["quantity"] <= p["reorder"]:
                    stock.receive_stock(db, pid, p["opening"], staff, p["supplier"],
                                        f"Invoice {day.strftime('%d%m')}-{pid:02d}", when=at(day, 9))
        # Customers buy things during the day
        for pid, p in info.items():
            chance = p["rate"] * (1.4 if weekend else 1.0)
            for _ in range(3):
                if rng.random() < chance / 3:
                    qty = 2 if (p["rate"] >= 0.4 and rng.random() < 0.25) else 1
                    if stock.get_product(db, pid)["quantity"] >= qty:
                        payment = "Cash" if rng.random() < 0.2 else "Card"
                        stock.record_sale(db, pid, qty, staff, payment,
                                          when=at(day, rng.randint(10, 17), rng.randint(0, 59)))
        # Now and then something is damaged or faulty
        if rng.random() < 0.18:
            pid = rng.choice(list(info))
            if stock.get_product(db, pid)["quantity"] > 1:
                reason = rng.choice(["Damaged", "Faulty", "Damaged", "Faulty", "Lost or stolen"])
                note = {"Damaged": "Damaged in delivery", "Faulty": "Customer return, does not power on",
                        "Lost or stolen": "Missing at stock check"}[reason]
                stock.record_waste(db, pid, 1, reason, staff, note, when=at(day, 17, 30))

    # A few planned events so every report has something to show
    stock.record_waste(db, 20, 2, "Obsolete", manager, "DDR3 no longer in demand", when=at(today - timedelta(days=9), 18))
    stock.record_waste(db, 11, 1, "Sent for recycling", manager, "Screen faulty - sent to WEEE recycler",
                    when=at(today - timedelta(days=6), 18))
    stock.stock_count(db, 24, stock.get_product(db, 24)["quantity"] - 1, manager, "Monthly shelf count",
                      when=at(today - timedelta(days=3), 18))
    db.close()
    if not quiet:
        print(f"Created the ShelfWise database ({settings['DB_ENGINE']}) with {len(PRODUCTS)} products "
              f"and {days} days of made-up sales.")


if __name__ == "__main__":
    try:
        seed(settings_from_config())
    except Exception as error:      # explain common problems in plain English
        print("\nCould not create the database:", error)
        if config.DB_ENGINE == "mysql":
            print("Check that MySQL is running (XAMPP: press Start next to MySQL) and that the\n"
                  "user name and password in config.py are correct.\n"
                  "No MySQL? Set DB_ENGINE = \"sqlite\" in config.py and run this again.")
        sys.exit(1)
