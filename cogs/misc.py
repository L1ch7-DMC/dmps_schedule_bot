
import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from datetime import datetime

from config import JST, BIRTHDAY_NOTIFY_TIME, BIRTHDAY_CHANNEL_ID
from utils.database import get_db_connection

class MiscCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_birthdays_today.start()

    def cog_unload(self):
        self.check_birthdays_today.cancel()

    @app_commands.command(name="note", description="メンバー紹介noteのURLを送信します。")
    async def note_slash(self, interaction: Interaction):
        await interaction.response.send_message("GTVメンバー紹介noteだ！\nhttps://note.com/koresute_0523/n/n1b3bf9754432")

    @tasks.loop(time=BIRTHDAY_NOTIFY_TIME)
    async def check_birthdays_today(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(BIRTHDAY_CHANNEL_ID)
        if not channel:
            print(f"Error: Birthday notification channel ID {BIRTHDAY_CHANNEL_ID} not found.")
            return

        today_str = datetime.now(JST).strftime('%m-%d')
        
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=discord.psycopg2.extras.DictCursor) as cur:
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
                    await channel.send(message)
            conn.commit()
        except Exception as e:
            print(f"DB Error in birthday task: {e}")
        finally:
            if conn: conn.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(MiscCog(bot))
