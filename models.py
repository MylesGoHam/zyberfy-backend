import sqlite3
import os
import json
import re
import random
import string
import secrets
from datetime import datetime

DATABASE = os.getenv('DATABASE', 'zyberfy.db')

def get_db_connection():
    conn = sqlite3.connect("/data/zyberfy.db")  # 🔒 persistent storage path
    conn.row_factory = sqlite3.Row
    return conn

def add_is_default_column():
    conn = get_db_connection()
    try:
        conn.execute("ALTER TABLE proposals ADD COLUMN is_default INTEGER DEFAULT 0")
        conn.commit()
        print("[DB] ✅ 'is_default' column added to proposals table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[DB] ℹ️ 'is_default' column already exists.")
        else:
            raise e
    conn.close()

def add_stripe_column_if_missing():
    conn = get_db_connection()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()

def create_users_table():
    conn = get_db_connection()
    conn.execute(""" 
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        first_name TEXT,
        plan_status TEXT,
        stripe_customer_id TEXT
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
            full_auto BOOLEAN,
            accept_offers BOOLEAN,
            reject_offers BOOLEAN,
            length TEXT,
            first_name TEXT,
            company_name TEXT,
            position TEXT,
            website TEXT,
            phone TEXT,
            reply_to TEXT,
            timezone TEXT,
            logo TEXT,
            custom_slug TEXT
        )
    """)
    conn.commit()
    conn.close()

def create_settings_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            email TEXT PRIMARY KEY,
            first_name TEXT,
            company_name TEXT,
            position TEXT,
            website TEXT,
            phone TEXT,
            reply_to TEXT
        )
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

def create_analytics_events_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            user_email TEXT,
            metadata TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def create_offers_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT NOT NULL,
            offer_amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(public_id) REFERENCES proposals(public_id)
        );
    """)
    conn.commit()
    conn.close()

def create_proposals_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT UNIQUE,
            user_email TEXT,
            lead_name TEXT,
            lead_email TEXT,
            lead_company TEXT,
            services TEXT,
            budget TEXT,
            timeline TEXT,
            message TEXT,
            proposal_text TEXT,
            custom_slug TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def generate_public_id(company_name, custom_slug=None):
    base = slugify(custom_slug if custom_slug else company_name)
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{base}-{suffix}"

def generate_short_id(length=6):
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choices(characters, k=length))

def generate_random_public_id(length=6):
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def log_event(event_name, user_email=None, metadata=None):
    print(f"[LOG EVENT] {event_name=} {user_email=} {metadata=}")
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO analytics_events (event_name, user_email, metadata, timestamp) VALUES (?, ?, ?, ?)",
        (event_name, user_email, json.dumps(metadata or {}), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_user_automation(email: str):
    conn = get_db_connection()
    row = conn.execute("""
        SELECT tone, full_auto, accept_offers, reject_offers, length,
               first_name, company_name, position, website, phone, reply_to, timezone, logo, custom_slug
        FROM automation_settings
        WHERE email = ?
    """, (email,)).fetchone()
    conn.close()
    return row

def handle_new_proposal(name, email, company, services, budget, timeline, message, client_email):
    try:
        conn = get_db_connection()

        # ✅ Enforce 3-proposal limit for non-Elite users
        count_row = conn.execute("SELECT COUNT(*) AS cnt FROM proposals WHERE user_email = ?", (client_email,)).fetchone()
        if count_row["cnt"] >= 3:
            conn.close()
            return "LIMIT_REACHED"

        # ✅ Get client’s branding info
        branding = conn.execute(
            "SELECT company_name, custom_slug FROM automation_settings WHERE email = ?",
            (client_email,)
        ).fetchone()

        company_name = branding["company_name"] if branding else "client"
        custom_slug = branding["custom_slug"] if branding else None

        public_id = generate_public_id(company_name, custom_slug)

        print(f"[SQL] Saving proposal with public_id: {public_id} for client: {client_email}")

        conn.execute("""
            INSERT INTO proposals (
                public_id, user_email, lead_name, lead_email, lead_company,
                services, budget, timeline, message, custom_slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            public_id, client_email, name, email, company,
            services, budget, timeline, message, custom_slug
        ))
        conn.commit()
        conn.close()

        return public_id

    except Exception as e:
        print(f"[ERROR] Failed to handle proposal: {e}")
        return None
