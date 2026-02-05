import discord
from discord.ext import tasks, commands
from datetime import datetime
import psycopg2.extras

from ..config import JST, BIRTHDAY_NOTIFY_TIME, BIRTHDAY_CHANNEL_ID
from ..database import get_db_connection

@tasks.loop(time=BIRTHDAY_NOTIFY_TIME)
async def check_birthdays_today(bot: commands.Bot):
    await bot.wait_until_ready()
    channel = bot.get_channel(BIRTHDAY_CHANNEL_ID)
    if not channel:
        print(f"Error: Birthday notification channel ID {BIRTHDAY_CHANNEL_ID} not found.")
        return

    today_str = datetime.now(JST).strftime('%m-%d')
    
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT user_id, age FROM users WHERE birthday = %s", (today_str,))
            birthday_users = cur.fetchall()

            if birthday_users:
                user_ids_to_update = [user['user_id'] for user in birthday_users if user['age'] is not None]
                if user_ids_to_update:
                    cur.execute("UPDATE users SET age = age + 1 WHERE user_id = ANY(%s)", (user_ids_to_update,))
                    print(f"[LOG] Incremented age for users: {user_ids_to_update}")

                mentions = [f"<@{user['user_id']}>" for user in birthday_users]
                message = (f"@everyone\n🎉🎂ハッピーバースデー！🎂🎉\n"
                           f"今日は {', '.join(mentions)} さんのお誕生日だ！みんなでお祝いするぞ！🥳")
                await channel.send("".join(message))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error in birthday task: {e}")
