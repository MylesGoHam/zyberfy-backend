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

# Routes
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

@app.route('/onboarding', methods=['GET', 'POST'])
def onboarding():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        business_name = request.form.get('business_name')
        business_type = request.form.get('business_type')
        email = session.get('email')

        if email:
            conn = get_db_connection()
            conn.execute(
                """
                UPDATE subscriptions
                SET first_name = ?, last_name = ?, business_name = ?, business_type = ?
                WHERE email = ?
                """,
                (first_name, last_name, business_name, business_type, email)
            )
            conn.commit()
            conn.close()
            return redirect(url_for('dashboard'))
        
        return redirect(url_for('login'))
    
    return render_template('onboarding.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    user_info = conn.execute(
        "SELECT stripe_subscription_id, first_name FROM subscriptions WHERE email = ?", 
        (session['email'],)
    ).fetchone()

    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", 
        (session['email'],)
    ).fetchone()

    conn.close()

    automation_complete = bool(automation)

    plan_status = "Free"
    first_name = "User"

    if user_info:
        if user_info["stripe_subscription_id"]:
            plan_status = "Active Subscription"
        if user_info["first_name"]:
            first_name = user_info["first_name"]

    return render_template('dashboard.html', 
        email=session['email'], 
        plan_status=plan_status, 
        automation_complete=automation_complete, 
        first_name=first_name
    )

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
    saved = request.args.get('saved')
    return render_template('automation.html', saved=saved)

@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return redirect(url_for('login'))

    tone = request.form.get('tone')
    style = request.form.get('style')
    additional_notes = request.form.get('additional_notes')
    enable_follow_up = request.form.get('enable_follow_up')
    number_of_followups = request.form.get('number_of_followups')
    followup_delay = request.form.get('followup_delay')
    followup_style = request.form.get('followup_style')
    minimum_offer = request.form.get('minimum_offer')
    acceptance_message = request.form.get('acceptance_message')
    decline_message = request.form.get('decline_message')

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO automation_settings (
            email, tone, style, additional_notes,
            enable_follow_up, number_of_followups, followup_delay, followup_style,
            minimum_offer, acceptance_message, decline_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            tone = excluded.tone,
            style = excluded.style,
            additional_notes = excluded.additional_notes,
            enable_follow_up = excluded.enable_follow_up,
            number_of_followups = excluded.number_of_followups,
            followup_delay = excluded.followup_delay,
            followup_style = excluded.followup_style,
            minimum_offer = excluded.minimum_offer,
            acceptance_message = excluded.acceptance_message,
            decline_message = excluded.decline_message
    """, (
        session['email'], tone, style, additional_notes,
        enable_follow_up, number_of_followups, followup_delay, followup_style,
        minimum_offer, acceptance_message, decline_message
    ))
    conn.commit()
    conn.close()

    return redirect(url_for('automation', saved='true'))

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
            conn.execute("""
                INSERT INTO subscriptions (email, stripe_subscription_id) 
                VALUES (?, ?) 
                ON CONFLICT(email) DO UPDATE SET stripe_subscription_id = ?
            """, (customer_email, subscription_id, subscription_id))
            conn.commit()
            conn.close()

    return jsonify(success=True)

if __name__ == '__main__':
    app.run(debug=True)
