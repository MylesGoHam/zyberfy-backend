import os
import sqlite3
from flask import Flask, render_template, request, redirect, session, url_for
from dotenv import load_dotenv
import stripe
import openai
from models import create_automation_table

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Set Stripe secret key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Ensure automation_settings table exists on startup
create_automation_table()

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

@app.route('/automation', methods=['GET', 'POST'])
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    email = session['email']

    if request.method == 'POST':
        data = {
            'subject': request.form.get('subject'),
            'greeting': request.form.get('greeting'),
            'tone': request.form.get('tone'),
            'footer': request.form.get('footer'),
            'ai_training': request.form.get('ai_training'),
            'accept_msg': request.form.get('accept_msg'),
            'decline_msg': request.form.get('decline_msg'),
            'proposal_mode': request.form.get('proposal_mode')
        }

        conn.execute("""
            INSERT INTO automation_settings (email, subject, greeting, tone, footer, ai_training, accept_msg, decline_msg, proposal_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                subject=excluded.subject,
                greeting=excluded.greeting,
                tone=excluded.tone,
                footer=excluded.footer,
                ai_training=excluded.ai_training,
                accept_msg=excluded.accept_msg,
                decline_msg=excluded.decline_msg,
                proposal_mode=excluded.proposal_mode;
        """, (email, data['subject'], data['greeting'], data['tone'], data['footer'],
              data['ai_training'], data['accept_msg'], data['decline_msg'], data['proposal_mode']))
        conn.commit()

    settings = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (email,)).fetchone()
    conn.close()
    return render_template('automation.html', settings=settings)

@app.route('/subscribe', methods=['POST'])
def subscribe():
    plan = request.form.get('plan')
    return f"🛠️ Stripe subscription logic coming soon for plan: {plan}"

@app.route('/billing')
def billing():
    return render_template('billing.html')

@app.route('/memberships')
def memberships():
    plans = [
        {
            'name': 'Starter',
            'price': '$297/mo',
            'features': [
                'Up to 10 AI Proposals/month',
                'Basic Email Automation',
                'Email Support'
            ]
        },
        {
            'name': 'Pro',
            'price': '$597/mo',
            'features': [
                'Up to 30 AI Proposals/month',
                'Advanced Automation Settings',
                'Priority Support'
            ]
        },
        {
            'name': 'Elite',
            'price': '$1297/mo',
            'features': [
                'Unlimited Proposals',
                'Full White-Glove Setup',
                'Dedicated Account Manager'
            ]
        }
    ]
    return render_template('memberships.html', plans=plans)

@app.route('/test_proposal', methods=['GET'])
def test_proposal():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    email = session['email']
    settings = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (email,)).fetchone()
    conn.close()

    if not settings:
        return "⚠️ No automation settings found. Please save them first."

    prompt = f"""
Generate a sample email proposal using the following settings:
- Subject: {settings['subject']}
- Greeting: {settings['greeting']}
- Tone: {settings['tone']}
- Signature/Footer: {settings['footer']}
- Voice/Style Guidance: {settings['ai_training']}
- Use {'a concise' if settings['proposal_mode'] == 'concise' else 'a detailed'} format.

This is for a lead who just filled out a proposal form. Be persuasive, friendly, and aligned with the tone.
"""

    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.8
        )
        generated_email = response['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ OpenAI error: {e}"

    return render_template("test_proposal.html", settings=settings, generated_email=generated_email)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
