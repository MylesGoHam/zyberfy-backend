# app.py

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
from dotenv import load_dotenv
from email_utils import send_proposal_email
from models import get_db_connection, create_automation_table

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

# Initialize database tables
create_automation_table()

# Home page
@app.route('/')
def home():
    return render_template('index.html')

# Login page
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
            session['first_name'] = user['first_name']
            session['plan_status'] = user['plan_status']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid email or password')
    return render_template('login.html')

# Dashboard page
@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()
    conn.close()

    automation_complete = automation is not None

    return render_template(
        'dashboard.html',
        first_name=session.get('first_name', 'Client'),
        plan_status=session.get('plan_status', 'Free'),
        automation_complete=automation_complete
    )

# Automation settings page
@app.route('/automation')
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)

# Save automation settings
@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    form = request.form

    tone = form.get('tone')
    style = form.get('style')
    additional_notes = form.get('additional_notes')
    enable_follow_up = form.get('enable_follow_up')
    number_of_followups = form.get('number_of_followups')
    followup_delay = form.get('followup_delay')
    followup_style = form.get('followup_style')
    minimum_offer = form.get('minimum_offer')
    acceptance_message = form.get('acceptance_message')
    decline_message = form.get('decline_message')

    conn = get_db_connection()
    existing = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()

    if existing:
        conn.execute('''
            UPDATE automation_settings
            SET tone = ?, style = ?, additional_notes = ?, 
                enable_follow_up = ?, number_of_followups = ?, followup_delay = ?, followup_style = ?,
                minimum_offer = ?, acceptance_message = ?, decline_message = ?
            WHERE email = ?
        ''', (
            tone, style, additional_notes,
            enable_follow_up, number_of_followups, followup_delay, followup_style,
            minimum_offer, acceptance_message, decline_message,
            session['email']
        ))
    else:
        conn.execute('''
            INSERT INTO automation_settings 
            (email, tone, style, additional_notes, enable_follow_up, number_of_followups, followup_delay, followup_style, minimum_offer, acceptance_message, decline_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session['email'], tone, style, additional_notes,
            enable_follow_up, number_of_followups, followup_delay, followup_style,
            minimum_offer, acceptance_message, decline_message
        ))

    conn.commit()
    conn.close()

    return jsonify({'success': True})

# Test proposal generation
@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    automation = conn.execute('SELECT * FROM automation_settings WHERE email = ?', (session['email'],)).fetchone()
    conn.close()

    if not automation:
        return jsonify({'success': False, 'error': 'No automation settings found'}), 404

    # Dummy simple proposal generation (customize later)
    proposal = f"""Hi there,

Thanks for reaching out. We'd love to assist you with a {automation['style']} and {automation['tone']} approach.

{automation['additional_notes'] or ''}

Best regards,
The Zyberfy Team
"""
    return jsonify({'success': True, 'proposal': proposal})

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Run app
if __name__ == '__main__':
    app.run(debug=True)
