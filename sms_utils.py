# sms_utils.py
from twilio.rest import Client
import os
from dotenv import load_dotenv
from analytics import log_event

load_dotenv()

def send_sms_alert(to_number, message, user_email=None):
    try:
        client = Client(
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN")
        )

        client.messages.create(
            messaging_service_sid=os.getenv("TWILIO_MESSAGING_SERVICE_SID"),
            to=to_number,
            body=message
        )

        if user_email:
            log_event("sms_sent", user_email=user_email, details={"to": to_number, "message": message})

        print(f"[SMS SENT] to {to_number}")
        return True

    except Exception as e:
        print(f"[SMS ERROR] {e}")
        return False