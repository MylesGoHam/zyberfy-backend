from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session, send_file
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from dotenv import load_dotenv
import os
import re
import csv
from datetime import datetime
from email_assistant import generate_proposal

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@zyberfy.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password123")
CSV_FILENAME = "proposals.csv"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            name = request.form.get("name")
            email = request.form.get("email")
            service = request.form.get("service")
            budget = request.form.get("budget")
            location = request.form.get("location")
            special_requests = request.form.get("requests")

            if not is_valid_email(email):
                flash("Invalid email address", "error")
                return redirect(url_for('index'))

            proposal = generate_proposal(name, service, budget, location, special_requests)

            subject = f"Proposal Request from {name} ({service})"
            content = f"""Name: {name}
Email: {email}
Service: {service}
Budget: {budget}
Location: {location}
Special Requests: {special_requests}

---------------------
✨ AI-Generated Proposal:
{proposal}
"""
            send_email(subject, content, user_email=email)
            save_to_csv(name, email, service, budget, location, special_requests, proposal)

            return render_template("thank_you.html", name=name, proposal=proposal)

        except Exception as e:
            flash(f"An error occurred: {e}", "error")
            return redirect(url_for('index'))

    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['just_logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash("Incorrect login credentials", "error")
            return redirect(url_for('login'))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    flash("✅ Logged out successfully.", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if session.get("just_logged_in"):
        flash("✅ Logged in successfully!", "login")
        session.pop("just_logged_in")

    proposals = []

    if not os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Name", "Email", "Service", "Budget", "Location", "Requests", "Proposal"])
    else:
        with open(CSV_FILENAME, newline='', encoding="utf-8") as file:
            reader = csv.DictReader(file)
            proposals = list(reader)

    return render_template("dashboard.html", proposals=proposals)

@app.route("/download")
def download():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if not os.path.exists(CSV_FILENAME):
        flash("No CSV file available to download.", "error")
        return redirect(url_for("dashboard"))

    return send_file(CSV_FILENAME, as_attachment=True)

def send_email(subject, content, user_email=None):
    from_email = Email("hello@zyberfy.com")
    to_email = To(os.getenv("TO_EMAIL_ADDRESS", "mylescunningham0@gmail.com"))
    mail_content = Content("text/plain", content)
    mail = Mail(from_email, to_email, subject, mail_content)

    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    response = sg.send(mail)

    if user_email:
        confirm_subject = "Your Proposal Request Was Received"
        confirm_content = Content("text/plain", "Thanks for your request! We'll be in touch soon. — Team Zyberfy")
        confirmation_mail = Mail(from_email, To(user_email), confirm_subject, confirm_content)
        sg.send(confirmation_mail)

    return response

def save_to_csv(name, email, service, budget, location, requests, proposal):
    file_exists = os.path.isfile(CSV_FILENAME)
    with open(CSV_FILENAME, mode="a", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Name", "Email", "Service", "Budget", "Location", "Requests", "Proposal"])
        writer.writerow([datetime.now().isoformat(), name, email, service, budget, location, requests, proposal])

def is_valid_email(email):
    email_regex = r"(^[A-Za-z0-9]+[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)"
    return re.match(email_regex, email) is not None

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
