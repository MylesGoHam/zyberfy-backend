# app.py

import os
import sqlite3
from flask import (
    Flask, render_template, request,
    redirect, url_for, session,
    flash, jsonify
)
from dotenv import load_dotenv
import openai

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table
)
from email_utils import send_proposal_email

# ─── Load env & init Flask/OpenAI ─────────────────────────────────────────────
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret")

openai.api_key = os.getenv("OPENAI_API_KEY")

# ─── Initialize DB + Tables ────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()

# ─── Seed Admin User ───────────────────────────────────────────────────────────
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute("""
      INSERT OR IGNORE INTO users
        (email, password, first_name, plan_status)
      VALUES (?, ?, ?, ?)
    """, (
      ADMIN_EMAIL,
      ADMIN_PASSWORD,
      "Admin",
      "pro"
    ))
    conn.commit()
    conn.close()

# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email','').strip()
        password = request.form.get('password','')
        if not email or not password:
            flash("Please enter both email and password.", "error")
            return redirect(url_for('login'))

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['email'] = email
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    email = session['email']
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (email,)
    ).fetchone()
    conn.close()

    return render_template(
        'dashboard.html',
        first_name        = user['first_name'],
        plan_status       = user['plan_status'],
        automation        = automation,
        automation_exists = (automation is not None)
    )


@app.route('/automation', methods=['GET','POST'])
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))

    email = session['email']
    conn = get_db_connection()

    if request.method == 'POST':
        tone  = request.form.get('tone')
        style = request.form.get('style')
        notes = request.form.get('additional_notes')

        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?", (email,)
        ).fetchone()

        if exists:
            conn.execute("""
              UPDATE automation_settings
                 SET tone = ?, style = ?, additional_notes = ?
               WHERE email = ?
            """, (tone, style, notes, email))
        else:
            conn.execute("""
              INSERT INTO automation_settings
                (email, tone, style, additional_notes)
              VALUES (?,?,?,?)
            """, (email, tone, style, notes))

        conn.commit()
        conn.close()
        flash("✅ Settings saved!", "success")
        return redirect(url_for('automation'))

    # GET
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return render_template('automation.html', automation=automation)


@app.route('/proposal')
def proposal():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('proposal.html')


@app.route('/preview-proposal', methods=['POST'])
def preview_proposal():
    if 'email' not in session:
        return jsonify(success=False, error="Unauthorized"), 403

    name   = request.form['name'].strip()
    lead   = request.form['email'].strip()
    budget = request.form['budget'].strip()
    email  = session['email']

    # fetch automation settings
    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (email,)
    ).fetchone()
    conn.close()

    if not automation:
        return jsonify(success=False, error="No automation settings"), 400

    prompt = (
      f"Write a business proposal email to {name} (budget ${budget}), "
      f"in a {automation['tone']} tone & {automation['style']} style. "
      f"Extra notes: {automation['additional_notes'] or 'none'}"
    )

    try:
        resp = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=350,
            temperature=0.7
        )
        body = resp.choices[0].text.strip()
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

    return jsonify(success=True, email_body=body)


@app.route('/send-proposal', methods=['POST'])
def send_proposal():
    if 'email' not in session:
        return jsonify(success=False, error="Unauthorized"), 403

    data = request.get_json()
    name       = data.get('name')
    lead       = data.get('email')
    budget     = data.get('budget')
    email_body = data.get('email_body')

    subject = f"Proposal for {name} (Budget: ${budget})"
    status  = send_proposal_email(
        to_email   = lead,
        subject    = subject,
        content    = email_body,
        cc_client  = False
    )

    if status and 200 <= status < 300:
        return jsonify(success=True)
    return jsonify(success=False, error="Failed to send email"), 500


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
