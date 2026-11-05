"""ShelfWise - "Know your shelves."
Smart Inventory and Sales Management System for Small Businesses.
"""
from datetime import datetime

from flask import Flask, render_template

import config

from . import auth, db, routes


def create_app(settings=None):
    app = Flask(__name__)
    # Read settings from config.py, then apply any test settings on top
    for key in ("DB_ENGINE", "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD",
                "MYSQL_DATABASE", "SQLITE_FILE", "SECRET_KEY"):
        app.config[key] = getattr(config, key)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    if settings:
        app.config.update(settings)

    app.teardown_appcontext(db.close_db)
    app.register_blueprint(auth.bp)
    app.register_blueprint(routes.bp)
    app.jinja_env.globals["csrf_token"] = auth.csrf_token

    @app.template_filter("money")
    def money(value):
        return f"£{(value or 0):,.2f}"

    @app.template_filter("short_date")
    def short_date(value):
        """Show dates the British way: 22 Oct 2026 17:34 (or 22 Oct 2026 when there is no time)."""
        text = str(value or "")
        try:
            when = datetime.fromisoformat(text[:19])
        except ValueError:
            return text[:16]
        return when.strftime("%d %b %Y %H:%M") if len(text) > 10 else when.strftime("%d %b %Y")

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", code=400, message=error.description), 400

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="Only managers can open this page."), 403

    @app.errorhandler(500)
    def server_error(error):
        # Show a helpful message instead of a blank "Internal Server Error" page.
        original = getattr(error, "original_exception", None) or error
        app.logger.error("ShelfWise error: %s", original)
        return render_template("error.html", code=500,
                               message="Something went wrong: " + str(original) +
                                       ". Look at the black window for details. If it mentions a missing table "
                                       "or column, close the window and start ShelfWise again so it can fix "
                                       "the database."), 500

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="Page not found."), 404

    return app
