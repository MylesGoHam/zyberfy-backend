import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "zyberfy.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_automation_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automation_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            subject TEXT,
            greeting TEXT,
            tone TEXT,
            footer TEXT,
            ai_training TEXT,
            accept_msg TEXT,
            decline_msg TEXT,
            proposal_mode TEXT DEFAULT 'concise'
        );
    """)
    conn.commit()
    conn.close()
