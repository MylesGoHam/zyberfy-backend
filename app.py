# app.py

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
from email_utils import send_proposal_email
from models import create_users_table, create_automation_table, create_subscriptions_table
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

# Initialize tables
create_users_table()
create_automation_table()
create_subscriptions_table()

# Home
@app.route('/')
def home():
    return render_template('index.html')

# Login
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

# Dashboard
@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (session['email'],)).fetchone()
    subscription = conn.execute("SELECT * FROM subscriptions WHERE email = ?", (session['email'],)).fetchone()
    conn.close()

    # Dummy fallback values
    first_name = session['email'].split('@')[0].capitalize()
    plan_status = 'Active' if subscription else 'Inactive'
    automation_complete = True if automation else False

    return render_template('dashboard.html',
                            first_name=first_name,
                            plan_status=plan_status,
                            automation_complete=automation_complete)

# Automation Settings
@app.route('/automation', methods=['GET', 'POST'])
def automation_settings():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        tone = request.form.get('tone')
        style = request.form.get('style')
        additional_notes = request.form.get('additional_notes')
        enable_follow_up = request.form.get('enable_follow_up')
        number_of_followups = request.form.get('number_of_followups')
        followup_delay = request.form.get('followup_delay')
        followup_style = request.form.get('followup_style')
        minimum_offer = request.form.get('minimum_offer')
        acceptance_message = request.form.get('acceptance_message')
        decline_message = request.form.get('decline_message')

        existing = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()

        if existing:
            conn.execute('''
                UPDATE automation_settings
                SET tone=?, style=?, additional_notes=?, 
                    enable_follow_up=?, number_of_followups=?, followup_delay=?, followup_style=?, 
                    minimum_offer=?, acceptance_message=?, decline_message=?
                WHERE email=?
            ''', (tone, style, additional_notes, enable_follow_up, number_of_followups, followup_delay, followup_style, minimum_offer, acceptance_message, decline_message, session['email']))
        else:
            conn.execute('''
                INSERT INTO automation_settings
                (email, tone, style, additional_notes, enable_follow_up, number_of_followups, followup_delay, followup_style, minimum_offer, acceptance_message, decline_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session['email'], tone, style, additional_notes, enable_follow_up, number_of_followups, followup_delay, followup_style, minimum_offer, acceptance_message, decline_message))

        conn.commit()
        conn.close()
        return jsonify({'success': True})

    automation = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)

# Save automation (Ajax POST from form)
@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    return automation_settings()

# Generate a Test Proposal
@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    automation = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()
    conn.close()

    if not automation:
        return jsonify({'success': False, 'error': 'No automation settings found'})

    proposal = f"""Hi there,

Thanks for reaching out. We'd love to assist you with a {automation['style']} and {automation['tone']} approach.

{automation['additional_notes'] or ''}

Best regards,  
The Zyberfy Team
"""

    return jsonify({'success': True, 'proposal': proposal})

# Memberships Page
@app.route('/memberships')
def memberships():
    return render_template('memberships.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Run App
if __name__ == '__main__':
    app.run(debug=True)
