from flask import Flask, request, render_template, redirect, url_for, flash, session, send_file
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from dotenv import load_dotenv
import os
import re
import csv
from datetime import datetime
from collections import Counter
from email_assistant import generate_proposal

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
ADMIN_EMAIL = "hello@zyberfy.com"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password123")
CSV_FILENAME = "proposals.csv"
CLIENTS_FILENAME = "clients.csv"

# ---------- INDEX ----------
@app.route("/", methods=["GET"])
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
        return redirect(url_for("client_dashboard"))
    return render_template("login.html")

# ---------- CLIENT DASHBOARD ----------
@app.route("/client_dashboard")
def client_dashboard():
    email = session.get("client_email")
    if not email:
        flash("Please log in first.", "error")
        return redirect(url_for("client_login"))

    proposals = []
    if os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, newline='', encoding="utf-8") as file:
            for row in csv.DictReader(file):
                if row.get("Email", "").strip().lower() == email.lower():
                    proposals.append(row)

    return render_template("client_dashboard.html", proposals=proposals, email=email)

# ---------- CLIENT LOGOUT ----------
@app.route("/client_logout")
def client_logout():
    session.pop("client_email", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("client_login"))

# ---------- UTILS ----------
def send_email(subject, content, user_email=None):
    from_email = Email("hello@zyberfy.com")
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    sg.send(Mail(from_email, To("mylescunningham0@gmail.com"), subject, Content("text/plain", content)))

    if user_email:
        sg.send(Mail(
            from_email,
            To(user_email),
            "Your Proposal Request Was Received",
            Content("text/plain", "Thanks for your request! Our concierge team will be in touch shortly.\n\n-- The Zyberfy Team")
        ))

def send_admin_alert(subject, body):
    try:
        from_email = Email("hello@zyberfy.com", "Zyberfy AI")
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        sg.send(Mail(from_email, To("hello@zyberfy.com"), subject, Content("text/plain", body)))
    except Exception as e:
        print("Failed to send alert:", str(e))

def save_to_csv(filename, *args):
    file_exists = os.path.isfile(filename)
    with open(filename, mode="a", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            if filename == CLIENTS_FILENAME:
                writer.writerow(["Timestamp", "Name", "Email", "Company", "Phone", "Message", "Proposal"])
            else:
                writer.writerow(["Timestamp", "Name", "Email", "Service", "Budget", "Location", "Requests", "Proposal"])
        writer.writerow([datetime.now().isoformat(), *args])

def is_valid_email(email):
    return re.match(r"(^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)", email) is not None

# ---------- RUN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
