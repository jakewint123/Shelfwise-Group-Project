"""Start file for hosting ShelfWise online (for example on Render).

Render runs:   gunicorn wsgi:app
By default it uses SQLite, because Render's free plan has no MySQL. If the
database is empty (a new or restarted server), the made-up demo data is created.
To use a MySQL server instead, set SHELFWISE_DB_ENGINE=mysql and the
SHELFWISE_MYSQL_* settings in Render's Environment page.
"""
import os

os.environ.setdefault("SHELFWISE_DB_ENGINE", "sqlite")

import seed                                                    # noqa: E402
from shelfwise import create_app                               # noqa: E402
from shelfwise.db import Database, add_reset_table, settings_from, table_names   # noqa: E402

app = create_app()
settings = settings_from(app)
if settings["DB_ENGINE"] == "sqlite":
    os.makedirs(os.path.dirname(os.path.abspath(settings["SQLITE_FILE"])), exist_ok=True)

try:
    db = Database(settings)
    empty = not table_names(db)
    if not empty:
        add_reset_table(db)
    db.close()
except Exception:                                              # database does not exist yet
    empty = True

if empty:
    print("ShelfWise: creating the database with made-up demo data...", flush=True)
    seed.seed(settings, quiet=True)
