# init_automation.py

import sqlite3

def create_automation_table():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS automation_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            ai_tone TEXT,
            subject_line TEXT,
            greeting_line TEXT,
            closing_line TEXT,
            minimum_offer INTEGER,
            acceptance_message TEXT,
            decline_message TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ automation_settings table created (or already exists).")

if __name__ == "__main__":
    create_automation_table()
