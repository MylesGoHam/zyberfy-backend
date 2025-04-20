# app.py
import sqlite3
import os

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from dotenv import load_dotenv
import openai

load_dotenv()

# --- CONFIG ---
DATABASE       = os.getenv('DATABASE', 'zyberfy.db')
SECRET_KEY     = os.getenv('SECRET_KEY', 'default_secret_key')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# --- APP SETUP ---
app = Flask(__name__)
app.secret_key = SECRET_KEY

openai.api_key = OPENAI_API_KEY

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

    # subscriptions table (stub—you can adjust columns)
    c.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
      id     INTEGER PRIMARY KEY AUTOINCREMENT,
      email  TEXT,
      active INTEGER DEFAULT 1,
      FOREIGN KEY(email) REFERENCES users(email)
    );
    """)

    # seed default user
    c.execute("""
      INSERT OR IGNORE INTO users
        (email, password, first_name, plan_status)
      VALUES (?, ?, ?, ?);
    """, (
      "hello@zyberfy.com",
      "Financialfreedom1",
      "Hello",
      "free"
    ))

    conn.commit()
    conn.close()

init_db()


# --- ROUTES (unchanged) ---
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
            conn.execute(
              "INSERT INTO users (email, password, first_name, plan_status) VALUES (?,?,?,?)",
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

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute(
          "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and user['password']==password:
            session['email'] = email
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

    first_name          = user['first_name'] if user else ''
    plan_status         = user['plan_status'] if user else 'Unknown'
    automation_complete = (automation is not None)

    return render_template('dashboard.html',
      first_name=first_name,
      plan_status=plan_status,
      automation=automation,
      automation_complete=automation_complete
    )

@app.route('/automation', methods=['GET','POST'])
def automation_settings():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if request.method=='POST':
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
                 SET tone=?, style=?, additional_notes=?
               WHERE email=?
            """, (tone, style, notes, session['email']))
        else:
            conn.execute("""
              INSERT INTO automation_settings
                (email, tone, style, additional_notes)
              VALUES (?,?,?,?)
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


# --- NEW: generate a sample proposal via OpenAI ---
@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify(success=False, error="Not logged in"), 401

    conn = get_db_connection()
    s = conn.execute(
      "SELECT tone, style, additional_notes FROM automation_settings WHERE email = ?",
      (session['email'],)
    ).fetchone()
    conn.close()

    if not s:
        return jsonify(success=False, error="No automation settings yet")

    prompt = (
      f"You are a world‑class business proposal writer.\n"
      f"Tone: {s['tone']}\n"
      f"Style: {s['style']}\n"
      f"Additional notes: {s['additional_notes']}\n\n"
      "Now generate a concise, client‑ready proposal in plain text."
    )

    try:
        resp = openai.ChatCompletion.create(
          model="gpt-4o-mini",
          messages=[
            {"role":"system","content":"You craft business proposals."},
            {"role":"user","content":prompt}
          ],
          temperature=0.7,
          max_tokens=500
        )
        proposal = resp.choices[0].message.content.strip()
        return jsonify(success=True, proposal=proposal)
    except Exception as e:
        return jsonify(success=False, error=str(e))

# --- RUN ---
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
