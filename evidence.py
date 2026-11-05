"""Collect evaluation evidence and save it to docs/evidence.json.

    python evidence.py

Uses a temporary SQLite copy of the demo data (and MySQL too if
SHELFWISE_EVIDENCE_MYSQL=1), measures page speed, checks that every
product's stock matches its history, and summarises the sales.
"""
import json
import os
import re
import statistics
import tempfile
import time
from datetime import date

import config
import seed
from shelfwise import create_app, stock
from shelfwise.db import Database

# A fixed 'today', so the evidence (and the numbers in our report) are the same every time it is run.
EVIDENCE_DAY = date(2026, 10, 22)

PAGES = {"Dashboard": "/", "Products": "/products", "Search": "/products?q=dell", "New sale": "/sales/new",
         "Sales report": "/reports?view=sales", "Low stock": "/reports?view=low", "Stock history": "/history"}


def measure(settings):
    seed.seed(settings, today=EVIDENCE_DAY, quiet=True)
    db = Database(settings)
    result = {"dataset": {t: db.value(f"SELECT COUNT(*) AS n FROM {t}")
                          for t in ("products", "sales", "waste_records", "stock_movements")}}
    checks = [stock.reconcile(db, r["product_id"]) for r in db.all("SELECT product_id FROM products")]
    result["reconciliation"] = {"checked": len(checks), "matching": sum(1 for c in checks if c[2])}
    start, end = stock.days_ago(34, EVIDENCE_DAY), EVIDENCE_DAY.isoformat()
    result["sales_by_condition"] = stock.sales_summary(db, start, end, "condition")
    result["sales_by_category"] = stock.sales_summary(db, start, end, "category")
    result["waste_by_reason"] = stock.waste_summary(db, start, end, "reason")
    result["stock_by_condition"] = stock.stock_by_condition(db)
    result["low_stock"] = [{"name": r["product_name"], "quantity": r["quantity"], "days_left": r["days_left"],
                            "suggested_order": r["suggested_order"]} for r in stock.low_stock(db, EVIDENCE_DAY)]
    result["slow_moving"] = [r["product_name"] for r in stock.slow_moving(db, today=EVIDENCE_DAY)]
    result["totals"] = {"revenue": db.value("SELECT ROUND(SUM(total), 2) AS v FROM sales"),
                        "profit": db.value("SELECT ROUND(SUM(total - quantity * unit_cost), 2) AS v FROM sales"),
                        "waste_cost": db.value("SELECT ROUND(SUM(quantity * unit_cost), 2) AS v FROM waste_records")}
    db.close()

    app = create_app({**settings, "TESTING": True, "SECRET_KEY": "evidence"})
    client = app.test_client()
    tok = re.search(r'name="csrf_token" value="([0-9a-f]+)"', client.get("/login").get_data(as_text=True)).group(1)
    client.post("/login", data={"email": "manager@shelfwise.test", "password": "Manager123!", "csrf_token": tok})
    timings = {}
    for name, url in PAGES.items():
        samples = []
        for _ in range(20):
            t0 = time.perf_counter()
            client.get(url)
            samples.append((time.perf_counter() - t0) * 1000)
        timings[name] = {"mean_ms": round(statistics.mean(samples), 1), "max_ms": round(max(samples), 1)}
    result["timings"] = timings
    return result


if __name__ == "__main__":
    base = {k: getattr(config, k) for k in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD")}
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    evidence = {"generated": date.today().isoformat(), "data_up_to": EVIDENCE_DAY.isoformat(),
                "sqlite": measure({**base, "DB_ENGINE": "sqlite", "SQLITE_FILE": path, "MYSQL_DATABASE": ""})}
    os.remove(path)
    if os.environ.get("SHELFWISE_EVIDENCE_MYSQL") == "1":
        evidence["mysql"] = measure({**base, "DB_ENGINE": "mysql", "SQLITE_FILE": "", "MYSQL_DATABASE": "shelfwise_evidence"})
    os.makedirs("docs", exist_ok=True)
    with open(os.path.join("docs", "evidence.json"), "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    for engine in ("sqlite", "mysql"):
        if engine in evidence:
            e = evidence[engine]
            print(engine, e["dataset"], e["reconciliation"], {k: v["mean_ms"] for k, v in e["timings"].items()})
