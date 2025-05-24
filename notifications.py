import os
import requests

def send_onesignal_notification(title, message):
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