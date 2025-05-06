import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

def send_sms_alert(to_number, message):
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        twilio_number = os.getenv("TWILIO_PHONE_NUMBER")

        client = Client(account_sid, auth_token)
        client.messages.create(
            body=message,
            from_=twilio_number,
            to=to_number
        )
        print(f"[SMS] Sent to {to_number}")
    except Exception as e:
        print(f"[SMS ERROR] Failed to send: {e}")