from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from dotenv import load_dotenv
import os
import sqlite3
import stripe

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Stripe config
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Pricing plan Stripe IDs
PRICE_IDS = {
    'starter': 'price_1REQ6RKpgIhBPea4EMSakXdq',
    'pro': 'price_1REQ73KpgIhBPea4lcMQPz65',
    'elite': 'price_1REQ7RKpgIhBPea4NnXjzTMN'
}

def get_db_connection():
    db_path = os.environ.get("ZDB_PATH", os.path.join(os.path.abspath(os.path.dirname(__file__)), "zyberfy.db"))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

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
    return render_template('dashboard.html', email=session['email'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/memberships')
def memberships():
    return render_template('memberships.html')

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    price_id = request.form.get('price_id')
    if not price_id:
        return "Missing price ID", 400

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

@app.route("/webhook", methods=["POST"])
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
        price_id = session_obj.get("items", {}).get("data", [{}])[0].get("price", {}).get("id", "unknown")

        # TODO: Save subscription info to DB here
        print(f"✅ Checkout complete: {customer_email} subscribed to {price_id} (sub_id: {subscription_id})")

    return jsonify(success=True)

if __name__ == '__main__':
    app.run(debug=True)
