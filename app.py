from flask import Flask, request, render_template, redirect, url_for, flash
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from dotenv import load_dotenv
import os
import re

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')  # Ensure you set a secret key for sessions and flashing

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

            # Print form data for debugging
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

            # Flash success message and redirect
            flash("Your request has been sent successfully!", "success")
            return redirect(url_for('index'))  # Redirect back to the form page

        except Exception as e:
            # If an error occurs, catch it and print it in the console for debugging
            print(f"Error: {e}")
            flash(f"An error occurred: {e}", "error")
            return redirect(url_for('index'))  # Redirect back to the form page on error
    
    return render_template("index.html")

def send_email(subject, content):
    try:
        # Replace with your sender and recipient emails
        from_email = Email("hello@zyberfy.com")  # Replace with your sender email
        to_email = To("mylescunningham0@gmail.com")  # Replace with the recipient email
        content = Content("text/plain", content)
        mail = Mail(from_email, to_email, subject, content)

        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = sg.send(mail)

        # Debugging output
        print(f"SendGrid Response: {response.status_code}")
        print(f"Response Body: {response.body}")
        print(f"Response Headers: {response.headers}")

        return response

    except Exception as e:
        # Catch any exceptions in sending the email
        print(f"SendGrid error: {e}")
        raise e  # Re-raise the error to be caught in the index route

def is_valid_email(email):
    # Simple regex for basic email validation
    email_regex = r"(^[A-Za-z0-9]+[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)"
    return re.match(email_regex, email) is not None

if __name__ == "__main__":
    app.run(debug=True)
