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

from email_utils import send_proposal_email
from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

# ─── INITIALIZE DB + TABLES + DEFAULT USER ─────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()

# seed your default login
with get_db_connection() as conn:
    conn.execute("""
      INSERT OR IGNORE INTO users
        (email, password, first_name, plan_status)
      VALUES (?, ?, ?, ?)
    """, (
      'hello@zyberfy.com',
      'Financialfreedom1',
      'Admin',
      'pro'
    ))
    conn.commit()

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def generate_proposal_text(automation, prospect_name, prospect_email, prospect_budget):
    """
    Calls OpenAI to generate a proposal based on the user's automation settings.
    """
    prompt = f"""
You are a professional proposal writer.
Write an email proposal to {prospect_name} <{prospect_email}>
with a budget of ${prospect_budget:,}. 

Tone of voice: {automation['tone']}
Email style: {automation['style']}
Additional notes: {automation.get('additional_notes','None')}

Keep it concise but persuasive, sign off as "The Zyberfy Team".
Respond with plain text only.
"""
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.7,
        max_tokens=500
    )
    return resp.choices[0].message.content.strip()

# ─── ROUTES ────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/memberships', methods=['GET','POST'])
def memberships():
    if 'email' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email      = request.form['email']
        password   = request.form['password']
        first_name = request.form.get('first_name','')
        plan       = request.form.get('plan','free')
        conn = get_db_connection()
        try:
            conn.execute("""
              INSERT INTO users (email,password,first_name,plan_status)
              VALUES (?, ?, ?, ?)
            """, (email,password,first_name,plan))
            conn.commit()
        except sqlite3.IntegrityError:
            flash('That email is already registered. Please log in.','error')
            conn.close()
            return redirect(url_for('memberships'))
        conn.close()
        session['email'] = email
        return redirect(url_for('dashboard'))
    return render_template('memberships.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email    = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()
        if user and user['password']==password:
            session['email']=email
            return redirect(url_for('dashboard'))
        flash('Invalid email or password','error')
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
        first_name         = user['first_name'],
        plan_status        = user['plan_status'],
        automation         = automation,
        automation_complete = (automation is not None)
    )

@app.route('/automation')
def automation_page():
    if 'email' not in session:
        return redirect(url_for('login'))
    # just serve the page; AJAX does the rest
    return render_template('automation.html')

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
             SET tone=?, style=?, additional_notes=?
           WHERE email=?
        """, (tone, style, notes, session['email']))
    else:
        conn.execute("""
          INSERT INTO automation_settings
            (email,tone,style,additional_notes)
          VALUES (?,?,?,?)
        """, (session['email'], tone, style, notes))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()

    if not automation:
        return jsonify({'success': False, 'error': 'No automation settings found'}), 400

    try:
        # dummy lead info for test
        text = generate_proposal_text(
            automation,
            prospect_name="Esteemed Client",
            prospect_email="client@example.com",
            prospect_budget=5000
        )
        return jsonify({'success': True, 'proposal': text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/proposal', methods=['GET','POST'])
def proposal():
    if 'email' not in session:
        return redirect(url_for('login'))
    if request.method=='POST':
        name   = request.form['name']
        email  = request.form['email']
        budget = request.form['budget']

        conn = get_db_connection()
        automation = conn.execute(
            "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
        ).fetchone()
        conn.close()
        if not automation:
            flash('Please configure your automation first!','error')
            return redirect(url_for('automation_page'))

        # generate & email
        proposal_text = generate_proposal_text(automation, name, email, budget)
        subject = f"{automation['style']} Proposal from Zyberfy"
        send_proposal_email(to_email=email, subject=subject, content=proposal_text)
        return redirect(url_for('thank_you'))

    return render_template('proposal.html')

@app.route('/thank-you')
def thank_you():
    return render_template('thank_you.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── RUN ──────────────────────────────────────────────────────────────────────
if __name__=='__main__':
    port = int(os.getenv('PORT',5000))
    app.run(host='0.0.0.0', port=port, debug=True)
