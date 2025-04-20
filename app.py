# app.py
import os
import sqlite3
import logging
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

# ─── Configuration ─────────────────────────────────────────────────────────────
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
SENDER_EMAIL    = os.getenv("SENDER_EMAIL")
ADMIN_EMAIL     = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")

# Optional: send errors to your logs
logging.basicConfig(level=logging.INFO)

# ─── Initialize database and tables ─────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()

# Seed admin user (if not already present)
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute("""
      INSERT OR IGNORE INTO users
        (email, password, first_name, plan_status)
      VALUES (?, ?, ?, ?)
    """, (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro"))
    conn.commit()
    conn.close()

# ─── Routes ────────────────────────────────────────────────────────────────────

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
            "SELECT * FROM users WHERE email = ?", (email,)
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
        "SELECT * FROM users WHERE email = ?", (session['email'],)
    ).fetchone()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
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
def automation_page():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)


@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    tone  = request.form.get('tone')
    style = request.form.get('style')
    notes = request.form.get('additional_notes')

    conn = get_db_connection()
    exists = conn.execute(
        "SELECT 1 FROM automation_settings WHERE email = ?", (session['email'],)
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
    conn.close()
    return jsonify({'success': True})


@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    """Used by the Test Proposal button on /automation"""
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    auto = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()
    if not auto:
        return jsonify({'success': False, 'error': 'No settings found'}), 400

    prompt = (
        f"Write a concise business proposal email in a {auto['tone']} tone "
        f"and {auto['style']} style.\n\n"
        f"Extra notes: {auto['additional_notes'] or 'none'}"
    )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":prompt}],
            max_tokens=300,
            temperature=0.7
        )
        proposal = resp.choices[0].message.content.strip()
        return jsonify({'success': True, 'proposal': proposal})
    except Exception as e:
        logging.error("OpenAI error: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/proposal', methods=['GET', 'POST'])
def proposal():
    """Public form to send a real proposal email to a lead."""
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        lead_name  = request.form['name']
        lead_email = request.form['email']
        budget     = request.form['budget']

        conn = get_db_connection()
        auto = conn.execute(
            "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
        ).fetchone()
        conn.close()

        prompt = (
            f"Write a professional business proposal email addressed to {lead_name}, "
            f"with budget ${budget}, in a {auto['tone']} tone and {auto['style']} style. "
            f"Notes: {auto['additional_notes'] or 'none'}"
        )

        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role":"user","content":prompt}],
                max_tokens=350,
                temperature=0.7
            )
            email_body = resp.choices[0].message.content.strip()
        except Exception as e:
            flash(f"Error generating proposal: {e}", "error")
            logging.error("OpenAI error on /proposal: %s", e)
            return redirect(url_for('proposal'))

        subject = f"Proposal for {lead_name} (Budget ${budget})"
        status = send_proposal_email(
            to_email=lead_email,
            subject=subject,
            content=email_body,
            cc_client=False
        )

        if status and 200 <= status < 300:
            return render_template('thank_you.html')
        else:
            flash("Failed to send proposal email", "error")
            return redirect(url_for('proposal'))

    return render_template('proposal.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
