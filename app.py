from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify
)
import os
from dotenv import load_dotenv

import sqlite3
from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table
)
from email_utils import send_email

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

# Initialize tables
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
        pwd   = request.form['password']
        conn  = get_db_connection()
        user  = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, pwd)
        ).fetchone()
        conn.close()
        if user:
            session['email']      = user['email']
            session['first_name'] = user['first_name']
            session['plan_status']= user['plan_status']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    auto = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()
    automation_complete = auto is not None
    return render_template(
        'dashboard.html',
        first_name=session.get('first_name'),
        plan_status=session.get('plan_status'),
        automation_complete=automation_complete
    )

@app.route('/automation', methods=['GET', 'POST'])
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if request.method == 'POST':
        data = {
            'tone':                request.form.get('tone'),
            'style':               request.form.get('style'),
            'additional_notes':    request.form.get('additional_notes'),
            'enable_follow_up':    request.form.get('enable_follow_up'),
            'number_of_followups': int(request.form.get('number_of_followups') or 0),
            'followup_delay':      request.form.get('followup_delay'),
            'followup_style':      request.form.get('followup_style'),
            'minimum_offer':       float(request.form.get('minimum_offer') or 0),
            'acceptance_message':  request.form.get('acceptance_message'),
            'decline_message':     request.form.get('decline_message'),
        }
        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?",
            (session['email'],)
        ).fetchone()
        if exists:
            conn.execute("""
                UPDATE automation_settings
                   SET tone=?, style=?, additional_notes=?, enable_follow_up=?,
                       number_of_followups=?, followup_delay=?, followup_style=?,
                       minimum_offer=?, acceptance_message=?, decline_message=?
                 WHERE email=?
            """, (*data.values(), session['email']))
        else:
            conn.execute("""
                INSERT INTO automation_settings (
                    email, tone, style, additional_notes,
                    enable_follow_up, number_of_followups,
                    followup_delay, followup_style,
                    minimum_offer, acceptance_message, decline_message
                ) VALUES (?, ?,?,?,?,?,?,?,?,?,?)
            """, (session['email'], *data.values()))
        conn.commit()
        conn.close()
        return jsonify(success=True)

    # GET
    current = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()
    return render_template('automation.html', automation=current)

@app.route('/save-automation', methods=['POST'])
def save_automation():
    # legacy alias if your JS calls /save-automation
    return automation()

@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify(success=False, error='Not logged in'), 403

    conn = get_db_connection()
    auto = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?",
        (session['email'],)
    ).fetchone()
    conn.close()
    if not auto:
        return jsonify(success=False, error='No automation settings'), 400

    # build your prompt using settings:
    prompt = (
        f"Tone: {auto['tone']}\n"
        f"Style: {auto['style']}\n"
        f"Notes: {auto['additional_notes']}\n\n"
        "Generate a sample proposal email body."
    )
    # send_email can also be used here if you want to actually send.
    # For a test, we'll just return the prompt as 'proposal'
    # or you could call OpenAI here to generate text.
    proposal = prompt  # replace with your AI call
    return jsonify(success=True, proposal=proposal)

@app.route('/membership')
def membership():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('membership.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
