# models.py

import sqlite3

DATABASE = 'zyberfy.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def create_users_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

def create_automation_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS automation_settings (
            email TEXT PRIMARY KEY,
            tone TEXT,
            style TEXT,
            additional_notes TEXT,
            enable_follow_up TEXT,
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
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            email TEXT PRIMARY KEY,
            stripe_subscription_id TEXT,
            price_id TEXT
        );
    """)
    conn.commit()
    conn.close()
