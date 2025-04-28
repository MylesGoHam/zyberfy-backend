import sqlite3
import os

# use this constant everywhere
DATABASE = os.getenv('DATABASE', 'zyberfy.db')

def get_db_connection():
    conn = sqlite3.connect(
        DATABASE,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def create_users_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email       TEXT UNIQUE    NOT NULL,
        password    TEXT           NOT NULL,
        first_name  TEXT,
        plan_status TEXT
      );
    """)
    conn.commit()
    conn.close()

def create_automation_settings_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS automation_settings (
        email             TEXT PRIMARY KEY,
        tone              TEXT,
        style             TEXT,
        additional_notes  TEXT,
        FOREIGN KEY(email) REFERENCES users(email)
      );
    """)
    conn.commit()
    conn.close()

def create_subscriptions_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS subscriptions (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        email    TEXT NOT NULL,
        plan     TEXT NOT NULL,
        status   TEXT NOT NULL,
        FOREIGN KEY(email) REFERENCES users(email)
      );
    """)
    conn.commit()
    conn.close()

def create_analytics_events_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS analytics_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        event_type TEXT    NOT NULL,
        timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
      );
    """)
    conn.commit()
    conn.close()

def get_user_automation(email: str):
    """Fetch the automation_settings row for this user, or None if not set."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT email, tone, style, additional_notes "
        "FROM automation_settings WHERE email = ?",
        (email,)
    ).fetchone()
    conn.close()
    return row

def log_event(user_email: str, event_type: str):
    """
    Lookup the user_id from users.email, then insert the analytics event.
    """
    conn = get_db_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (user_email,)
    ).fetchone()
    if user:
        conn.execute(
            "INSERT INTO analytics_events (user_id, event_type) VALUES (?, ?)",
            (user['id'], event_type)
        )
        conn.commit()
    conn.close()
