from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from dotenv import load_dotenv
import os
import sqlite3
import stripe
from models import create_automation_table, create_subscriptions_table, get_db_connection

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Stripe setup
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Price IDs from .env
PRICE_IDS = {
    'starter': os.getenv("STRIPE_STARTER_PRICE_ID"),
    'pro': os.getenv("STRIPE_PRO_PRICE_ID"),
    'elite': os.getenv("STRIPE_ELITE_PRICE_ID"),
}

# Create tables
create_automation_table()
create_subscriptions_table()

# Routes (NOW it's safe to start routes after app is created)
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        session['email'] = email
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    subscription = conn.execute(
        "SELECT stripe_subscription_id FROM subscriptions WHERE email = ?", 
        (session['email'],)
    ).fetchone()

    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", 
        (session['email'],)
    ).fetchone()

    conn.close()

    automation_complete = bool(automation)

    plan_status = "Free"
    if subscription:
        plan_status = "Active Subscription"

    return render_template('dashboard.html', email=session['email'], plan_status=plan_status, automation_complete=automation_complete)

@app.route('/memberships')
def memberships():
    return render_template('memberships.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/automation')
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", 
        (session['email'],)
    ).fetchone()
    conn.close()

    tone = automation['tone'] if automation else ''
    style = automation['style'] if automation else ''
    additional_notes = automation['additional_notes'] if automation else ''

    return render_template('automation.html', tone=tone, style=style, additional_notes=additional_notes)

# UPDATED `/save-automation` route

@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return redirect(url_for('login'))

    tone = request.form.get('tone')
    style = request.form.get('style')
    follow_up = request.form.get('follow_up')
    auto_response = request.form.get('auto_response')
    additional_notes = request.form.get('additional_notes')
    custom_message = request.form.get('custom_message')

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO automation_settings 
            (email, tone, style, follow_up, auto_response, additional_notes, custom_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            tone = excluded.tone,
            style = excluded.style,
            follow_up = excluded.follow_up,
            auto_response = excluded.auto_response,
            additional_notes = excluded.additional_notes,
            custom_message = excluded.custom_message
    """, (session['email'], tone, style, follow_up, auto_response, additional_notes, custom_message))
    conn.commit()
    conn.close()

    return redirect(url_for('automation'))


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    plan = request.form.get('plan')
    price_id = PRICE_IDS.get(plan)

    if not price_id:
        return "Invalid or missing plan", 400

    try:
        checkout_session = stripe.checkout.Session.create(
            success_url=url_for('dashboard', _external=True) + '?success=true',
            cancel_url=url_for('memberships', _external=True) + '?canceled=true',
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            metadata={
                "user_email": session.get('email', 'guest')
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return f"Checkout failed: {e}", 500

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except ValueError:
        return jsonify(success=False, message="Invalid payload"), 400
    except stripe.error.SignatureVerificationError:
        return jsonify(success=False, message="Invalid signature"), 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        customer_email = session_obj.get("customer_email")
        subscription_id = session_obj.get("subscription")

        if customer_email and subscription_id:
            conn = get_db_connection()
            conn.execute(
                """
                INSERT INTO subscriptions (email, stripe_subscription_id) 
                VALUES (?, ?) 
                ON CONFLICT(email) DO UPDATE SET stripe_subscription_id = ?
                """,
                (customer_email, subscription_id, subscription_id)
            )
            conn.commit()
            conn.close()

    return jsonify(success=True)

# Only for local testing
if __name__ == '__main__':
    app.run(debug=True)
