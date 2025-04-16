from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from dotenv import load_dotenv
import os
import sqlite3
import stripe

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Add your actual price IDs here
PRICE_IDS = {
    'starter': 'price_1REQ6RKpgIhBPea4EMSakXdq',
    'pro': 'price_1REQ73KpgIhBPea4lcMQPz65',
    'elite': 'price_1REQ7RKpgIhBPea4NnXjzTMN'
}

# DB connection function
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

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (session['email'],)).fetchone()
    conn.close()

    return render_template('dashboard.html', email=session['email'], membership=user['membership'] if user else 'None')

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
            success_url=url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('memberships', _external=True),
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

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    if not session_id:
        return "Session ID missing.", 400

    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        customer_email = checkout_session.metadata.get('user_email')
        price_id = checkout_session['display_items'][0]['price']['id'] if 'display_items' in checkout_session else checkout_session['line_items']['data'][0]['price']['id']

        membership = next((tier for tier, id in PRICE_IDS.items() if id == price_id), None)

        if customer_email and membership:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO users (email, membership)
                VALUES (?, ?)
                ON CONFLICT(email) DO UPDATE SET membership=excluded.membership
            """, (customer_email, membership))
            conn.commit()
            conn.close()

            session['email'] = customer_email

            return redirect(url_for('dashboard'))
        else:
            return "Could not determine membership tier.", 400
    except Exception as e:
        return f"Stripe session error: {e}", 500

if __name__ == '__main__':
    app.run(debug=True)
