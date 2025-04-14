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

@app.route("/", methods=["GET"])
def home():
    proposals, clients = [], []
    if os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, newline='', encoding="utf-8") as file:
            proposals = list(csv.DictReader(file))
    if os.path.exists(CLIENTS_FILENAME):
        with open(CLIENTS_FILENAME, newline='', encoding="utf-8") as file:
            clients = list(csv.DictReader(file))

    def extract_number(value):
        digits = ''.join(c for c in value if c.isdigit())
        return int(digits) if digits else 0

    estimated_revenue = sum(extract_number(p.get("Budget", "")) for p in proposals)
    service_counter = Counter(p.get("Service", "") for p in proposals)
    stats = {
        "total_proposals": len(proposals),
        "total_clients": len(clients),
        "estimated_revenue": estimated_revenue,
        "most_common_service": service_counter.most_common(1)[0][0] if service_counter else "N/A"
    }

    return render_template("landing.html", stats=stats)

@app.route("/proposal", methods=["GET", "POST"])
def proposal():
    if request.method == "POST":
        try:
            name = request.form["name"]
            email = request.form["email"]
            service = request.form["service"]
            budget = request.form["budget"]
            location = request.form["location"]
            special_requests = request.form["requests"]

            if not is_valid_email(email):
                flash("Invalid email address", "error")
                return redirect(url_for("proposal"))

            proposal_text = generate_proposal(name, service, budget, location, special_requests)
            slug_name = name.strip().lower().replace(" ", "-")
            subject = f"Proposal Request from {name} ({service})"
            content = f"""Name: {name}
Email: {email}
Service: {service}
Budget: {budget}
Location: {location}
Special Requests: {special_requests}

---------------------
AI-Generated Proposal:
{proposal_text}

--
The Zyberfy Concierge Team
hello@zyberfy.com
www.zyberfy.com
"""

            send_email(subject, content, user_email=email)
            save_to_csv(CSV_FILENAME, name, email, service, budget, location, special_requests, proposal_text)
            return render_template("thank_you.html", name=name, proposal=proposal_text)

        except Exception as e:
            flash(f"An error occurred: {e}", "error")
            return redirect(url_for("proposal"))

    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    proposals = []
    if os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, newline='', encoding="utf-8") as file:
            proposals = list(csv.DictReader(file))
    return render_template("dashboard.html", proposals=proposals)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Incorrect login credentials", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

def send_email(subject, content, user_email=None):
    from_email = Email("hello@zyberfy.com")
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    sg.send(Mail(from_email, To("mylescunningham0@gmail.com"), subject, Content("text/plain", content)))
    if user_email:
        sg.send(Mail(from_email, To(user_email), "Your Proposal Request Was Received", Content("text/plain", "Thanks for your request! We’ll be in touch soon.")))

def save_to_csv(filename, *args):
    file_exists = os.path.isfile(filename)
    with open(filename, mode="a", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Name", "Email", "Service", "Budget", "Location", "Requests", "Proposal"])
        writer.writerow([datetime.now().isoformat(), *args])

def is_valid_email(email):
    return re.match(r"(^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)", email) is not None

if __name__ == "__main__":
    app.run(debug=True)
