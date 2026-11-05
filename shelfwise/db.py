"""Database helper.

All SQL in ShelfWise is written in MySQL style with %s placeholders, e.g.
    db.all("SELECT * FROM products WHERE quantity <= %s", (5,))
The same code also works with SQLite (used by the tests), because this
file swaps %s for ? when SQLite is used.

Rows always come back as plain Python dictionaries, e.g. row["product_name"].
"""
import datetime
import decimal
import os
import sqlite3

from flask import current_app, g

try:
    import pymysql
    import pymysql.cursors
except ImportError:          # PyMySQL is only needed for MySQL
    pymysql = None

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = {
    "mysql": os.path.join(HERE, "database", "shelfwise_mysql.sql"),
    "sqlite": os.path.join(HERE, "database", "shelfwise_sqlite.sql"),
}


def _clean(row):
    """Turn MySQL types into simple Python types: Decimal -> float, dates -> text."""
    clean = {}
    for key, value in dict(row).items():
        if isinstance(value, decimal.Decimal):
            value = float(value)
        elif isinstance(value, datetime.datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(value, datetime.date):
            value = value.isoformat()
        clean[key] = value
    return clean


class Database:
    """A small wrapper so the rest of the code does not care which database is used."""

    def __init__(self, settings, select_database=True):
        self.engine = settings["DB_ENGINE"]
        if self.engine == "sqlite":
            folder = os.path.dirname(settings["SQLITE_FILE"])
            if folder:
                os.makedirs(folder, exist_ok=True)
            self.conn = sqlite3.connect(settings["SQLITE_FILE"])
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
        else:
            if pymysql is None:
                raise RuntimeError("PyMySQL is not installed. Run: pip install -r requirements.txt")
            self.conn = pymysql.connect(
                host=settings["MYSQL_HOST"], port=settings["MYSQL_PORT"],
                user=settings["MYSQL_USER"], password=settings["MYSQL_PASSWORD"],
                database=settings["MYSQL_DATABASE"] if select_database else None,
                cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4", autocommit=False,
            )

    def _sql(self, sql):
        return sql.replace("%s", "?") if self.engine == "sqlite" else sql

    def run(self, sql, params=()):
        """Run INSERT / UPDATE / DELETE. Returns the cursor (for lastrowid and rowcount)."""
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), params)
        return cur

    def all(self, sql, params=()):
        """Run a SELECT and return a list of dictionaries."""
        cur = self.run(sql, params)
        return [_clean(r) for r in cur.fetchall()]

    def one(self, sql, params=()):
        """Run a SELECT and return the first row (or None)."""
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def value(self, sql, params=()):
        """Run a SELECT and return the first value of the first row."""
        row = self.one(sql, params)
        return list(row.values())[0] if row else None

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def settings_from(app_or_dict):
    keys = ["DB_ENGINE", "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "SQLITE_FILE"]
    source = app_or_dict.config if hasattr(app_or_dict, "config") else app_or_dict
    return {k: source[k] for k in keys}


# The columns ShelfWise needs in each table. Used to spot an old or different database.
EXPECTED = {
    "users": "user_id, full_name, email, password_hash, role, is_active",
    "categories": "category_id, category_name",
    "suppliers": "supplier_id, supplier_name, phone, email",
    "products": "product_id, sku, product_name, brand, category_id, item_condition, cost_price, "
                "sell_price, quantity, reorder_level, warranty_months, is_active",
    "sales": "sale_id, product_id, user_id, quantity, unit_price, unit_cost, total, payment_method, sale_date",
    "waste_records": "waste_id, product_id, user_id, quantity, reason, note, unit_cost, waste_date",
    "stock_movements": "movement_id, product_id, user_id, supplier_id, movement_type, quantity_change, "
                       "balance_after, note, movement_date",
}


def add_reset_table(db):
    """Add the password_resets table if it is missing (for databases made before 'Forgot password?')."""
    if "password_resets" in table_names(db):
        return
    with open(SCHEMA[db.engine], encoding="utf-8") as f:
        text = "".join(line for line in f if not line.strip().startswith("--"))
    for statement in text.split(";"):
        if "CREATE TABLE IF NOT EXISTS password_resets" in statement:
            db.run(statement.strip())
    db.commit()


def rename_old_tables(db):
    """Older ShelfWise databases called the waste table 'write_offs'. Rename it, keeping all the data."""
    names = table_names(db)
    if "write_offs" not in names or "waste_records" in names:
        return
    if db.engine == "mysql":
        db.run("RENAME TABLE write_offs TO waste_records")
    else:
        db.run("ALTER TABLE write_offs RENAME TO waste_records")
    db.run("ALTER TABLE waste_records RENAME COLUMN write_off_id TO waste_id")
    db.run("ALTER TABLE waste_records RENAME COLUMN write_off_date TO waste_date")
    db.commit()


def table_names(db):
    """Names of all tables in the database (empty list = a brand-new, empty database)."""
    if db.engine == "sqlite":
        rows = db.all("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    else:
        rows = db.all("SHOW TABLES")
    return [list(r.values())[0] for r in rows]


def missing_parts(db):
    """Return a list of tables that are missing or have different columns (empty list = all good)."""
    problems = []
    for table, columns in EXPECTED.items():
        try:
            db.all(f"SELECT {columns} FROM {table} LIMIT 1")
        except Exception:
            db.rollback()
            problems.append(table)
    return problems


def create_tables(settings, fresh_database=False):
    """Create the database (MySQL) and all tables from the .sql file. Deletes old data!

    fresh_database=True deletes the whole MySQL database first (used only after the
    user has typed YES), so old tables from earlier versions cannot get in the way.
    """
    engine = settings["DB_ENGINE"]
    if engine == "mysql":
        server = Database(settings, select_database=False)
        name = settings["MYSQL_DATABASE"]
        if fresh_database:
            server.run(f"DROP DATABASE IF EXISTS `{name}`")
        server.run(f"CREATE DATABASE IF NOT EXISTS `{name}` "
                   "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        server.commit()
        server.close()
    db = Database(settings)
    if engine == "mysql":
        db.run("SET FOREIGN_KEY_CHECKS = 0")   # allows old linked tables to be dropped
    with open(SCHEMA[engine], encoding="utf-8") as f:
        lines = [line for line in f if not line.strip().startswith("--")]
    for statement in "".join(lines).split(";"):
        statement = statement.strip()
        upper = statement.upper()
        # The database is already chosen in config.py, so skip these two lines
        if not statement or upper.startswith("CREATE DATABASE") or upper.startswith("USE "):
            continue
        db.run(statement)
    if engine == "mysql":
        db.run("SET FOREIGN_KEY_CHECKS = 1")
    db.commit()
    return db


def get_db():
    """One database connection per web request."""
    if "db" not in g:
        g.db = Database(settings_from(current_app))
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
