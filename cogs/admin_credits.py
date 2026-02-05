import discord
from discord.ext import commands
from discord import Interaction, app_commands, Embed
from typing import Optional

from config import ADMIN_ROLES
from database import get_db_connection

class AdminCredits(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    admin_credit = app_commands.Group(name="admin_credit", description="管理者用のクレジット操作コマンド", guild_only=True)

    @admin_credit.command(name="set", description="ユーザーのGTVクレジットを指定した額に設定します。")
    @app_commands.describe(user="対象ユーザー", amount="設定する額 (0以上)")
    @app_commands.rename(user='ユーザー', amount='額')
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def admin_credit_set(self, interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 0]):
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, credits) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET credits = %s;
                """, (user.id, amount, amount))
            conn.commit()
            await interaction.response.send_message(f"{user.display_name} さんのクレジットを `{amount}` GTVに設定しました。", ephemeral=True)
        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error on /admin_credit set: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        finally:
            if conn: conn.close()

    @admin_credit.command(name="add", description="ユーザーのGTVクレジットを指定した額だけ増やします。")
    @app_commands.describe(user="対象ユーザー", amount="増やす額 (1以上)")
    @app_commands.rename(user='ユーザー', amount='額')
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def admin_credit_add(self, interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, credits) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET credits = users.credits + %s;
                """, (user.id, amount, amount))
            conn.commit()
            await interaction.response.send_message(f"{user.display_name} さんのクレジットに `{amount}` GTVを追加しました。", ephemeral=True)
        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error on /admin_credit add: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        finally:
            if conn: conn.close()

    @admin_credit.command(name="remove", description="ユーザーのGTVクレジットを指定した額だけ減らします。")
    @app_commands.describe(user="対象ユーザー", amount="減らす額 (1以上)")
    @app_commands.rename(user='ユーザー', amount='額')
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def admin_credit_remove(self, interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT credits FROM users WHERE user_id = %s;", (user.id,))
                user_data = cur.fetchone()
                current_credits = user_data[0] if user_data and user_data[0] is not None else 0
                if current_credits < amount:
                    await interaction.response.send_message(f"残高不足です。{user.display_name}さんの所持クレジットは `{current_credits}` GTVです。", ephemeral=True)
                    return

                cur.execute("UPDATE users SET credits = credits - %s WHERE user_id = %s;", (amount, user.id))
            conn.commit()
            await interaction.response.send_message(f"{user.display_name} さんのクレジットから `{amount}` GTVを削除しました。", ephemeral=True)
        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error on /admin_credit remove: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        finally:
            if conn: conn.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCredits(bot))
