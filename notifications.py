import os
import requests
from models import get_db_connection, log_event  # Make sure get_db_connection is imported

def send_onesignal_notification(title, message, user_email=None, public_id=None):
    # ✅ Check if user has notifications enabled
    if user_email:
        conn = get_db_connection()
        user = conn.execute("SELECT notifications_enabled FROM users WHERE email = ?", (user_email,)).fetchone()
        conn.close()

        if not user or not user["notifications_enabled"]:
            print(f"[🔕] Skipping push — notifications disabled for {user_email}")
            return

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {os.getenv('ONESIGNAL_REST_API_KEY')}"
    }

    payload = {
        "app_id": os.getenv("ONESIGNAL_APP_ID"),
        "included_segments": ["All"] if not user_email else [],
        "include_external_user_ids": [user_email] if user_email else [],
        "headings": {"en": title},
        "contents": {"en": message},
        "url": f"https://zyberfy.com/proposal_view/{public_id}" if public_id else None
    }

    response = requests.post("https://onesignal.com/api/v1/notifications", json=payload, headers=headers)
    print("[OneSignal] Status:", response.status_code, response.json())

    # ✅ Log push event
    log_event(
        event_name="push_sent",
        user_email=user_email,
        metadata={
            "public_id": public_id,
            "title": title,
            "message": message
        }
    )
