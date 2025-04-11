import openai
import os
from dotenv import load_dotenv
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content

# Load environment variables from the .env file
load_dotenv()

# OpenAI API key setup
openai.api_key = os.getenv("OPENAI_API_KEY")

# SendGrid API key setup
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

# Function to generate an email reply using OpenAI's GPT model
def generate_reply(email_input, tone, sender_email, recipient_name):
    # Clean name inputs
    sender_name = sender_email.split("@")[0].capitalize()
    recipient_display = recipient_name.strip() if recipient_name else "Customer"

    # Create the prompt for OpenAI
    prompt = f"""
    You are an AI email assistant helping write a reply.

    - Use a {tone.lower()} tone.
    - Address the recipient as: Dear {recipient_display}
    - Sign off with: {sender_name}

    Here is the email you're replying to:
    "{email_input}"

    Now write a clear and helpful reply:
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message["content"].strip()

    except Exception as e:
        return f"Error generating reply: {str(e)}"

# Function to send an email using SendGrid
def send_email(subject, recipient_email, body_content):
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    from_email = Email("hello@zyberfy.com")  # Replace with your email
    to_email = To(recipient_email)
    content = Content("text/plain", body_content)
    mail = Mail(from_email, subject, to_email, content)

    try:
        response = sg.send(mail)
        return response.status_code, response.body, response.headers
    except Exception as e:
        return f"Error sending email: {str(e)}"

if __name__ == "__main__":
    # Example usage
    email_input = "Hello, I need help with my order. Can you assist me?"
    tone = "friendly"
    sender_email = "customer@example.com"
    recipient_name = "Support Team"

    reply = generate_reply(email_input, tone, sender_email, recipient_name)
    print(f"Generated Reply: {reply}")

    # Send the reply via email
    subject = "Re: Help with Order"
    recipient_email = "support@yourcompany.com"
    status_code, response_body, response_headers = send_email(subject, recipient_email, reply)
    print(f"Email Sent with status code: {status_code}")
