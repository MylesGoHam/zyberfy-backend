from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from email_utils import send_email
from models import create_users_table, create_automation_settings_table, create_subscriptions_table
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
create_users_table()
create_automation_settings_table()
create_subscriptions_table()

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
    conn.close()

    return render_template('dashboard.html', automation=automation)

@app.route('/automation', methods=['GET', 'POST'])
def automation_settings():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        subject = request.form['subject']
        greeting = request.form['greeting']
        tone = request.form['tone']
        footer = request.form['footer']

        existing = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()

        if existing:
            conn.execute('''
                UPDATE automation_settings
                SET subject = ?, greeting = ?, tone = ?, footer = ?
                WHERE email = ?
            ''', (subject, greeting, tone, footer, session['email']))
        else:
            conn.execute('''
                INSERT INTO automation_settings (email, subject, greeting, tone, footer)
                VALUES (?, ?, ?, ?, ?)
            ''', (session['email'], subject, greeting, tone, footer))

        conn.commit()

    automation = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
