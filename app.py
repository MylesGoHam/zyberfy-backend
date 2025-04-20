import os
import openai
from flask import Flask, request, render_template, redirect, url_for
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = 'hello@zyberfy.com'  # your verified sender email

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        user_input = request.form["user_input"]
        recipient_email = request.form["recipient_email"]

        # Generate proposal using GPT-3.5-Turbo
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # <-- locked back to 3.5
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that writes professional proposals."},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.7,
                max_tokens=800
            )

            generated_text = response['choices'][0]['message']['content']

            # Send generated text via email
            message = Mail(
                from_email=FROM_EMAIL,
                to_emails=recipient_email,
                subject="Your AI-Generated Proposal",
                html_content=f"<p>{generated_text}</p>"
            )
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            sg.send(message)

            return render_template("thank_you.html")

        except Exception as e:
            print(f"Error: {e}")
            return "Something went wrong. Please try again."

    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
