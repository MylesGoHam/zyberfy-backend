# notifications.py
import requests
import os

def send_onesignal_notification(title, message, public_id, proposal_id=None):
    api_key = os.getenv("ONESIGNAL_API_KEY")
    app_id = os.getenv("ONESIGNAL_APP_ID")

    if not api_key or not app_id:
        print("[OneSignal] Missing credentials.")
        return

    data = {
        "app_id": app_id,
        "headings": {"en": title},
        "contents": {"en": message},
        "url": f"https://zyberfy.com/proposal/{public_id}",
        "included_segments": ["All"]
    }

    try:
        res = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers={
                "Authorization": f"Basic {api_key}",
                "Content-Type": "application/json"
            },
            json=data
        )
        print("[OneSignal] ✅ Notification sent:", res.status_code)
    except Exception as e:
        print("[OneSignal] ❌ Failed:", e)
