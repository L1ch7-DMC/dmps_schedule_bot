import discord
from discord.ext import commands
import os
from discord import app_commands

from config import TOKEN_MAIN, DATABASE_URL
from database import setup_database

from cogs.profile import Profile
from cogs.dmps_info import DMPSInfo
from cogs.general import General
from cogs.admin_profile import AdminProfile

from tasks.tournament_notifier import check_tournaments_today
from tasks.birthday_notifier import check_birthdays_today


class MainBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # intents.members = True  # ← 使ってないならコメントアウト（重要）
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("Setting up database...")
        try:
            setup_database()
            print("Database setup successful.")
        except Exception as e:
            print(f"Database setup failed: {e}")
            raise e  # ← 失敗時は即落とす（無限再起動防止）

        print("Loading cogs...")
        await self.add_cog(Profile(self))
        await self.add_cog(DMPSInfo(self))
        await self.add_cog(General(self))
        await self.add_cog(AdminProfile(self))

        # ===== コマンド同期は「必要な時だけ」 =====
        if os.getenv("SYNC_COMMANDS") == "true":
            print("Syncing commands...")
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        else:
            print("Skip command sync")

        print("Starting tasks...")
        if not check_tournaments_today.is_running():
            check_tournaments_today.start(self)
        if not check_birthdays_today.is_running():
            check_birthdays_today.start(self)

    async def on_ready(self):
        print(f"Main Bot Logged in as {self.user}")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。",
                ephemeral=True
            )
        else:
            print(f"App command error: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "コマンドの実行中にエラーが発生しました。",
                    ephemeral=True
                )


if __name__ == "__main__":
    if not TOKEN_MAIN:
        print("TOKEN_MAIN が設定されていません")
        exit(1)

    if not DATABASE_URL:
        print("DATABASE_URL が設定されていません")
        exit(1)

    bot = MainBot()
    bot.run(TOKEN_MAIN, reconnect=False)
