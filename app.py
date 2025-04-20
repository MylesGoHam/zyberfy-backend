# app.py

import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
DATABASE = os.getenv('DATABASE', 'zyberfy.db')
SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')

# --- APP SETUP ---
app = Flask(__name__)
app.secret_key = SECRET_KEY

# --- DB HELPERS ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # users table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
      email       TEXT PRIMARY KEY,
      password    TEXT NOT NULL,
      first_name  TEXT,
      plan_status TEXT
    );
    """)
    # automation_settings table
    c.execute("""
    CREATE TABLE IF NOT EXISTS automation_settings (
      email            TEXT PRIMARY KEY,
      tone             TEXT,
      style            TEXT,
      additional_notes TEXT,
      FOREIGN KEY(email) REFERENCES users(email)
    );
    """)
    # subscriptions table (stub—you can adjust columns as needed)
    c.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
      id       INTEGER PRIMARY KEY AUTOINCREMENT,
      email    TEXT,
      active   INTEGER DEFAULT 1,
      FOREIGN KEY(email) REFERENCES users(email)
    );
    """)
    # seed default user
    c.execute("""
      INSERT OR IGNORE INTO users
        (email, password, first_name, plan_status)
      VALUES (?, ?, ?, ?)
    """, (
      "hello@zyberfy.com",
      "Financialfreedom1",
      "Hello",
      "free"
    ))
    conn.commit()
    conn.close()

# initialize on startup
init_db()


# --- ROUTES ---
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/memberships', methods=['GET', 'POST'])
def memberships():
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

    first_name          = user['first_name'] if user else ''
    plan_status         = user['plan_status'] if user else 'Unknown'
    automation_complete = (automation is not None)

    return render_template('dashboard.html',
                           first_name=first_name,
                           plan_status=plan_status,
                           automation=automation,
                           automation_complete=automation_complete)


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


# --- RUN ---
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
