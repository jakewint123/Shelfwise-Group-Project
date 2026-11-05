# ShelfWise – *Know your shelves.*

**Smart Inventory and Sales Management System for Small Businesses**

CPU4106-20C Group Project · **Group 6 (Yellow)** · Fly-Tech simulated internship
Supports **UN SDG 12 – Responsible Consumption and Production** (Target 12.5: reduce waste through prevention, reduction, recycling and *reuse*).

## The problem

Small electronics shops sell new, refurbished and used computers, laptops, monitors, keyboards, parts and accessories. Many still track stock in notebooks or spreadsheets, so they run out of popular items, over-buy slow ones, and cannot see which products or conditions (new, refurbished, used) make the most profit. ShelfWise keeps products, deliveries, sales and waste in one MySQL database and turns them into simple, *smart* reports.

## What it does

| Area | Feature |
|---|---|
| Sign-in | Manager and staff accounts, hashed passwords, form protection (CSRF), role checks, **Forgot password?** with a one-time 6-digit code |
| Products | 27 demo products in 7 categories; condition **New / Refurbished / Used**; brand, warranty, cost and selling price |
| Parts | Parts (RAM, SSDs, chargers, batteries, power supplies) are a **category**, so no separate parts table |
| Receive stock | Deliveries linked to a supplier |
| New sale | **One product per sale**, card or cash; stock goes down automatically; blocked if there is not enough stock |
| Waste records | Damaged, faulty, obsolete, lost or stolen, sent for recycling |
| Stock history | Every change is saved (audit trail), can be searched by product or SKU, and is checked on each product page |
| **Low stock alerts** | Each product has an alert level (reorder level). When stock falls to it – e.g. from 12 to 4 – the manager sees a banner, a count in the menu and the alerts page; the alert also prints in the black window |
| **Smart reorder** | Uses the last 30 days of sales to show *days of stock left* and a *suggested order* for 4 weeks |
| Reports | Low stock, slow-moving, sales and profit (by product, category or condition), waste, stock by condition, CSV export |
| Manager tools | Suppliers, users, whole-shop stock count, hide products from sale |
| Design and accessibility | Page design in HTML and CSS by Sahan; colours and keyboard use meet **WCAG 2.2 level AA** (see `docs/ACCESSIBILITY.md`) |

## How to run it (Windows + XAMPP)

> **Do not open the files in `shelfwise/templates/` directly.** They only work when ShelfWise is running.

1. Install **Python 3.10+** from python.org (tick *Add Python to PATH*).
2. Open the **XAMPP Control Panel** and press **Start** next to **MySQL**.
3. Unzip this folder (right-click → *Extract All*).
4. Double-click **`START_SHELFWISE_Windows.bat`**.
   The first time, it installs Flask and PyMySQL, creates the `shelfwise` database with demo data, and opens <http://127.0.0.1:5000>.

If your MySQL has a password, the black window asks for it once (the typing is hidden) and saves it in **`config.py`**.
If you already had an older `shelfwise` database, the window says so and asks: **YES** (replace the old tables), **NEW** (keep them and use `shelfwise_app`) or **Enter** (change nothing).
No MySQL? In `config.py` change `DB_ENGINE = "mysql"` to `"sqlite"` – no server needed.

Demo logins (made-up people):

| Role | Email | Password |
|---|---|---|
| Manager | manager@shelfwise.test | Manager123! |
| Staff | staff@shelfwise.test | Staff123! |

### Using MySQL Workbench or phpMyAdmin instead

Run `database/shelfwise_mysql.sql` (creates the database and 8 tables), then `database/shelfwise_sample_data.sql` (demo data). Then start the app with `python run.py`.

## The database (MySQL)

| Table | Purpose |
|---|---|
| `users` | People who can sign in (manager / staff) |
| `categories` | Laptops, Desktop Computers, Monitors, Keyboards & Mice, Parts & Components, Accessories & Cables, Networking |
| `suppliers` | Companies we buy from |
| `products` | Everything we sell, with `item_condition` = New, Refurbished or Used |
| `sales` | One row = one sale of one product (saves price **and** cost, so profit is correct later) |
| `waste_records` | Stock that cannot be sold, with a reason |
| `stock_movements` | Audit trail: every IN, SALE, WRITE_OFF and ADJUST |
| `password_resets` | One-time codes for *Forgot password?* (only a hash is stored; 15 minutes, 5 tries) |

The old `parts` and `sale_items` tables are no longer needed: parts are a category, and each sale is one product.

## Tests

```bash
python -m unittest -v                 # 49 tests on a temporary SQLite database
set SHELFWISE_TEST_ENGINE=mysql       # Windows: run the same tests on MySQL (uses shelfwise_test)
python -m unittest -v
```

## Project structure

```
ShelfWise/
├── START_SHELFWISE_Windows.bat   double-click to start (Windows)
├── START_SHELFWISE_Mac.command   double-click to start (Mac)
├── config.py                     database settings – edit here
├── run.py                        starts the web server
├── seed.py                       creates tables + made-up demo data
├── evidence.py                   measures speed and checks stock
├── database/
│   ├── shelfwise_mysql.sql       MySQL tables (main)
│   ├── shelfwise_sample_data.sql MySQL demo data
│   └── shelfwise_sqlite.sql      SQLite version (tests / no MySQL)
├── shelfwise/
│   ├── db.py                     connects to MySQL or SQLite
│   ├── auth.py                   sign-in, roles, form protection
│   ├── stock.py                  business rules + reports + smart reorder
│   ├── routes.py                 web pages
│   ├── templates/                HTML pages (Sahan's design)
│   └── static/                   style.css (accessible colours) + logo
├── tests/test_shelfwise.py       49 automated tests
├── tools/                        a11y_check.py, contrast.py, export_sample_data.py
└── docs/                         diagrams, screenshots, evidence
```

## Team – Group 6 (Yellow)

We followed the **Waterfall model** in four phases – Planning & Analysis, Design, Development, Testing & Delivery – each signed off by a milestone. Our Gantt chart is in `docs/Group_Project_Gantt_Chart.xlsx`.

| Member | Role | Tasks in the Gantt chart |
|---|---|---|
| Arif Zaman Wali | Project Manager (with Roberto) and back-end developer | Project scope; research question, aim and objectives (with Sahan); back end for products, inventory, sales and orders; integration |
| Roberto Lima Felix | Project Manager (with Arif) and database developer | Scope sign-off (M1); database tables; MySQL database set-up |
| Jacob Thomas Winters | Database designer and tools lead | Roles and GitHub set-up; normalisation and ERD |
| Sahan Dumesh Aluthge Don | Front-end developer | Research question, aim and objectives (with Arif); pages and forms |
| Natalia Severi Lafuza | Tester and evidence lead | Architecture and tech stack; testing and bug fixing; report and evidence |

All five members prepare the presentation and demo, and submit together.

## Ethics

All shop data is **made up** by `seed.py` (real product model names, invented prices and sales). No customer data is stored. Staff accounts hold only name, email, role and a password hash.

## Locked out?

Run `python reset_password.py` (Windows: double-click `RESET_PASSWORD_Windows.bat`). It lists every account, lets you pick one and set a new password, and switches the account back on.

## Put ShelfWise online (Render)

1. Put this folder on GitHub (the files `render.yaml`, `wsgi.py` and `requirements.txt` must be at the top of the repository).
   Use the `config.py` from this download – it has **no password** in it. Never upload a `config.py` that holds your MySQL password.
2. Sign in at render.com with GitHub → **New** → **Blueprint** → choose the repository → **Apply**.
   (Or **New → Web Service**: build command `pip install -r requirements.txt`, start command `gunicorn wsgi:app --workers 1 --bind 0.0.0.0:$PORT`,
   and add the setting `SHELFWISE_SECRET_KEY` with a long random value.)
3. Wait for "Live", then open the `onrender.com` link and sign in with the demo accounts.

Things to know about the free plan:
- It goes to sleep after a period with no visitors; the first visit after that takes about a minute.
- Files are not kept when the server restarts, so ShelfWise uses SQLite and **creates the demo data again** on each start. Anything you add online is lost after a restart – fine for a demo.
- The *Forgot password?* code appears in Render → your service → **Logs**.
- To keep data permanently, use an online MySQL database and set `SHELFWISE_DB_ENGINE=mysql`, `SHELFWISE_MYSQL_HOST`, `SHELFWISE_MYSQL_PORT`, `SHELFWISE_MYSQL_USER`, `SHELFWISE_MYSQL_PASSWORD` and `SHELFWISE_MYSQL_DATABASE` in Render's **Environment** page.
