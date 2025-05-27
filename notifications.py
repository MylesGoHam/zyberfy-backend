# notifications.py
import requests
import os

def send_onesignal_notification(title, message, public_id=None, proposal_id=None):
    api_key = os.getenv("ONESIGNAL_API_KEY")
    app_id = os.getenv("ONESIGNAL_APP_ID")

    if not api_key or not app_id:
        print("❌ [OneSignal] Missing ONESIGNAL_API_KEY or ONESIGNAL_APP_ID.")
        return

    if not public_id:
        print("❌ [OneSignal] Missing public_id for notification URL.")
        return

    url = f"https://zyberfy.com/proposal/{public_id}"

    data = {
        "app_id": app_id,
        "headings": {"en": title},
        "contents": {"en": message},
        "url": url,
        "included_segments": ["All"],  # Can later target specific users with external_user_ids
        "data": {
            "public_id": public_id,
            "proposal_id": proposal_id
        }
    }

    try:
        response = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers={
                "Authorization": f"Basic {api_key}",
                "Content-Type": "application/json"
            },
            json=data
        )

        if response.status_code == 200:
            print("✅ [OneSignal] Notification sent successfully.")
        else:
            print(f"⚠️ [OneSignal] Failed with status {response.status_code}: {response.text}")

    except Exception as e:
        print("❌ [OneSignal] Exception occurred:", e)
