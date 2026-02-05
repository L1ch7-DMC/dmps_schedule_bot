import os
import discord
from discord.ext import commands
import threading
from flask import Flask

from config import TOKEN, DATABASE_URL
from utils.database import setup_database

# --- Flask (Keep Alive) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def keep_alive_thread():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

# --- Bot ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """起動時に1回だけ呼ばれる（超重要）"""

        # Cogsロード
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f'Loaded cog: {filename[:-3]}')
                except Exception as e:
                    print(f'Failed to load cog {filename[:-3]}: {e}')

        # DBセットアップ
        try:
            setup_database()
            print("Database setup successful.")
        except Exception as e:
            print(f"Database setup failed: {e}")

        # 🔥 スラッシュコマンド同期はここで1回だけ
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Command sync failed: {e}")

    async def on_ready(self):
        # ここでは表示だけ
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

# --- Main ---
if __name__ == '__main__':
    if TOKEN is None:
        print("エラー: DISCORD_BOT_TOKEN が未設定です")
    elif DATABASE_URL is None:
        print("エラー: DATABASE_URL が未設定です")
    else:
        keep_alive_thread()
        bot = MyBot()
        bot.run(TOKEN)
