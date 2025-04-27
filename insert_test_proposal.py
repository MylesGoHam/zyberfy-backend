import sqlite3
import uuid
from datetime import datetime

conn = sqlite3.connect("zyberfy.db")
cursor = conn.cursor()

public_id = str(uuid.uuid4())
cursor.execute("""
    INSERT INTO proposals (
        user_email, lead_name, lead_email, lead_company,
        services, budget, timeline, message, proposal_text,
        created_at, public_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "hello@zyberfy.com",  # Make sure this matches a valid client in your DB
    "Test Lead",
    "lead@example.com",
    "Test Co.",
    "Luxury concierge",
    "$5000",
    "2 weeks",
    "Looking for luxury help",
    "This is a test AI-generated proposal text.",
    datetime.utcnow(),
    public_id
))

conn.commit()
conn.close()

print("✅ Inserted test proposal")
print("🔗 Public URL: http://127.0.0.1:5000/proposal/" + public_id)