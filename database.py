import psycopg2
import psycopg2.extras
import os
from .config import DATABASE_URL, PROFILE_ITEMS

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(DATABASE_URL)

def setup_database():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                top100 INT,
                nd_rate INT,
                ad_rate INT,
                player_id BIGINT,
                achievements TEXT,
                age INT,
                birthday VARCHAR(5),
                credits INT DEFAULT 0,
                last_daily TIMESTAMP WITH TIME ZONE
            )
        ''')
        # For existing tables, add columns if they don't exist
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INT DEFAULT 0;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily TIMESTAMP WITH TIME ZONE;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_taxed_credits INT DEFAULT 0;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dmps_player_id TEXT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dmps_rank INT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dmps_points INT;")
    conn.commit()
    conn.close()

def get_user_profile(user_id):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user_data = cur.fetchone()
    conn.close()
    return user_data
