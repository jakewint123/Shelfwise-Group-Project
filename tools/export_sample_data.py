"""Write database/shelfwise_sample_data.sql from the current database.

Run "python seed.py" first, then:  python tools/export_sample_data.py
The .sql file can be imported in MySQL Workbench or phpMyAdmin after
running shelfwise_mysql.sql.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import seed                                  # noqa: E402
from shelfwise.db import Database            # noqa: E402

TABLES = ["users", "categories", "suppliers", "products", "sales", "waste_records", "stock_movements"]


def sql_value(value):
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


db = Database(seed.settings_from_config())
lines = ["-- ShelfWise sample data (MADE-UP, for testing and the viva only)",
         "-- Run shelfwise_mysql.sql first, then this file.",
         "-- Demo logins: manager@shelfwise.test / Manager123!   staff@shelfwise.test / Staff123!",
         "USE shelfwise;", "SET FOREIGN_KEY_CHECKS = 0;", ""]
for table in TABLES:
    rows = db.all(f"SELECT * FROM {table}")
    lines.append(f"-- {table}: {len(rows)} rows")
    for row in rows:
        columns = ", ".join(row.keys())
        values = ", ".join(sql_value(v) for v in row.values())
        lines.append(f"INSERT INTO {table} ({columns}) VALUES ({values});")
    lines.append("")
lines.append("SET FOREIGN_KEY_CHECKS = 1;")
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "shelfwise_sample_data.sql")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("Wrote", path)
