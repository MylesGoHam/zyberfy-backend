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

# ---------- LANDING PAGE ----------
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# ---------- PROPOSAL FORM ----------
@app.route("/proposal", methods=["GET", "POST"])
def proposal():
    show_branding = request.args.get("branding", "1") == "1"
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
            send_admin_alert("New Proposal Submission", f"{name} ({email}) for {service}")
            share_url = f"{request.url_root}proposal/{slug_name}".rstrip("/")
            return render_template("thank_you.html", name=name, proposal=proposal_text, share_url=share_url)

        except Exception as e:
            flash(f"An error occurred: {e}", "error")
            return redirect(url_for("proposal"))

    return render_template("proposal.html", show_branding=show_branding)

# ---------- PUBLIC PROPOSAL PAGE ----------
@app.route("/proposal/<name_slug>")
def view_proposal(name_slug):
    if os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, newline='', encoding="utf-8") as file:
            for row in csv.DictReader(file):
                if row["Name"].strip().lower().replace(" ", "-") == name_slug:
                    return render_template("public_proposal.html", name=row["Name"], proposal=row["Proposal"])
    return "Proposal not found."

# ---------- ONBOARDING ----------
@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    show_branding = request.args.get("branding", "1") == "1"
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
        content = f"""Name: {name}
Email: {email}
Company: {company}
Phone: {phone}
Message: {message}"""
        send_email(f"New Client Onboarding: {name}", content, user_email=email)
        send_admin_alert("New Client Onboarding", f"{name} ({email}) from {company}")
        return render_template("thank_you.html", name=name, proposal="Your onboarding was submitted successfully.")

    return render_template("onboarding.html", show_branding=show_branding)

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
