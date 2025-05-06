# migrations/add_public_id_column.py
import sqlite3

conn = sqlite3.connect("zyberfy.db")

try:
    conn.execute("ALTER TABLE users ADD COLUMN public_id TEXT")
    conn.commit()
    print("✅ public_id column added successfully.")
except sqlite3.OperationalError as e:
    print(f"⚠️ Skipped: {e}")
finally:
    conn.close()
