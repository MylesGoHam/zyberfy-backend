import sqlite3
import os

# use this constant everywhere
DATABASE = os.getenv('DATABASE', 'zyberfy.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def create_users_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        first_name TEXT,
        plan_status TEXT
      );
    """)
    conn.commit()
    conn.close()

def create_automation_settings_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS automation_settings (
        email TEXT PRIMARY KEY,
        tone TEXT,
        style TEXT,
        additional_notes TEXT
      );
    """)
    conn.commit()
    conn.close()

def create_subscriptions_table():
    conn = get_db_connection()
    conn.execute("""
      CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        plan TEXT NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY(email) REFERENCES users(email)
      );
    """)
    conn.commit()
    conn.close()
