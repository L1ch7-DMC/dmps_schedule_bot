import os
import asyncio
import discord
from discord.ext import commands
import threading
from flask import Flask

# --- ローカルモジュールのインポート ---
from config import TOKEN, DATABASE_URL
from utils.database import setup_database

# --- Flask (Keep Alive) ---
# RenderなどのホスティングサービスでBotを常時起動させるための簡易的なWebサーバー
app = Flask(__name__)
@app.route('/')
def home():
    return "Discord bot is running!"

def run_flask():
    # 環境変数 PORT があればそれを、なければ5000番ポートを使用
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def keep_alive_thread():
    """Flaskアプリを別スレッドで実行する"""
    t = threading.Thread(target=run_flask)
    t.daemon = True # メインスレッドが終了したらこのスレッドも終了する
    t.start()

# --- Botのセットアップ ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True # メンバー情報の取得を有効化
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """Bot起動時に最初に実行される処理"""
        # cogsフォルダから拡張機能をロード
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f'Loaded cog: {filename[:-3]}')
                except Exception as e:
                    print(f'Failed to load cog {filename[:-3]}: {e}')
        
        # データベースのセットアップ
        try:
            setup_database()
            print("Database setup successful.")
        except Exception as e:
            print(f"Database setup failed: {e}")

    async def on_ready(self):
        """Botの準備が完了したときのイベント"""
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')
        
        # スラッシュコマンドをDiscordサーバーに同期
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

# --- メイン実行ブロック ---
if __name__ == '__main__':
    # 必須の環境変数が設定されているか確認
    if TOKEN is None:
        print("エラー: .envファイルで DISCORD_BOT_TOKEN を設定してください。")
    elif DATABASE_URL is None:
        print("エラー: .envファイルまたは環境変数で DATABASE_URL を設定してください。")
    else:
        # Botを起動
        bot = MyBot()
        
        # Keep-aliveスレッドを開始
        keep_alive_thread()
        
        # Botを非同期で実行
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("エラー: 不正なDiscordボットトークンです。 .env ファイルを確認してください。")
        except Exception as e:
            print(f"Botの実行中に予期せぬエラーが発生しました: {e}")