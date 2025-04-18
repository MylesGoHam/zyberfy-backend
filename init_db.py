import sqlite3

def initialize_database():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Create subscriptions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        email TEXT PRIMARY KEY,
        stripe_subscription_id TEXT,
        first_name TEXT,
        last_name TEXT,
        business_name TEXT,
        business_type TEXT
    )
    ''')

    # Create automation_settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS automation_settings (
        email TEXT PRIMARY KEY,
        tone TEXT,
        style TEXT,
        additional_notes TEXT,
        enable_follow_up TEXT,
        number_of_followups TEXT,
        followup_delay TEXT,
        followup_style TEXT,
        minimum_offer TEXT,
        acceptance_message TEXT,
        decline_message TEXT
    )
    ''')

    conn.commit()
    conn.close()
    print("✅ database.db initialized successfully!")

if __name__ == "__main__":
    initialize_database()