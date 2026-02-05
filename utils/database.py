import os
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse

def get_db_connection():
    """データベースへの接続を取得します（Render対応）"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set.")

    result = urlparse(database_url)

    return psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode="require"
    )

def setup_database():
    """データベースのテーブルをセットアップします。"""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
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
                last_daily TIMESTAMP WITH TIME ZONE,
                last_taxed_credits INT DEFAULT 0,
                dmps_player_id TEXT,
                dmps_rank INT,
                dmps_points INT
            )
        """)

        # 存在しない可能性のあるカラムを追加
        columns_to_add = {
            "credits": "INT DEFAULT 0",
            "last_daily": "TIMESTAMP WITH TIME ZONE",
            "last_taxed_credits": "INT DEFAULT 0",
            "dmps_player_id": "TEXT",
            "dmps_rank": "INT",
            "dmps_points": "INT"
        }

        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users'
        """)
        existing_columns = [row[0] for row in cur.fetchall()]

        for col, col_type in columns_to_add.items():
            if col not in existing_columns:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type};")

    conn.commit()
    conn.close()

def get_user_profile(user_id: int):
    """指定されたユーザーIDのプロフィールデータを取得します。"""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            "SELECT * FROM users WHERE user_id = %s",
            (user_id,)
        )
        user_data = cur.fetchone()
    conn.close()
    return user_data
