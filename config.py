"""ShelfWise settings - change these to match your computer.

XAMPP default MySQL login is user "root" with NO password.
If MySQL is not installed, change DB_ENGINE to "sqlite" and it will
work without any database server.
"""
import os

DB_ENGINE = os.environ.get("SHELFWISE_DB_ENGINE", "mysql")   # "mysql" or "sqlite"

MYSQL_HOST = os.environ.get("SHELFWISE_MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("SHELFWISE_MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("SHELFWISE_MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("SHELFWISE_MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("SHELFWISE_MYSQL_DATABASE", "shelfwise")

SQLITE_FILE = os.environ.get("SHELFWISE_SQLITE_FILE", os.path.join("instance", "shelfwise.sqlite"))

# Used to protect sign-in sessions. Change it before using the app for real.
SECRET_KEY = os.environ.get("SHELFWISE_SECRET_KEY", "change-this-to-a-long-random-text")
