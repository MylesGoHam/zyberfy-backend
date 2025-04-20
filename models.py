# models.py

import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_FILE = os.getenv("DATABASE_FILE", "zyberfy.db")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_users_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT   PRIMARY KEY,
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
            email TEXT   PRIMARY KEY,
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
            id INTEGER   PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            plan TEXT,
            status TEXT,
            FOREIGN KEY(email) REFERENCES users(email)
        );
    """)
    conn.commit()
    conn.close()
