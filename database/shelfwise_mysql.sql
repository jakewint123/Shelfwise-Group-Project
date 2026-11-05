-- =====================================================================
-- ShelfWise - "Know your shelves."
-- Smart Inventory and Sales Management System for Small Businesses
-- CPU4106-20C Group 6 (Yellow)
--
-- MySQL 8 database for a small shop selling electronics:
-- computers, laptops, monitors, keyboards, parts and accessories.
-- Every product has a condition: New, Refurbished or Used.
-- Parts (RAM, SSDs, chargers ...) are a CATEGORY, so no separate
-- "parts" table is needed. Each sale is for ONE product, so no
-- "sale_items" table is needed.
--
-- How to use: open this file in MySQL Workbench or phpMyAdmin (XAMPP)
-- and run it. Then run shelfwise_sample_data.sql for demo data,
-- or run "python seed.py" which does both.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS shelfwise CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE shelfwise;

-- Remove old tables (children first, because of foreign keys).
-- write_offs was the old name of waste_records.
DROP TABLE IF EXISTS password_resets;
DROP TABLE IF EXISTS stock_movements;
DROP TABLE IF EXISTS waste_records;
DROP TABLE IF EXISTS write_offs;
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS sale_items;
DROP TABLE IF EXISTS parts;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS users;

-- 1. People who can sign in
CREATE TABLE users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('manager', 'staff') NOT NULL DEFAULT 'staff',
    is_active     TINYINT(1) NOT NULL DEFAULT 1,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Groups of products (Laptops, Desktop Computers, Parts & Components ...)
CREATE TABLE categories (
    category_id   INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- 3. Companies we buy stock from
CREATE TABLE suppliers (
    supplier_id   INT AUTO_INCREMENT PRIMARY KEY,
    supplier_name VARCHAR(120) NOT NULL UNIQUE,
    phone         VARCHAR(30) NULL,
    email         VARCHAR(150) NULL
) ENGINE=InnoDB;

-- 4. Everything the shop sells
CREATE TABLE products (
    product_id      INT AUTO_INCREMENT PRIMARY KEY,
    sku             VARCHAR(30)  NOT NULL UNIQUE,
    product_name    VARCHAR(150) NOT NULL,
    brand           VARCHAR(60)  NULL,
    category_id     INT NOT NULL,
    item_condition  ENUM('New', 'Refurbished', 'Used') NOT NULL DEFAULT 'New',
    cost_price      DECIMAL(8,2) NOT NULL,
    sell_price      DECIMAL(8,2) NOT NULL,
    quantity        INT NOT NULL DEFAULT 0,
    reorder_level   INT NOT NULL DEFAULT 2,
    warranty_months INT NOT NULL DEFAULT 0,
    is_active       TINYINT(1) NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cost      CHECK (cost_price >= 0),
    CONSTRAINT chk_price     CHECK (sell_price >= 0),
    CONSTRAINT chk_quantity  CHECK (quantity >= 0),
    CONSTRAINT chk_reorder   CHECK (reorder_level >= 0),
    CONSTRAINT chk_warranty  CHECK (warranty_months >= 0),
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
) ENGINE=InnoDB;

-- 5. One row = one sale of ONE product (simple till)
CREATE TABLE sales (
    sale_id        INT AUTO_INCREMENT PRIMARY KEY,
    product_id     INT NOT NULL,
    user_id        INT NOT NULL,
    quantity       INT NOT NULL,
    unit_price     DECIMAL(8,2) NOT NULL,
    unit_cost      DECIMAL(8,2) NOT NULL,
    total          DECIMAL(10,2) NOT NULL,
    payment_method ENUM('Cash', 'Card') NOT NULL DEFAULT 'Card',
    sale_date      DATETIME NOT NULL,
    CONSTRAINT chk_sale_qty CHECK (quantity > 0),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- 6. Stock that cannot be sold (damaged, faulty, obsolete ...)
CREATE TABLE waste_records (
    waste_id       INT AUTO_INCREMENT PRIMARY KEY,
    product_id     INT NOT NULL,
    user_id        INT NOT NULL,
    quantity       INT NOT NULL,
    reason         ENUM('Damaged', 'Faulty', 'Obsolete', 'Lost or stolen', 'Sent for recycling') NOT NULL,
    note           VARCHAR(255) NULL,
    unit_cost      DECIMAL(8,2) NOT NULL,
    waste_date     DATETIME NOT NULL,
    CONSTRAINT chk_waste_qty CHECK (quantity > 0),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- 7. Audit trail: EVERY change to stock is saved here
CREATE TABLE stock_movements (
    movement_id     INT AUTO_INCREMENT PRIMARY KEY,
    product_id      INT NOT NULL,
    user_id         INT NOT NULL,
    supplier_id     INT NULL,
    movement_type   ENUM('IN', 'SALE', 'WRITE_OFF', 'ADJUST') NOT NULL,
    quantity_change INT NOT NULL,
    balance_after   INT NOT NULL,
    note            VARCHAR(255) NULL,
    movement_date   DATETIME NOT NULL,
    CONSTRAINT chk_balance CHECK (balance_after >= 0),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
) ENGINE=InnoDB;

-- 8. One-time codes for "Forgot password?" (only a hash of the code is stored)
CREATE TABLE IF NOT EXISTS password_resets (
    reset_id   INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    code_hash  VARCHAR(255) NOT NULL,
    expires_at DATETIME NOT NULL,
    attempts   INT NOT NULL DEFAULT 0,
    used       TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- Indexes make searches and reports faster
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_sales_date        ON sales(sale_date);
CREATE INDEX idx_sales_product     ON sales(product_id);
CREATE INDEX idx_waste_date        ON waste_records(waste_date);
CREATE INDEX idx_movements_product ON stock_movements(product_id);
