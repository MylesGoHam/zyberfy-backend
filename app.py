from flask import Flask, request, render_template, redirect, url_for, flash, session
from dotenv import load_dotenv
from ai import generate_proposal
from email_utils import send_proposal_email
import os
import re
from models import create_automation_table, get_db_connection

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')

# ---------- INDEX (Landing Page) ----------
@app.route("/")
def home():
    return render_template("index.html")

# ---------- CLIENT LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        if not is_valid_email(email):
            flash("Invalid email format.", "error")
            return redirect(url_for("login"))
        session["client_email"] = email
        flash("Welcome back!", "success")
        return redirect(url_for("dashboard"))
    return render_template("login.html")

# ---------- CLIENT DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    email = session.get("client_email")
    if not email:
        flash("Please log in to access the dashboard.", "error")
        return redirect(url_for("login"))
    return render_template("dashboard.html", email=email)

# ---------- AUTOMATION SETTINGS ----------
@app.route("/automation", methods=["GET", "POST"])
def automation():
    email = session.get("client_email")
    if not email:
        flash("Please log in to access automation settings.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        subject = request.form.get("subject")
        greeting = request.form.get("greeting")
        tone = request.form.get("tone")
        footer = request.form.get("footer")
        ai_training = request.form.get("ai_training")
        accept_msg = request.form.get("accept_msg")
        decline_msg = request.form.get("decline_msg")

        conn.execute("""
            INSERT INTO automation_settings (email, subject, greeting, tone, footer, ai_training, accept_msg, decline_msg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                subject=excluded.subject,
                greeting=excluded.greeting,
                tone=excluded.tone,
                footer=excluded.footer,
                ai_training=excluded.ai_training,
                accept_msg=excluded.accept_msg,
                decline_msg=excluded.decline_msg;
        """, (email, subject, greeting, tone, footer, ai_training, accept_msg, decline_msg))

        conn.commit()
        conn.close()

        flash("Your automation settings have been saved!", "success")
        return redirect(url_for("dashboard"))

    settings = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (email,)).fetchone()
    conn.close()

    return render_template("automation.html", settings=settings)

# ---------- SUBMIT PROPOSAL ----------
@app.route("/submit_proposal", methods=["POST"])
def submit_proposal():
    lead_name = request.form.get("lead_name")
    lead_email = request.form.get("lead_email")
    message = request.form.get("message")
    inquiry_type = request.form.get("inquiry_type")
    offer_amount = request.form.get("offer_amount")
    client_email = request.form.get("client_email") or session.get("client_email")

    if not client_email:
        flash("Client information is missing.", "error")
        return redirect(url_for("home"))

    conn = get_db_connection()
    settings = conn.execute("SELECT * FROM automation_settings WHERE email = ?", (client_email,)).fetchone()
    conn.close()

    if not settings:
        flash("Client automation settings not found.", "error")
        return redirect(url_for("home"))

    form_data = {
        "lead_name": lead_name,
        "lead_email": lead_email,
        "message": message
    }

    if inquiry_type == "offer" and offer_amount:
        form_data["message"] += f"\n\nOffer Submitted: ${offer_amount}"

    proposal_text = generate_proposal(settings, form_data)

    # ✅ Send proposal email to lead
    email_subject = settings['subject'] or "Your Proposal from Zyberfy"
    send_proposal_email(lead_email, email_subject, proposal_text)

    return render_template("thank_you.html", proposal=proposal_text)

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.pop("client_email", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

# ---------- UTILS ----------
def is_valid_email(email):
    return re.match(r"(^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)", email) is not None

# ---------- RUN ----------
if __name__ == "__main__":
    create_automation_table()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
