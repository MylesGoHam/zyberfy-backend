# email_utils.py
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
from dotenv import load_dotenv

load_dotenv()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@zyberfy.com")

def send_proposal_email(to_email, subject, content, cc_client=False, client_email=None):
    formatted_html = content.replace('\n', '<br>')
    html_body = f"""
    <html><body style="font-family:Arial,sans-serif">
      <div style="max-width:640px;margin:auto;padding:20px">
        {formatted_html}
      </div>
    </body></html>
    """
    msg = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        plain_text_content=content,
        html_content=html_body
    )
    if cc_client and client_email:
        msg.add_cc(client_email)
    sg = SendGridAPIClient(SENDGRID_API_KEY)
    return sg.send(msg)

# Alias for app.py
send_email = send_proposal_email
