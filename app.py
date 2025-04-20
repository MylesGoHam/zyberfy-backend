# app.py

import os
import sqlite3
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
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

# ─── Load keys ────────────────────────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
    
# ─── App setup ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

# ─── Initialize DB tables ─────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()


# ─── Public routes ────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/memberships', methods=['GET', 'POST'])
def memberships():
    # if already logged in, go straight to dashboard
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
                "INSERT INTO users (email, password, first_name, plan_status) "
                "VALUES (?, ?, ?, ?)",
                (email, password, first_name, plan)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash('That email is already registered.', 'error')
            conn.close()
            return redirect(url_for('memberships'))
        conn.close()

        # auto-login
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


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Protected routes ─────────────────────────────────────────────────────────
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

    return render_template(
        'dashboard.html',
        first_name=user['first_name'] if user else '',
        plan_status=user['plan_status'] if user else 'None',
        automation=automation,
        automation_complete=(automation is not None)
    )


@app.route('/automation')
def automation():
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
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    tone    = request.form.get('tone')
    style   = request.form.get('style')
    notes   = request.form.get('additional_notes')

    conn = get_db_connection()
    existing = conn.execute(
        "SELECT 1 FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE automation_settings "
            "SET tone = ?, style = ?, additional_notes = ? "
            "WHERE email = ?",
            (tone, style, notes, session['email'])
        )
    else:
        conn.execute(
            "INSERT INTO automation_settings (email, tone, style, additional_notes) "
            "VALUES (?, ?, ?, ?)",
            (session['email'], tone, style, notes)
        )

    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    autom = conn.execute(
        "SELECT tone, style, additional_notes FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()

    if not autom:
        return jsonify({'success': False, 'error': 'No automation settings found'}), 400

    # build your prompt
    prompt = (
        f"Write a business proposal email using tone “{autom['tone']}”, "
        f"style “{autom['style']}”, and these extra notes: {autom['additional_notes'] or 'none'}."
    )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You craft high‑end business proposals."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        proposal = resp.choices[0].message.content.strip()
        return jsonify({'success': True, 'proposal': proposal})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/new-lead', methods=['GET', 'POST'])
def new_lead():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'GET':
        return render_template('new_lead.html')

    # POST → gather lead info
    name    = request.form['lead_name']
    email   = request.form['lead_email']
    budget  = request.form['lead_budget']
    message = request.form['lead_message']

    # fetch automation settings
    conn = get_db_connection()
    autom = conn.execute(
        "SELECT tone, style, additional_notes FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()

    if not autom:
        flash("Please configure automation settings first.", "error")
        return redirect(url_for('automation'))

    # compose prompt
    prompt = (
        f"You are writing a sales proposal for {name}.\n"
        f"Budget: ${budget}\n"
        f"Message: {message}\n\n"
        f"Use tone “{autom['tone']}”, style “{autom['style']}”, notes: {autom['additional_notes'] or 'none'}."
    )

    # call OpenAI
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You craft high‑end business proposals."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        proposal_text = resp.choices[0].message.content.strip()
    except Exception as e:
        flash(f"AI error: {e}", "error")
        return redirect(url_for('new_lead'))

    # email it
    subject = f"Your Proposal from {session['email'].split('@')[0].title()}"
    status = send_proposal_email(
        to_email=email,
        subject=subject,
        content=proposal_text
    )
    if not status or status >= 400:
        flash("Failed to send email to lead.", "error")
        return redirect(url_for('new_lead'))

    return render_template('lead_sent.html', lead_name=name)


# ─── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
