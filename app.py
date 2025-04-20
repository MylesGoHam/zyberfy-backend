# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from dotenv import load_dotenv

load_dotenv()

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table
)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

# Initialize DB + tables
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
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['email'] = email
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()

    return render_template('dashboard.html', automation=automation)

@app.route('/automation', methods=['GET', 'POST'])
def automation_settings():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        # pull all your form fields here...
        # for example:
        tone    = request.form.get('tone')
        style   = request.form.get('style')
        notes   = request.form.get('additional_notes')
        # ...etc

        existing = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?",
            (session['email'],)
        ).fetchone()

        if existing:
            conn.execute("""
              UPDATE automation_settings
              SET tone=?, style=?, additional_notes=?
              WHERE email=?;
            """, (tone, style, notes, session['email']))
        else:
            conn.execute("""
              INSERT INTO automation_settings
                (email, tone, style, additional_notes)
              VALUES (?, ?, ?, ?);
            """, (session['email'], tone, style, notes))

        conn.commit()

    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)

@app.route('/memberships')
def memberships():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('memberships.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # pick port from env (Render) or default 5000
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
