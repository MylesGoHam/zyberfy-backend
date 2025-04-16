from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from dotenv import load_dotenv
import os
import sqlite3
import stripe

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Stripe API Key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Stripe Price IDs
PRICE_IDS = {
    'starter': 'price_1REQ6RKpgIhBPea4EMSakXdq',
    'pro': 'price_1REQ73KpgIhBPea4lcMQPz65',
    'elite': 'price_1REQ7RKpgIhBPea4NnXjzTMN'
}

# DB Connection
def get_db_connection():
    db_path = os.environ.get("ZDB_PATH", os.path.join(os.path.abspath(os.path.dirname(__file__)), "zyberfy.db"))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

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
    data = request.get_json()
    plan = data.get('plan')

    if plan not in PRICE_IDS:
        return jsonify({'error': 'Invalid plan'}), 400

    try:
        session_obj = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': PRICE_IDS[plan],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('memberships', _external=True),
            metadata={
                'plan': plan,
                'user_email': session.get('email', 'guest')
            }
        )
        return jsonify({'url': session_obj.url})
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/success')
def success():
    return render_template('success.html')  # You can create a proper thank you page
