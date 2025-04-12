from flask import Flask, request, render_template, redirect, url_for, flash, jsonify
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from dotenv import load_dotenv
import os
import re

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')

# SendGrid setup
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            # Get form data
            email = request.form.get("email")
            service = request.form.get("service")
            budget = request.form.get("budget")
            location = request.form.get("location")

            # Validate email format
            if not is_valid_email(email):
                flash("Invalid email address", "error")
                return redirect(url_for('index'))

            # Debug print
            print(f"Email: {email}, Service: {service}, Budget: {budget}, Location: {location}")

            # Create email content
            subject = f"New request for {service}"
            content = f"""
Name: {email}
Service: {service}
Budget: {budget}
Location: {location}
"""

            # Send email through SendGrid
            send_email(subject, content)

            flash("Your request has been sent successfully!", "success")
            return redirect(url_for('index'))

        except Exception as e:
            print(f"Error: {e}")
            flash(f"An error occurred: {e}", "error")
            return redirect(url_for('index'))

    return render_template("index.html")

@app.route("/api/test", methods=["GET"])
def test_api():
    return {"status": "ok", "message": "Backend is connected!"}, 200

@app.route("/__debug__/files", methods=["GET"])
def debug_files():
    """
    Debug route: lists files in the deployed container
    """
    root = os.listdir(".")
    templates = os.listdir("templates") if os.path.isdir("templates") else []
    static = os.listdir("static") if os.path.isdir("static") else []
    return jsonify({
        "root": root,
        "templates": templates,
        "static": static
    })

def send_email(subject, content):
    try:
        from_email = Email("hello@zyberfy.com")
        to_email = To("mylescunningham0@gmail.com")
        content = Content("text/plain", content)
        mail = Mail(from_email, to_email, subject, content)

        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = sg.send(mail)

        print(f"SendGrid Response: {response.status_code}")
        print(f"Response Body: {response.body}")
        print(f"Response Headers: {response.headers}")

        return response

    except Exception as e:
        print(f"SendGrid error: {e}")
        raise

def is_valid_email(email):
    email_regex = r"(^[A-Za-z0-9]+[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)"
    return re.match(email_regex, email) is not None

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
<<<<<<< HEAD
    app.run(host="0.0.0.0", port=port, debug=True)
=======
    app.run(host="0.0.0.0", port=port, debug=True)
>>>>>>> 629979d (chore: add debug_files route for deployed structure inspection)
