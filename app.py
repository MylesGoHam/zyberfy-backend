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

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

# ─── Initialize DB + Tables ────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()

# seed admin user
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
    return render_template('index.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email = request.form['email']
        pw    = request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?",(email,)).fetchone()
        conn.close()
        if user and user['password']==pw:
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
    user = conn.execute("SELECT * FROM users WHERE email = ?",(session['email'],)).fetchone()
    automation = conn.execute("SELECT * FROM automation_settings WHERE email = ?",(session['email'],)).fetchone()
    conn.close()
    return render_template(
        'dashboard.html',
        first_name=user['first_name'],
        plan_status=user['plan_status'],
        automation=automation,
        automation_complete=(automation is not None)
    )

@app.route('/proposal')
def proposal():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('proposal.html')

@app.route('/preview-proposal', methods=['POST'])
def preview_proposal():
    if 'email' not in session:
        return jsonify({'success':False,'error':'Unauthorized'}),403

    lead_name  = request.form['name']
    lead_email = request.form['email']
    budget     = request.form['budget']

    # grab automation settings
    conn = get_db_connection()
    automation = conn.execute(
      "SELECT * FROM automation_settings WHERE email = ?",(session['email'],)
    ).fetchone()
    conn.close()

    if not automation:
        return jsonify({'success':False,'error':'No automation settings found'}),400

    prompt = (
      f"Write a business proposal email to {lead_name}, budget ${budget}, "
      f"in a {automation['tone']} tone and {automation['style']} style. "
      f"Notes: {automation['additional_notes'] or 'none'}"
    )
    try:
        resp = openai.Completion.create(
          engine="text-davinci-003",
          prompt=prompt,
          max_tokens=350,
          temperature=0.7
        )
        email_body = resp.choices[0].text.strip()
    except Exception as e:
        return jsonify({'success':False,'error':str(e)}),500

    return jsonify({'success':True,'email_body':email_body})

@app.route('/send-proposal', methods=['POST'])
def send_proposal():
    if 'email' not in session:
        return jsonify({'success':False,'error':'Unauthorized'}),403

    data = request.get_json()
    lead_name  = data.get('name')
    lead_email = data.get('email')
    budget     = data.get('budget')
    email_body = data.get('email_body')

    subject = f"Proposal for {lead_name} (Budget: ${budget})"
    status = send_proposal_email(
      to_email=lead_email,
      subject=subject,
      content=email_body,
      cc_client=False
    )

    if status and 200 <= status < 300:
        return jsonify({'success':True})
    else:
        return jsonify({'success':False,'error':'Failed to send email'}),500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__=='__main__':
    port = int(os.getenv('PORT',5000))
    app.run(host='0.0.0.0',port=port,debug=True)
