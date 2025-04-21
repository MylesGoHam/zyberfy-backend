import os
import sqlite3
import logging
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from dotenv import load_dotenv
import openai
import stripe

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table
)
from email_utils import send_proposal_email

# ─── Config ───────────────────────────────────────────────────────────────────
load_dotenv()
stripe.api_key   = os.getenv("STRIPE_SECRET_KEY")
openai.api_key   = os.getenv("OPENAI_API_KEY")
PERSONAL_EMAIL   = os.getenv("PERSONAL_EMAIL")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

# ─── DB Init ───────────────────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()

ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/memberships', methods=['GET', 'POST'])
def memberships():
    # allow both logged‑in and new users to see/join this page
    if request.method == 'POST':
        # 1) Extract form inputs
        first_name = request.form.get('first_name', '').strip()
        email      = request.form.get('email', '').strip()
        password   = request.form.get('password', '').strip()
        plan       = request.form.get('plan', 'bundle')

        if not first_name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for('memberships'))

        # 2) Persist user (if not already there)
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (email, password, first_name, plan_status) VALUES (?, ?, ?, ?)",
                (email, password, first_name, plan)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # user already exists—ok to proceed to checkout
            flash("Welcome back! Continuing to checkout…", "info")
        finally:
            conn.close()

        # store in session so post‑payment you know who’s logged in
        session['email'] = email

        # 3) Prepare Stripe checkout
        price_id = os.getenv("SECRET_BUNDLE_PRICE_ID")
        if not price_id:
            flash("Payment configuration missing. Please try again later.", "error")
            return redirect(url_for('memberships'))

        try:
            checkout_session = stripe.checkout.Session.create(
                customer_email=email,
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=url_for('dashboard', _external=True),
                cancel_url=url_for('memberships', _external=True),
            )
        except Exception as e:
            logger.exception("Stripe checkout creation failed")
            flash("Could not start payment. Please try again later.", "error")
            return redirect(url_for('memberships'))

        # 4) Redirect user into Stripe's checkout flow
        return redirect(checkout_session.url, code=303)

    # GET → render the signup/checkout page
    return render_template('memberships.html')


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
            session['email'] = email
            return redirect(url_for('dashboard'))

        flash('Invalid email or password', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (session['email'],)
    ).fetchone()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()

    return render_template(
        'dashboard.html',
        first_name=user['first_name'] if user else '',
        plan_status=user['plan_status'] if user else 'None',
        automation=automation,
        automation_complete=automation is not None
    )


@app.route('/automation')
def automation_page():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()
    return render_template('automation.html', automation=automation)


@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return jsonify(success=False, error='Unauthorized'), 403

    tone, style, notes = (
        request.form.get('tone'),
        request.form.get('style'),
        request.form.get('additional_notes'),
    )

    conn = get_db_connection()
    if conn.execute(
        "SELECT 1 FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone():
        conn.execute(
            "UPDATE automation_settings SET tone=?, style=?, additional_notes=? WHERE email=?",
            (tone, style, notes, session['email'])
        )
    else:
        conn.execute(
            "INSERT INTO automation_settings (email, tone, style, additional_notes) VALUES (?, ?, ?, ?)",
            (session['email'], tone, style, notes)
        )
    conn.commit()
    conn.close()
    return jsonify(success=True)


@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify(success=False, error='Unauthorized'), 403

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()

    if not automation:
        return jsonify(success=False, error='No automation settings found'), 400

    prompt = (
        f"Write a concise business proposal email in a {automation['tone']} tone "
        f"and {automation['style']} style.\n\nExtra notes: {automation['additional_notes'] or 'none'}"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant writing business proposals."},
                {"role": "user",   "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        proposal = resp.choices[0].message.content.strip()
        return jsonify(success=True, proposal=proposal)
    except Exception:
        logger.exception("OpenAI failure; using dummy.")
        fallback = (
            f"Hi there,\n\nThanks for reaching out! "
            f"We'd love to assist you with a {automation['tone']} and {automation['style']} proposal.\n\n"
            f"{automation['additional_notes'] or ''}\n\nBest regards,\nThe Zyberfy Team"
        )
        return jsonify(success=True, proposal=fallback, fallback=True)


@app.route('/proposal', methods=['GET', 'POST'])
def proposal():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        lead_name  = request.form['name']
        lead_email = PERSONAL_EMAIL or request.form['email']
        budget     = request.form['budget']

        conn = get_db_connection()
        automation = conn.execute(
            "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
        ).fetchone()
        conn.close()

        prompt = (
            f"Write a business proposal email to {lead_name}, budget ${budget}, "
            f"in a {automation['tone']} tone and {automation['style']} style. "
            f"Notes: {automation['additional_notes'] or 'none'}"
        )
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant writing business proposals."},
                    {"role": "user",   "content": prompt}
                ],
                max_tokens=350,
                temperature=0.7
            )
            email_body = resp.choices[0].message.content.strip()
        except Exception as e:
            flash(f"Error generating proposal: {e}", "error")
            return redirect(url_for('proposal'))

        subject = f"Proposal for {lead_name} (Budget: ${budget})"
        resp_obj = send_proposal_email(
            to_email=lead_email,
            subject=subject,
            content=email_body,
            cc_client=False
        )
        status_code = getattr(resp_obj, 'status_code', resp_obj)
        if 200 <= status_code < 300:
            flash(f"✅ Proposal sent to {lead_email}", "success")
            return render_template('thank_you.html')
        flash("❌ Failed to send proposal email.", "error")
        return redirect(url_for('proposal'))

    return render_template('proposal.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
