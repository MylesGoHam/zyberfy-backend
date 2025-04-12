from flask import Flask, request, render_template, redirect, url_for, flash, jsonify
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from dotenv import load_dotenv
import os
import re
from email_assistant import generate_proposal  # Your GPT proposal logic

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            print("🚨 Form POST hit Flask route")

            # Get form data
            name = request.form.get("name")
            email = request.form.get("email")
            service = request.form.get("service")
            budget = request.form.get("budget")
            location = request.form.get("location")
            special_requests = request.form.get("requests")

            # Validate email format
            if not is_valid_email(email):
                flash("Invalid email address", "error")
                return redirect(url_for('index'))

            print(f"📨 Generating proposal for {name} - {service}")

            # Generate proposal
            proposal = generate_proposal(name, service, budget, location, special_requests)

            # Compose email
            subject = f"Proposal Request from {name} ({service})"
            content = f"""
A new proposal request has been submitted:

Name: {name}
Email: {email}
Service: {service}
Budget: {budget}
Location: {location}
Special Requests: {special_requests}

---------------------
✨ AI-Generated Proposal:
{proposal}
"""

            send_email(subject, content)

            flash("✅ Your request has been sent successfully!", "success")
            return redirect(url_for('index'))

        except Exception as e:
            print(f"❌ Error in POST handler: {e}")
            flash(f"An error occurred: {e}", "error")
            return redirect(url_for('index'))

    return render_template("index.html")

@app.route("/api/test", methods=["GET"])
def test_api():
    return jsonify(status="ok", message="Backend is connected!")

def send_email(subject, content):
    print("📧 Attempting to send email...")
    print("Subject:", subject)
    print("Email content preview:")
    print(content[:500])  # Print first 500 characters of content

    from_email = Email("hello@zyberfy.com")
    to_email = To("mylescunningham0@gmail.com")
    mail_content = Content("text/plain", content)
    mail = Mail(from_email, to_email, subject, mail_content)

    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = sg.send(mail)
        print(f"✅ SendGrid Response: {response.status_code}")
        print(f"Body: {response.body}")
        print(f"Headers: {response.headers}")
    except Exception as e:
        print(f"❌ Error sending email: {e}")

def is_valid_email(email):
    email_regex = r"(^[A-Za-z0-9]+[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)"
    return re.match(email_regex, email) is not None

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
