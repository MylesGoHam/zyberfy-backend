# app.py
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
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

# --- initialize our three tables ---
create_users_table()
create_automation_settings_table()
create_subscriptions_table()


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/memberships', methods=['GET', 'POST'])
def memberships():
    # If you already have a session, skip to dash
    if 'email' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email      = request.form['email']
        password   = request.form['password']
        first_name = request.form.get('first_name', '')
        plan       = request.form.get('plan', 'free')

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (email, password, first_name, plan_status) VALUES (?, ?, ?, ?)",
                (email, password, first_name, plan)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash('That email is already registered.', 'error')
            conn.close()
            return redirect(url_for('memberships'))
        conn.close()

        # auto-login and go to dashboard
        session['email'] = email
        return redirect(url_for('dashboard'))

    return render_template('memberships.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
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

        flash('Invalid email or password', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (session['email'],)
    ).fetchone()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()

    # pass the bits your dashboard.html needs
    first_name         = user['first_name'] if user else ''
    plan_status        = user['plan_status'] if user else 'None'
    automation_complete = automation is not None

    return render_template(
        'dashboard.html',
        first_name=first_name,
        plan_status=plan_status,
        automation=automation,
        automation_complete=automation_complete
    )


@app.route('/automation', methods=['GET', 'POST'])
def automation_settings():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        tone  = request.form.get('tone')
        style = request.form.get('style')
        notes = request.form.get('additional_notes')

        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?",
            (session['email'],)
        ).fetchone()

        if exists:
            conn.execute("""
              UPDATE automation_settings
                 SET tone = ?, style = ?, additional_notes = ?
               WHERE email = ?
            """, (tone, style, notes, session['email']))
        else:
            conn.execute("""
              INSERT INTO automation_settings
                (email, tone, style, additional_notes)
              VALUES (?, ?, ?, ?)
            """, (session['email'], tone, style, notes))

        conn.commit()

    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
