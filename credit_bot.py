import discord
from discord.ext import commands
import os
import asyncio

from config import TOKEN, DATABASE_URL
from database import setup_database
from cogs.games import Games
from cogs.admin_credits import AdminCredits
from tasks.income_tax import collect_income_tax
from tasks.dmps_credit_updater import dmps_credit_updater

class CreditBot(commands.Bot):
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
        await self.add_cog(Games(self))
        await self.add_cog(AdminCredits(self))
        
        print("Syncing commands...")
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

        print("Starting tasks...")
        if not collect_income_tax.is_running():
            collect_income_tax.start(self)
        if not dmps_credit_updater.is_running():
            dmps_credit_updater.start(self)

    async def on_ready(self):
        print(f'Credit Bot Logged in as {self.user}')

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        else:
            print(f"An app command error occurred in Credit Bot: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("コマンドの実行中にエラーが発生しました。", ephemeral=True)

if __name__ == '__main__':
    if TOKEN is None:
        print("エラー: .envファイルで DISCORD_BOT_TOKEN を設定してください。")
    elif DATABASE_URL is None:
        print("エラー: .envファイルまたは環境変数で DATABASE_URL を設定してください。")
    else:
        bot = CreditBot()
        bot.run(TOKEN)
