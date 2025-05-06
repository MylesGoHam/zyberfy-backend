# migrations/add_public_id_column.py

import sqlite3

def add_public_id_column():
    conn = sqlite3.connect("zyberfy.db")
    cursor = conn.cursor()

    # Check if 'public_id' column already exists
    cursor.execute("PRAGMA table_info(proposals);")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "public_id" not in columns:
        cursor.execute("ALTER TABLE proposals ADD COLUMN public_id TEXT;")
        conn.commit()
        print("[MIGRATION] public_id column added to proposals table.")
    else:
        print("[MIGRATION] public_id column already exists.")

    conn.close()

if __name__ == "__main__":
    add_public_id_column()