# test_sms.py

from sms_utils import send_sms_alert

# Replace with your test number (must be verified in Twilio if using trial)
test_number = "+12096402828"
test_message = "🚨 Test SMS from Zyberfy backend!"

send_sms_alert(test_number, test_message)
<<<<<<< HEAD
print("✅ Test SMS sent!")
=======
print("✅ Test SMS sent!")
>>>>>>> 803d2a8 (Update backend files and database for test client)
