import os
import requests
from models import log_event  # make sure this import is at the top

def send_onesignal_notification(title, message, public_id=None):
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {os.getenv('ONESIGNAL_REST_API_KEY')}"
    }

    payload = {
        "app_id": os.getenv("ONESIGNAL_APP_ID"),
        "included_segments": ["All"],
        "headings": {"en": title},
        "contents": {"en": message}
    }

    response = requests.post("https://onesignal.com/api/v1/notifications", json=payload, headers=headers)
    print("[OneSignal] Status:", response.status_code, response.json())

    # ✅ Log push event
    if public_id:
        log_event(
            event_name="push_sent",
            user_email=None,
            metadata={
                "public_id": public_id,
                "title": title,
                "message": message
            }
        )
