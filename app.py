# app.py

from flask import Flask, render_template, request, redirect, url_for, session
import os
from dotenv import load_dotenv

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

# Initialize necessary tables at startup
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
            'SELECT * FROM users WHERE email = ? AND password = ?',
            (email, password)
        ).fetchone()
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
        tone             = request.form.get('tone')
        style            = request.form.get('style')
        additional_notes = request.form.get('additional_notes')

        existing = conn.execute(
            'SELECT email FROM automation_settings WHERE email = ?',
            (session['email'],)
        ).fetchone()

        if existing:
            conn.execute('''
                UPDATE automation_settings
                   SET tone            = ?,
                       style           = ?,
                       additional_notes= ?
                 WHERE email          = ?
            ''', (tone, style, additional_notes, session['email']))
        else:
            conn.execute('''
                INSERT INTO automation_settings
                            (email, tone, style, additional_notes)
                     VALUES (?,    ?,    ?,     ?)
            ''', (session['email'], tone, style, additional_notes))

        conn.commit()

    automation = conn.execute(
        'SELECT * FROM automation_settings WHERE email = ?',
        (session['email'],)
    ).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # get PORT from the environment (Render will set this for you),
    # default to 5000 when you run locally
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
