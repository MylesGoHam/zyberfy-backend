import sqlite3
import os

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

def add_stripe_column_if_missing():
    """Run once at startup to ALTER the users table if needed."""
    conn = get_db_connection()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        # column already exists
        pass
    conn.close()

def create_users_table():
    """Create users table if it doesn’t exist (with stripe_customer_id)."""
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        email                 TEXT UNIQUE,
        password              TEXT,
        first_name            TEXT,
        plan_status           TEXT,
        stripe_customer_id    TEXT
      )
    """)
    conn.commit()
    conn.close()

def create_automation_settings_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automation_settings (
            email TEXT PRIMARY KEY,
            tone TEXT,
            full_auto INTEGER DEFAULT 0,
            accept_offers INTEGER DEFAULT 0,
            reject_offers INTEGER DEFAULT 0,
            length TEXT DEFAULT 'concise'
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
    conn = get_db_connection()
    row = conn.execute(
        "SELECT email, tone, style, additional_notes "
        "FROM automation_settings WHERE email = ?",
        (email,)
    ).fetchone()
    conn.close()
    return row

def create_proposals_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT UNIQUE,
            name TEXT,
            email TEXT,
            company TEXT,
            details TEXT,
            budget TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def log_event(user_email: str, event_type: str):
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
