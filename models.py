# models.py
import sqlite3

DB_PATH = 'zyberfy.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_users_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        password TEXT NOT NULL
      );
    """)
    # seed one default user:
    conn.execute("""
      INSERT OR IGNORE INTO users (email, password)
      VALUES (?, ?);
    """, ("admin@zyberfy.com", "admin"))
    conn.commit()
    conn.close()

def create_automation_settings_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS automation_settings (
        email TEXT PRIMARY KEY,
        tone TEXT,
        style TEXT,
        additional_notes TEXT,
        enable_follow_up BOOLEAN,
        number_of_followups INTEGER,
        followup_delay TEXT,
        followup_style TEXT,
        minimum_offer REAL,
        acceptance_message TEXT,
        decline_message TEXT
      );
    """)
    conn.commit()
    conn.close()

def create_subscriptions_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        plan TEXT,
        started_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );
    """)
    conn.commit()
    conn.close()
