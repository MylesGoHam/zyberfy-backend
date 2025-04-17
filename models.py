import sqlite3

# Connect to database
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Create automation_settings table
def create_automation_table():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS automation_settings (
            email TEXT PRIMARY KEY,
            tone TEXT,
            style TEXT,
            additional_notes TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Create subscriptions table
def create_subscriptions_table():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            email TEXT PRIMARY KEY,
            stripe_subscription_id TEXT,
            price_id TEXT
        )
    ''')
    conn.commit()
    conn.close()
