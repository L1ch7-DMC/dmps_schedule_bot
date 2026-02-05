import discord
from discord.ext import commands
import os
import asyncio

from config import TOKEN, DATABASE_URL
from database import setup_database
from keep_alive import keep_alive_thread

from cogs.profile import Profile
from cogs.dmps_info import DMPSInfo
from cogs.general import General
from cogs.admin_profile import AdminProfile

from tasks.tournament_notifier import check_tournaments_today
from tasks.birthday_notifier import check_birthdays_today

class MainBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("Setting up database...")
        try:
            setup_database()
            print("Database setup successful.")
        except Exception as e:
            print(f"Database setup failed: {e}")

        print("Loading cogs...")
        await self.add_cog(Profile(self))
        await self.add_cog(DMPSInfo(self))
        await self.add_cog(General(self))
        await self.add_cog(AdminProfile(self))
        
        print("Syncing commands...")
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

        print("Starting tasks...")
        if not check_tournaments_today.is_running():
            check_tournaments_today.start(self)
        if not check_birthdays_today.is_running():
            check_birthdays_today.start(self)

    async def on_ready(self):
        print(f'Main Bot Logged in as {self.user}')

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        else:
            print(f"An app command error occurred in Main Bot: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("コマンドの実行中にエラーが発生しました。", ephemeral=True)

if __name__ == '__main__':
    if TOKEN is None:
        print("エラー: .envファイルで DISCORD_BOT_TOKEN を設定してください。")
    elif DATABASE_URL is None:
        print("エラー: .envファイルまたは環境変数で DATABASE_URL を設定してください。")
    else:
        keep_alive_thread() # Start Flask server for keep-alive
        bot = MainBot()
        bot.run(TOKEN)
