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
stripe.api_key     = os.getenv("STRIPE_SECRET_KEY")
openai.api_key     = os.getenv("OPENAI_API_KEY")
PERSONAL_EMAIL     = os.getenv("PERSONAL_EMAIL")
ADMIN_EMAIL        = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD     = os.getenv("ADMIN_PASSWORD")

# ─── Flask Setup ────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

# ─── Init + Migrations ───────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()
# add stripe_customer_id if missing
conn = get_db_connection()
try:
    conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass
conn.close()

# seed admin
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Public endpoints that don’t require login ──────────────────────────────
PUBLIC_ENDPOINTS = {
    'home', 'login', 'terms', 'ping', 'static', 'stripe_webhook'
}

@app.before_request
def require_login():
    if request.endpoint not in PUBLIC_ENDPOINTS and 'email' not in session:
        return redirect(url_for('login'))

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['email']       = email
            session['first_name']  = user['first_name']
            session['plan_status'] = user['plan_status']
            return redirect(url_for('dashboard'))

        flash('Invalid email or password', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    # now guaranteed logged in
    conn = get_db_connection()
    row = conn.execute(
        "SELECT plan_status, first_name FROM users WHERE email = ?",
        (session['email'],)
    ).fetchone()
    session['plan_status'] = row['plan_status']
    first = row['first_name']
    conn.close()

    log_event(session['email'], 'pageview')
    return render_template(
      'dashboard.html',
      first_name         = first,
      plan_status        = session['plan_status'],
      automation         = get_user_automation(session['email']),
      automation_complete= bool(get_user_automation(session['email']))
    )

# … your other pro-protected routes (memberships, analytics, automation, proposal, webhook, etc.)
# follow the same pattern: they’ll automatically redirect to /login if not logged in.

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/ping')
def ping():
    return "pong"

if __name__ == '__main__':
    app.run(host='0.0.0.0',
            port=int(os.getenv('PORT', 5001)),
            debug=True)
