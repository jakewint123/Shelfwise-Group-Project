-- ShelfWise database - SQLite version (same design as shelfwise_mysql.sql).
-- Used only if DB_ENGINE = "sqlite" in config.py, and by the automated tests.
-- SQLite has no ENUM type, so CHECK (... IN (...)) is used instead.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS password_resets;
DROP TABLE IF EXISTS stock_movements;
DROP TABLE IF EXISTS waste_records;
DROP TABLE IF EXISTS write_offs;
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'staff' CHECK (role IN ('manager', 'staff')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE categories (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE
);

CREATE TABLE suppliers (
    supplier_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT NOT NULL UNIQUE,
    phone         TEXT,
    email         TEXT
);

CREATE TABLE products (
    product_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL UNIQUE,
    product_name    TEXT NOT NULL,
    brand           TEXT,
    category_id     INTEGER NOT NULL REFERENCES categories(category_id),
    item_condition  TEXT NOT NULL DEFAULT 'New' CHECK (item_condition IN ('New', 'Refurbished', 'Used')),
    cost_price      REAL NOT NULL CHECK (cost_price >= 0),
    sell_price      REAL NOT NULL CHECK (sell_price >= 0),
    quantity        INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    reorder_level   INTEGER NOT NULL DEFAULT 2 CHECK (reorder_level >= 0),
    warranty_months INTEGER NOT NULL DEFAULT 0 CHECK (warranty_months >= 0),
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales (
    sale_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(product_id),
    user_id        INTEGER NOT NULL REFERENCES users(user_id),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     REAL NOT NULL,
    unit_cost      REAL NOT NULL,
    total          REAL NOT NULL,
    payment_method TEXT NOT NULL DEFAULT 'Card' CHECK (payment_method IN ('Cash', 'Card')),
    sale_date      TEXT NOT NULL
);

CREATE TABLE waste_records (
    waste_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(product_id),
    user_id        INTEGER NOT NULL REFERENCES users(user_id),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    reason         TEXT NOT NULL CHECK (reason IN ('Damaged', 'Faulty', 'Obsolete', 'Lost or stolen', 'Sent for recycling')),
    note           TEXT,
    unit_cost      REAL NOT NULL,
    waste_date     TEXT NOT NULL
);

CREATE TABLE stock_movements (
    movement_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    user_id         INTEGER NOT NULL REFERENCES users(user_id),
    supplier_id     INTEGER REFERENCES suppliers(supplier_id),
    movement_type   TEXT NOT NULL CHECK (movement_type IN ('IN', 'SALE', 'WRITE_OFF', 'ADJUST')),
    quantity_change INTEGER NOT NULL,
    balance_after   INTEGER NOT NULL CHECK (balance_after >= 0),
    note            TEXT,
    movement_date   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_resets (
    reset_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    code_hash  TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_sales_date        ON sales(sale_date);
CREATE INDEX idx_sales_product     ON sales(product_id);
CREATE INDEX idx_waste_date        ON waste_records(waste_date);
CREATE INDEX idx_movements_product ON stock_movements(product_id);
