"""Sign in, sign out, forgot password, roles (manager / staff) and form protection (CSRF)."""
import functools
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)


def hash_password(password):
    return generate_password_hash(password)


@bp.before_app_request
def load_user():
    """Before every page: find out who is signed in."""
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = get_db().one("SELECT * FROM users WHERE user_id = %s AND is_active = 1", (user_id,))
        if g.user is None:
            session.clear()


@bp.before_app_request
def check_form_token():
    """Every form must send back the secret token we gave it. This stops fake forms from other sites."""
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(sent, expected):
            abort(400, description="This form has expired. Please go back, refresh the page and try again.")


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            flash("Please sign in first.", "warning")
            return redirect(url_for("auth.login"))
        return view(**kwargs)
    return wrapped


def manager_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(**kwargs):
        if g.user["role"] != "manager":
            abort(403)
        return view(**kwargs)
    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().one("SELECT * FROM users WHERE email = %s AND is_active = 1", (email,))
        if user and check_password_hash(user["password_hash"], password):
            token = session.get("csrf_token") or secrets.token_hex(16)
            session.clear()
            session["user_id"] = user["user_id"]
            session["csrf_token"] = token
            flash(f"Welcome, {user['full_name']}.", "success")
            return redirect(url_for("main.dashboard"))
        flash("Email or password is wrong.", "error")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("auth.login"))


# ------------------------------------------------------------------ forgot password
# ShelfWise runs on the shop's own computer and has no email server, so the
# 6-digit reset code is shown in the black ShelfWise window on that computer.
# Only a hash of the code is saved. It works once, for 15 minutes, with 5 tries.
CODE_MINUTES = 15
MAX_TRIES = 5


def make_code():
    return f"{secrets.randbelow(1000000):06d}"


def strong_enough(password):
    return len(password) >= 8 and not password.isalpha() and not password.isdigit()


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        db = get_db()
        user = db.one("SELECT * FROM users WHERE email = %s AND is_active = 1", (email,))
        if user:
            code = make_code()
            now = datetime.now()
            # Cancel any older codes, then save the new one
            db.run("UPDATE password_resets SET used = 1 WHERE user_id = %s AND used = 0", (user["user_id"],))
            db.run("INSERT INTO password_resets (user_id, code_hash, expires_at, created_at) VALUES (%s, %s, %s, %s)",
                   (user["user_id"], generate_password_hash(code),
                    (now + timedelta(minutes=CODE_MINUTES)).strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")))
            db.commit()
            print("\n" + "=" * 60)
            print(f"  PASSWORD RESET CODE for {email}: {code}")
            print(f"  It works once and expires in {CODE_MINUTES} minutes.")
            print("=" * 60 + "\n", flush=True)
        # Same message whether or not the email exists, so nobody can test which emails are real
        flash("If that email belongs to an account, a 6-digit reset code is now shown in the black "
              "ShelfWise window on the shop computer. Ask the manager if you cannot see it.", "success")
        return redirect(url_for("auth.reset", email=email))
    return render_template("forgot.html")


@bp.route("/reset", methods=["GET", "POST"])
def reset():
    email = request.values.get("email", "").strip().lower()
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        db = get_db()
        user = db.one("SELECT * FROM users WHERE email = %s AND is_active = 1", (email,))
        row = None
        if user:
            row = db.one("SELECT * FROM password_resets WHERE user_id = %s AND used = 0 "
                         "ORDER BY reset_id DESC LIMIT 1", (user["user_id"],))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if password != confirm:
            flash("The two new passwords do not match.", "error")
        elif not strong_enough(password):
            flash("New password must be at least 8 characters with letters and numbers.", "error")
        elif row is None or str(row["expires_at"]) < now or row["attempts"] >= MAX_TRIES:
            flash("This code has expired or is not valid. Please ask for a new code.", "error")
        elif not check_password_hash(row["code_hash"], code):
            db.run("UPDATE password_resets SET attempts = attempts + 1 WHERE reset_id = %s", (row["reset_id"],))
            db.commit()
            left = MAX_TRIES - row["attempts"] - 1
            flash(f"Wrong code. {left} tries left." if left else "Wrong code. Please ask for a new code.", "error")
        else:
            db.run("UPDATE users SET password_hash = %s WHERE user_id = %s",
                   (generate_password_hash(password), user["user_id"]))
            db.run("UPDATE password_resets SET used = 1 WHERE reset_id = %s", (row["reset_id"],))
            db.commit()
            flash("Password changed. Please sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
    return render_template("reset.html", email=email)
