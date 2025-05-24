from models import log_event, get_db_connection
import os
import requests

def send_onesignal_notification(title, message, public_id=None, proposal_id=None, user_email=None):
    # ✅ Respect user settings: only send if notifications are enabled
    if user_email:
        conn = get_db_connection()
        user = conn.execute("SELECT notifications_enabled FROM users WHERE email = ?", (user_email,)).fetchone()
        conn.close()
        if user and user["notifications_enabled"] == 0:
            print(f"[OneSignal] Skipped — user {user_email} has push disabled")
            return  # ❌ Exit early

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

    # ✅ Add dynamic redirect link
    if proposal_id:
        payload["url"] = f"https://zyberfy.com/proposal_view/{proposal_id}"

    response = requests.post("https://onesignal.com/api/v1/notifications", json=payload, headers=headers)
    print("[OneSignal] Status:", response.status_code, response.json())

    # ✅ Log event
    if public_id:
        log_event(
            event_name="push_sent",
            user_email=user_email,
            metadata={
                "public_id": public_id,
                "title": title,
                "message": message
            }
        )
