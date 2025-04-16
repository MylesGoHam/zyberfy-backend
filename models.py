import os
import sqlite3

def get_db_connection():
    db_path = os.environ.get("ZDB_PATH", os.path.join(os.path.abspath(os.path.dirname(__file__)), "zyberfy.db"))
    print("📍 Using DB path:", db_path)  # Optional: helps debug
    conn = sqlite3.connect(db_path)
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
