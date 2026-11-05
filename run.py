"""Start ShelfWise and open it in your web browser.

    python run.py

Do NOT open the .html files in shelfwise/templates directly.
They only work when this program is running.
"""
import getpass
import json
import os
import re
import threading
import webbrowser

import config
from shelfwise import create_app
from shelfwise.db import Database, add_reset_table, missing_parts, rename_old_tables, settings_from, table_names

URL = "http://127.0.0.1:5000"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
app = create_app()


def error_code(error):
    """MySQL errors carry a number, e.g. 1045 = wrong password."""
    return error.args[0] if error.args and isinstance(error.args[0], int) else None


def save_setting(name, value):
    """Write a new value into config.py so it is remembered next time."""
    with open(CONFIG_FILE, encoding="utf-8") as f:
        text = f.read()
    pattern = rf'^({name} = os\.environ\.get\("[A-Z_]+", )"(?:[^"\\\n]|\\.)*"(\))'
    text = re.sub(pattern, lambda m: m.group(1) + json.dumps(value) + m.group(2), text, flags=re.M)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(text)


def ask_for_password():
    """MySQL said the password is wrong: ask for it, try it, and save it if it works."""
    print("\nMySQL is running, but it needs a password for user '%s'." % app.config["MYSQL_USER"])
    print("Type your MySQL password and press Enter (the typing is hidden).")
    print("Or type  sqlite  to use the built-in database instead.")
    for attempt in range(3):
        try:
            answer = getpass.getpass("MySQL password: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer.strip().lower() == "sqlite":
            app.config["DB_ENGINE"] = "sqlite"
            save_setting("DB_ENGINE", "sqlite")
            print("Switched to SQLite. This is saved in config.py.")
            return True
        app.config["MYSQL_PASSWORD"] = answer
        try:
            Database(settings_from(app)).close()
        except Exception as error:
            if error_code(error) == 1049:     # password right, database not created yet
                pass
            elif error_code(error) == 1045:
                print("That password did not work. Please try again.")
                continue
            else:
                print("Could not connect:", error)
                return False
        save_setting("MYSQL_PASSWORD", answer)
        print("Password accepted and saved in config.py.")
        return True
    print("Three wrong passwords. Check your MySQL password, or type sqlite next time.")
    return False


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def old_database(problems):
    """The database exists but its tables are not ShelfWise's (e.g. an older version). Ask what to do."""
    name = app.config["MYSQL_DATABASE"] if app.config["DB_ENGINE"] == "mysql" else "the SQLite file"
    print(f"\nThe database '{name}' already has tables that do not match ShelfWise.")
    print("Missing or different tables:", ", ".join(problems))
    print("This usually means it was made by an older version of the project.\n")
    print("  Type YES  to delete the old tables and create the new ShelfWise tables with demo data.")
    if app.config["DB_ENGINE"] == "mysql":
        print("  Type NEW  to keep the old database and use a separate one called shelfwise_app.")
    print("  Press Enter to stop without changing anything.")
    answer = ask("Your choice: ").upper()
    if answer == "YES":
        import seed
        print("Creating the new ShelfWise tables with made-up demo data...")
        seed.seed(settings_from(app), fresh_database=True)
        return "ready"
    if answer == "NEW" and app.config["DB_ENGINE"] == "mysql":
        app.config["MYSQL_DATABASE"] = "shelfwise_app"
        save_setting("MYSQL_DATABASE", "shelfwise_app")
        print("OK - using the database 'shelfwise_app' (saved in config.py).")
        return "try again"
    print("Nothing was changed.")
    return "stop"


def database_ready():
    """Check the database is reachable and has the right tables. Create demo data on the first run."""
    message = ""
    for _ in range(3):
        try:
            db = Database(settings_from(app))
            rename_old_tables(db)    # write_offs -> waste_records (older databases)
            problems = missing_parts(db)
            empty = not table_names(db)
            if not problems:
                add_reset_table(db)      # new table for "Forgot password?" (older databases)
            db.close()
        except Exception as error:
            message, code = str(error), error_code(error)
            if code == 1045 and ask_for_password():          # wrong or missing password
                continue
            if code == 1049:                                  # database does not exist yet
                import seed
                print("First run: creating the ShelfWise database with made-up demo data...")
                seed.seed(settings_from(app))
                return True
            break
        if not problems:
            return True
        if empty:                                             # empty database: first run
            import seed
            print("First run: creating the ShelfWise tables with made-up demo data...")
            seed.seed(settings_from(app))
            return True
        result = old_database(problems)                       # old or different tables
        if result == "ready":
            return True
        if result == "try again":
            continue
        return False
    print("\nCould not connect to the database:", message)
    if app.config["DB_ENGINE"] == "mysql":
        print("1. Start MySQL (XAMPP Control Panel: press Start next to MySQL).\n"
              "2. Check the user name and password in config.py.\n"
              "3. No MySQL? Open config.py and change DB_ENGINE to \"sqlite\".")
    return False


if __name__ == "__main__":
    if database_ready():
        print(f"\nShelfWise is running - Know your shelves. Open {URL}")
        print("Manager: manager@shelfwise.test / Manager123!")
        print("Staff:   staff@shelfwise.test / Staff123!")
        print("Press Ctrl+C to stop.\n")
        if os.environ.get("SHELFWISE_NO_BROWSER") != "1":
            threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
        app.run(debug=os.environ.get("FLASK_DEBUG") == "1", use_reloader=False)
