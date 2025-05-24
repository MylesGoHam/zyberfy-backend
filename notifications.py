def send_onesignal_notification(title, message, public_id=None, proposal_id=None):
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

    # ✅ Add the target URL to direct to the receipt
    if proposal_id:
        payload["url"] = f"https://zyberfy.com/proposal_view/{proposal_id}"

    response = requests.post("https://onesignal.com/api/v1/notifications", json=payload, headers=headers)
    print("[OneSignal] Status:", response.status_code, response.json())

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
