import sqlite3
import os

# Correct database path regardless of working directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "zyberfy.db")
print("📍 Using DB path:", DB_PATH)

import os
import sqlite3

def get_db_connection():
    db_path = os.environ.get("ZDB_PATH", "zyberfy.db")
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
