from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from dotenv import load_dotenv
import os
import sqlite3
import stripe
import openai
from models import create_automation_table, create_subscriptions_table, get_db_connection

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Connect to OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Stripe setup
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Price IDs
PRICE_IDS = {
    'starter': os.getenv("STRIPE_STARTER_PRICE_ID"),
    'pro': os.getenv("STRIPE_PRO_PRICE_ID"),
    'elite': os.getenv("STRIPE_ELITE_PRICE_ID"),
}

# Create tables
create_automation_table()
create_subscriptions_table()

# Home
@app.route('/')
def home():
    return render_template('index.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        session['email'] = email
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# Onboarding
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
            conn.execute("""
                UPDATE subscriptions
                SET first_name = ?, last_name = ?, business_name = ?, business_type = ?
                WHERE email = ?
            """, (first_name, last_name, business_name, business_type, email))
            conn.commit()
            conn.close()
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))
    return render_template('onboarding.html')

# Dashboard
@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    subscription = conn.execute("SELECT * FROM subscriptions WHERE email = ?", (session['email'],)).fetchone()
    automation = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (session['email'],)).fetchone()
    conn.close()

    automation_complete = bool(automation)

    first_name = None
    if subscription and subscription['first_name']:
        first_name = subscription['first_name']

    plan_status = "Free"
    if subscription and subscription['stripe_subscription_id']:
        plan_status = "Active Subscription"

    return render_template('dashboard.html', email=session['email'], plan_status=plan_status, automation_complete=automation_complete, first_name=first_name)

@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify(success=False, proposal="Please log in first."), 401

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", 
        (session['email'],)
    ).fetchone()
    conn.close()

    if not automation:
        return jsonify(success=False, proposal="No automation settings found."), 400

    tone = automation['tone'] or "Professional"
    style = automation['style'] or "Detailed"
    notes = automation['additional_notes'] or ""

    # Construct the prompt for OpenAI
    prompt = f"""Write a sample business proposal email.
- Tone: {tone}
- Style: {style}
- Notes: {notes if notes else "No extra notes"}

Make sure the proposal sounds realistic, professional, and helpful.
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert email writer specializing in personalized business proposals."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )

        proposal_text = response['choices'][0]['message']['content'].strip()

        return jsonify(success=True, proposal=proposal_text)
    except Exception as e:
        return jsonify(success=False, proposal=f"Error generating proposal: {str(e)}")

# Memberships
@app.route('/memberships')
def memberships():
    return render_template('memberships.html')

# Terms
@app.route('/terms')
def terms():
    return render_template('terms.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Automation Settings
@app.route('/automation')
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))
    saved = request.args.get('saved')
    return render_template('automation.html', saved=saved)

# Save Automation Settings
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

# Create Checkout Session
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

# Stripe Webhook
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

# Local run
if __name__ == '__main__':
    app.run(debug=True)
