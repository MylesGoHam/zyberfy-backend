# test_sms.py

from sms_utils import send_sms_alert

# Replace with your test number (must be verified in Twilio if using trial)
test_number = "2096402828"
test_message = "🚨 Test SMS from Zyberfy backend!"

send_sms_alert(test_number, test_message)
print("✅ Test SMS sent!")
