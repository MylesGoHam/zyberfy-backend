# email_utils.py
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Load API key
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = "hello@zyberfy.com"  # ✅ Hardcoded sender

def send_proposal_email(to_email, subject, content, cc_client=False, client_email=None):
    # Format plain text to HTML
    formatted_html = content.replace('\n', '<br>')

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 640px; margin: auto; padding: 20px;">
          {formatted_html}
        </div>
      </body>
    </html>
    """

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        plain_text_content=content,
        html_content=html_body
    )

    if cc_client and client_email:
        message.add_cc(client_email)

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"[SENDGRID] Email sent to {to_email} | Status: {response.status_code}")
        return response.status_code
    except Exception as e:
        print(f"[SENDGRID] Failed to send email: {e}")
        return None
