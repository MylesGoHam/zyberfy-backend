import sqlite3

def upgrade_subscriptions_table():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE subscriptions ADD COLUMN first_name TEXT;")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE subscriptions ADD COLUMN last_name TEXT;")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE subscriptions ADD COLUMN business_name TEXT;")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE subscriptions ADD COLUMN business_type TEXT;")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

if __name__ == "__main__":
    upgrade_subscriptions_table()