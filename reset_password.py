"""Rescue tool: set a new password for any ShelfWise account.

Use this if nobody can sign in (for example the manager forgot the password).
It must be run on the shop computer, because it talks to the database directly.

    python reset_password.py

It shows every account, you pick one by number and type a new password.
The account is also switched back on, in case it was switched off.
"""
import getpass

from werkzeug.security import generate_password_hash

import config
from shelfwise.auth import strong_enough
from shelfwise.db import Database

SETTINGS = {name: getattr(config, name) for name in
            ["DB_ENGINE", "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "SQLITE_FILE"]}


def choose_user(users):
    print("\nShelfWise accounts:")
    for number, user in enumerate(users, start=1):
        status = "" if user["is_active"] else "   (switched off)"
        print(f"  {number}. {user['full_name']:<22} {user['email']:<30} {user['role']}{status}")
    while True:
        answer = input("\nType the number of the account to reset (or press Enter to stop): ").strip()
        if answer == "":
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(users):
            return users[int(answer) - 1]
        print("Please type one of the numbers above.")


def ask_new_password():
    print("\nNew password: at least 8 characters, with letters AND numbers.")
    print("(Nothing appears on screen while you type. That is normal.)")
    while True:
        first = getpass.getpass("New password: ")
        second = getpass.getpass("Type it again: ")
        if first != second:
            print("The two passwords do not match. Try again.\n")
        elif not strong_enough(first):
            print("Too weak: use at least 8 characters with letters and numbers.\n")
        else:
            return first


def main():
    try:
        db = Database(SETTINGS)
        users = db.all("SELECT user_id, full_name, email, role, is_active FROM users ORDER BY user_id")
    except Exception as error:
        print("\nCould not open the ShelfWise database:")
        print("  ", error)
        if "2003" in str(error):
            print("MySQL is not running. Open XAMPP and click Start next to MySQL, then try again.")
        else:
            print("Start ShelfWise once (START_SHELFWISE) so it can save your MySQL password, then try again.")
        return
    if not users:
        print("\nThere are no accounts yet. Run:  python seed.py")
        return
    user = choose_user(users)
    if user is None:
        print("Nothing changed.")
        return
    password = ask_new_password()
    db.run("UPDATE users SET password_hash = %s, is_active = 1 WHERE user_id = %s",
           (generate_password_hash(password), user["user_id"]))
    db.commit()
    db.close()
    print("\nDone. Sign in with:")
    print("   Email:   ", user["email"])
    print("   Password: the one you just typed")


if __name__ == "__main__":
    main()
    input("\nPress Enter to close this window.")
