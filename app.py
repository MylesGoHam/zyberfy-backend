from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from models import get_db_connection
import os
import openai

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your_secret_key")
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        session['email'] = email
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    automation = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (session['email'],)).fetchone()
    conn.close()
    return render_template('dashboard.html', automation=automation)

@app.route('/automation', methods=['GET', 'POST'])
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        follow_up_strategy = request.form.get('follow_up_strategy')
        min_offer_amount = request.form.get('min_offer_amount')
        acceptance_message = request.form.get('acceptance_message')
        decline_message = request.form.get('decline_message')
        conn.execute('''
            INSERT INTO automation_settings (email, follow_up_strategy, min_offer_amount, acceptance_message, decline_message)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                follow_up_strategy=excluded.follow_up_strategy,
                min_offer_amount=excluded.min_offer_amount,
                acceptance_message=excluded.acceptance_message,
                decline_message=excluded.decline_message
        ''', (session['email'], follow_up_strategy, min_offer_amount, acceptance_message, decline_message))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    automation = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (session['email'],)).fetchone()
    conn.close()
    return render_template('automation.html', automation=automation)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
