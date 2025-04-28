import os
import logging
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
    get_user_automation
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

# ─── Force DB Init ──────────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

# Seed admin if configured
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Analytics helper ────────────────────────────────────────────────────────
def log_event(user_email: str, event_type: str):
    conn = get_db_connection()
    # look up the user’s integer id
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?",
        (user_email,)
    ).fetchone()
    if row:
        user_id = row["id"]
        conn.execute(
            "INSERT INTO analytics_events (user_id, event_type) VALUES (?, ?)",
            (user_id, event_type)
        )
        conn.commit()
    conn.close()

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
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


@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    log_event(session['email'], 'pageview')

    first_name          = session.get('first_name', 'there')
    plan_status         = session.get('plan_status', 'free')
    automation          = get_user_automation(session['email'])
    automation_complete = bool(automation)

    return render_template(
        'dashboard.html',
        first_name=first_name,
        plan_status=plan_status,
        automation=automation,
        automation_complete=automation_complete
    )


# ─── Automation setup ────────────────────────────────────────────────────────
@app.route('/automation', methods=['GET', 'POST'])
def automation_page():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # grab form data and save
        tone, style, notes = (
            request.form.get('tone'),
            request.form.get('style'),
            request.form.get('additional_notes'),
        )
        conn = get_db_connection()
        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?",
            (session['email'],)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE automation_settings "
                "SET tone=?, style=?, additional_notes=? WHERE email=?",
                (tone, style, notes, session['email'])
            )
        else:
            conn.execute(
                "INSERT INTO automation_settings (email, tone, style, additional_notes) "
                "VALUES (?, ?, ?, ?)",
                (session['email'], tone, style, notes)
            )
        conn.commit()
        conn.close()

        log_event(session['email'], 'saved_automation')
        return redirect(url_for('dashboard'))

    # GET → render the “set up automation” form
    automation = get_user_automation(session['email']) or {}
    return render_template(
        'automation.html',
        automation=automation
    )


@app.route('/memberships', methods=['GET', 'POST'])
def memberships():
    if request.method == 'POST':
        if not request.form.get('terms'):
            flash("You must agree to the Terms of Service.", "error")
            return redirect(url_for('memberships'))

        price_id = os.getenv("SECRET_BUNDLE_PRICE_ID")
        if not price_id:
            flash("Payment configuration missing. Try again later.", "error")
            return redirect(url_for('memberships'))

        try:
            session_obj = stripe.checkout.Session.create(
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=url_for('dashboard', _external=True),
                cancel_url=url_for('memberships', _external=True),
            )
            return redirect(session_obj.url, code=303)
        except Exception as e:
            logger.exception("Stripe checkout creation failed: %s", e)
            flash("Could not start payment. Please try again.", "error")
            return redirect(url_for('memberships'))

    return render_template('memberships.html')


# … rest of your routes remain untouched …


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
