from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from email_assistant import generate_reply
from dotenv import load_dotenv
import openai
import stripe
import posthog

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

DATABASE = "zyberfy.db"

# Initialize PostHog
posthog.project_api_key = os.getenv("POSTHOG_API_KEY")
posthog.host = 'https://app.posthog.com'

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Create subscriptions table if it doesn't exist
def create_subscriptions_table():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            stripe_subscription_id TEXT,
            price_id TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Create automation_settings table if it doesn't exist
def create_automation_table():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS automation_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            tone TEXT,
            subject TEXT,
            greeting TEXT,
            closing TEXT
        )
    ''')
    conn.commit()
    conn.close()

create_subscriptions_table()
create_automation_table()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['email'] = request.form['email']
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    automation = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (session['email'],)).fetchone()
    conn.close()
    return render_template('dashboard.html', automation=automation)

@app.route('/automation', methods=['GET', 'POST'])
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        tone = request.form['tone']
        subject = request.form['subject']
        greeting = request.form['greeting']
        closing = request.form['closing']
        existing = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (session['email'],)).fetchone()
        if existing:
            conn.execute('''
                UPDATE automation_settings
                SET tone = ?, subject = ?, greeting = ?, closing = ?
                WHERE email = ?
            ''', (tone, subject, greeting, closing, session['email']))
        else:
            conn.execute('''
                INSERT INTO automation_settings (email, tone, subject, greeting, closing)
                VALUES (?, ?, ?, ?, ?)
            ''', (session['email'], tone, subject, greeting, closing))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    automation = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (session['email'],)).fetchone()
    conn.close()
    return render_template('automation.html', automation=automation)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
