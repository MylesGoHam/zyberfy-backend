# app.py

import os
import sqlite3

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash, jsonify
)
from dotenv import load_dotenv
import openai

# ─── App & Env ────────────────────────────────────
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

openai.api_key = os.getenv("OPENAI_API_KEY")

# ─── Models / DB ───────────────────────────────────
# Make sure your models.py exposes these three functions:
from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table
)

# Initialize your tables on startup
create_users_table()
create_automation_settings_table()
create_subscriptions_table()

# ─── Routes ───────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/memberships', methods=['GET', 'POST'])
def memberships():
    # if already logged in, skip to dashboard
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
            return redirect(url_for('memberships'))
        finally:
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
    plan_status         = user['plan_status'] if user else 'None'
    automation_complete = automation is not None

    return render_template(
        'dashboard.html',
        first_name=first_name,
        plan_status=plan_status,
        automation=automation,
        automation_complete=automation_complete
    )


@app.route('/automation')
def automation_form():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()
    return render_template('automation.html', automation=automation)


@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return jsonify(success=False, error='Unauthorized'), 401

    tone             = request.form.get('tone')
    style            = request.form.get('style')
    additional_notes = request.form.get('additional_notes')

    conn = get_db_connection()
    exists = conn.execute(
        "SELECT 1 FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()

    if exists:
        conn.execute("""
            UPDATE automation_settings
               SET tone             = ?,
                   style            = ?,
                   additional_notes = ?
             WHERE email = ?
        """, (tone, style, additional_notes, session['email']))
    else:
        conn.execute("""
            INSERT INTO automation_settings
                (email, tone, style, additional_notes)
            VALUES (?, ?, ?, ?)
        """, (session['email'], tone, style, additional_notes))

    conn.commit()
    conn.close()
    return jsonify(success=True)


@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify(success=False, error="Unauthorized"), 401

    conn = get_db_connection()
    row = conn.execute(
        "SELECT tone, style, additional_notes FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify(success=False, error="No automation settings found"), 400

    prompt = (
        f"You are a world‑class proposal writer.\n"
        f"Tone: {row['tone']}\n"
        f"Style: {row['style']}\n"
        f"Notes: {row['additional_notes']}\n\n"
        "Generate a concise, client‑ready business proposal."
    )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role":"system", "content":"You craft high-end business proposals."},
                {"role":"user",   "content":prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        proposal = resp.choices[0].message.content.strip()
        return jsonify(success=True, proposal=proposal)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Run ──────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
