import os
import logging
import sqlite3

from flask import (
    Flask, render_template, request,
    redirect, url_for, session,
    flash, jsonify
)
from dotenv import load_dotenv
import openai
import stripe

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table,
    create_analytics_events_table,
    get_user_automation,
    log_event
)
from email_utils import send_proposal_email
from datetime import datetime, timedelta

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Config ─────────────────────────────────────────────────────────────────
load_dotenv()
stripe.api_key            = os.getenv("STRIPE_SECRET_KEY")
openai.api_key            = os.getenv("OPENAI_API_KEY")
PERSONAL_EMAIL            = os.getenv("PERSONAL_EMAIL")
ADMIN_EMAIL               = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD            = os.getenv("ADMIN_PASSWORD")
SECRET_BUNDLE_PRICE_ID    = os.getenv("SECRET_BUNDLE_PRICE_ID")
STRIPE_WEBHOOK_SECRET     = os.getenv("STRIPE_WEBHOOK_SECRET")

# ─── Flask Setup ───────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret")

# ─── DB Init + Migration ─────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()
# add stripe_customer_id column if not already there
conn = get_db_connection()
try:
    conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass
conn.close()

# ─── Seed Admin ─────────────────────────────────────────────────────────────
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status)"
        " VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Require Login ──────────────────────────────────────────────────────────
PUBLIC_PATHS = {"/", "/login", "/terms", "/ping"}
@app.before_request
def require_login():
    # allow static files
    if request.path.startswith("/static/"):
        return
    # allow explicitly public endpoints
    if request.path in PUBLIC_PATHS:
        return
    # otherwise force login
    if "email" not in session:
        return redirect(url_for("login"))

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]
        conn     = get_db_connection()
        user     = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and user["password"] == password:
            session["email"]       = email
            session["first_name"]  = user["first_name"]
            session["plan_status"] = user["plan_status"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password", "error")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/ping")
def ping():
    return "pong"

@app.route("/dashboard")
def dashboard():
    # now guaranteed logged-in
    conn = get_db_connection()
    row  = conn.execute(
        "SELECT first_name, plan_status FROM users WHERE email = ?",
        (session["email"],)
    ).fetchone()
    conn.close()

    session["plan_status"] = row["plan_status"]
    log_event(session["email"], "pageview")

    return render_template(
        "dashboard.html",
        first_name          = row["first_name"],
        plan_status         = row["plan_status"],
        automation          = get_user_automation(session["email"]),
        automation_complete = bool(get_user_automation(session["email"]))
    )

@app.route("/analytics")
def analytics():
    # **Removed** subscription gating — only login is required now
    conn = get_db_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for("dashboard"))
    user_id = user["id"]

    # Totals
    pageviews   = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'pageview'",
        (user_id,)
    ).fetchone()["cnt"]
    generated   = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'generated_proposal'",
        (user_id,)
    ).fetchone()["cnt"]
    sent        = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'sent_proposal'",
        (user_id,)
    ).fetchone()["cnt"]
    conversion_rate = (sent / generated * 100) if generated else 0

    # Last 7 days
    today = datetime.utcnow().date()
    dates = [today - timedelta(days=i) for i in reversed(range(7))]
    labels = [d.strftime("%b %-d") for d in dates]

    pv_data, gen_data, sent_data = [], [], []
    for d in dates:
        pv = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'pageview' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]
        gp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'generated_proposal' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]
        sp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'sent_proposal' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]
        pv_data.append(pv)
        gen_data.append(gp)
        sent_data.append(sp)

    conn.close()

    return render_template(
        "analytics.html",
        pageviews       = pageviews,
        generated       = generated,
        sent            = sent,
        conversion_rate = round(conversion_rate, 1),
        line_labels     = labels,
        line_data       = pv_data,
        generated_data  = gen_data,
        sent_data       = sent_data
    )

# …your other routes (memberships, automation, proposal, webhook) stay as you already have them…

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=True)
