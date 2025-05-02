import os
import logging
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# ─── Flask Setup ───────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

# ─── DB Init + Migration ─────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()
# (…plus your stripe_customer_id migration…)

# Seed admin
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Require login on every route except these ───────────────────────────────
PUBLIC_PATHS = { "/", "/login", "/terms", "/ping", "/stripe_webhook", "/memberships" }
@app.before_request
def require_login():
    if request.path.startswith("/static/"):
        return
    if request.path in PUBLIC_PATHS:
        return
    if "email" not in session:
        return redirect(url_for("login"))

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        # …authenticate…
        session["email"] = user["email"]
        session["plan_status"] = user["plan_status"]
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    # guaranteed logged in
    conn = get_db_connection()
    row = conn.execute(
        "SELECT first_name, plan_status FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    conn.close()

    session["plan_status"] = row["plan_status"]
    log_event(session["email"], "pageview")

    return render_template(
        "dashboard.html",
        first_name=row["first_name"],
        plan_status=row["plan_status"],
        automation=get_user_automation(session["email"]),
        automation_complete=bool(get_user_automation(session["email"]))
    )

@app.route("/analytics")
def analytics():
    # only PRO users get here
    if session.get("plan_status") != "pro":
        flash("Analytics is a Pro feature—please subscribe.", "error")
        return redirect(url_for("memberships"))

    # …fetch counts & time-series…
    return render_template(
        "analytics.html",
        pageviews=pageviews,
        generated=generated,
        sent=conversions,
        conversion_rate=round(conversion_rate, 1),
        line_labels=line_labels,
        line_data=pageviews_data,
        generated_data=generated_data,
        sent_data=sent_data
    )

# …other routes (automation, memberships, webhook, etc.)…

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=True)
