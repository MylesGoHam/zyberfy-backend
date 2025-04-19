from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from email_utils import send_proposal_email
from models import create_automation_table  # Only create automation table for now
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

DATABASE = 'zyberfy.db'

# Connect to the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize necessary tables
create_automation_table()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password)).fetchone()
        conn.close()

        if user:
            session['email'] = user['email']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid email or password')

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (session['email'],)).fetchone()
    subscription = conn.execute("SELECT * FROM subscriptions WHERE email = ?", (session['email'],)).fetchone()
    conn.close()

    first_name = session['email'].split('@')[0].capitalize()
    plan_status = 'Active' if subscription else 'Inactive'
    automation_complete = True if automation else False

    return render_template('dashboard.html',
                           first_name=first_name,
                           plan_status=plan_status,
                           automation_complete=automation_complete)

@app.route('/automation', methods=['GET', 'POST'])
def automation_settings():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        tone = request.form.get('tone')
        style = request.form.get('style')
        additional_notes = request.form.get('additional_notes')

        existing = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()

        if existing:
            conn.execute('''
                UPDATE automation_settings
                SET tone = ?, style = ?, additional_notes = ?
                WHERE email = ?
            ''', (tone, style, additional_notes, session['email']))
        else:
            conn.execute('''
                INSERT INTO automation_settings (email, tone, style, additional_notes)
                VALUES (?, ?, ?, ?)
            ''', (session['email'], tone, style, additional_notes))

        conn.commit()

    automation = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
