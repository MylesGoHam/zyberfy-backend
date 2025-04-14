from flask import Flask, request, render_template, redirect, url_for, flash, session
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
CSV_FILENAME = "proposals.csv"
CLIENTS_FILENAME = "clients.csv"
ADMIN_EMAIL = "hello@zyberfy.com"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password123")

# ---------- INDEX (Landing Page) ----------
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
@app.route("/dashboard")
def client_dashboard():
    email = session.get("client_email")
    if not email:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    proposals = []
    if os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, newline='', encoding="utf-8") as file:
            for row in csv.DictReader(file):
                if row.get("Email", "").strip().lower() == email.lower():
                    proposals.append(row)

    return render_template("dashboard.html", proposals=proposals, email=email)

# ---------- CLIENT LOGOUT ----------
@app.route("/logout")
def logout():
    session.pop("client_email", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

# ---------- PROPOSAL (Optional if still using it) ----------
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

-- The Zyberfy Team
hello@zyberfy.com
"""

            send_email(subject, content, user_email=email)
            save_to_csv(CSV_FILENAME, name, email, service, budget, location, special_requests, proposal_text)
            flash("Proposal submitted successfully!", "success")
            return render_template("thank_you.html", name=name, proposal=proposal_text)

        except Exception as e:
            flash(f"An error occurred: {e}", "error")
            return redirect(url_for("proposal"))

    return render_template("proposal.html")

# ---------- ONBOARDING ----------
@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        company = request.form["company"]
        phone = request.form["phone"]
        message = request.form["message"]

        if not is_valid_email(email):
            flash("Invalid email format.", "error")
            return redirect(url_for("onboarding"))

        save_to_csv(CLIENTS_FILENAME, name, email, company, phone, message, "")
        content = f"""New Client Onboarding:
Name: {name}
Email: {email}
Company: {company}
Phone: {phone}
Message: {message}"""
        send_email("New Client Onboarding", content, user_email=email)
        flash("Client onboarding submitted!", "success")
        return render_template("thank_you.html", name=name, proposal="Your info was received.")

    return render_template("onboarding.html")

# ---------- UTILS ----------
def send_email(subject, content, user_email=None):
    from_email = Email("hello@zyberfy.com")
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    sg.send(Mail(from_email, To("mylescunningham0@gmail.com"), subject, Content("text/plain", content)))

    if user_email:
        sg.send(Mail(
            from_email,
            To(user_email),
            "We Received Your Request",
            Content("text/plain", "Thank you! Our team will be in touch shortly.\n\n-- The Zyberfy Team")
        ))

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
    return re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email) is not None

# ---------- RUN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
