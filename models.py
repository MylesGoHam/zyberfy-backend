# models.py

import sqlite3

def get_db_connection():
    conn = sqlite3.connect('zyberfy.db')
    conn.row_factory = sqlite3.Row
    return conn

def create_automation_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS automation_settings (
            email TEXT PRIMARY KEY,
            tone TEXT,
            style TEXT,
            additional_notes TEXT
        );
    """)
    conn.commit()
    conn.close()
