from models import get_db_connection
from datetime import datetime

def log_event(event_type, user_email=None, details=None):
    try:
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO analytics_events (event_type, user_email, details, timestamp)
            VALUES (?, ?, ?, ?)
        """, (
            event_type,
            user_email,
            str(details) if details else "",
            datetime.utcnow()
        ))
        conn.commit()
        conn.close()
        print(f"[ANALYTICS] Logged event: {event_type}")
    except Exception as e:
        print(f"[ANALYTICS ERROR] {e}")