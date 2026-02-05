

import discord
from discord import app_commands, Embed, Interaction
from discord.ext import commands
from typing import Optional

from config import PROFILE_ITEMS, NUMERIC_ITEMS, ADMIN_ROLES
from utils.database import get_db_connection, get_user_profile
from utils.ui_views import RegisterView
import re

class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="register", description="あなたのプロフィール情報を登録・更新します。")
    async def register_slash(self, interaction: Interaction):
        await interaction.response.send_message("登録したい情報の種類を選んでください。", view=RegisterView(target_user=interaction.user), ephemeral=True)

    @app_commands.command(name="profile", description="メンバーの情報を表示します。")
    @app_commands.describe(user="情報を表示したいメンバー (指定がなければ自分)")
    async def profile_slash(self, interaction: Interaction, user: Optional[discord.Member] = None):
        target_user = user or interaction.user
        user_data = get_user_profile(target_user.id)
        
        if not user_data or not any(user_data.get(key) for key in PROFILE_ITEMS):
            message = f"{target_user.display_name}の情報はまだ登録されていないぞ。" + ("\n`/register`で登録してみよう！" if target_user == interaction.user else "")
            await interaction.response.send_message(message, ephemeral=True); return

        embed = Embed(title=f"{target_user.display_name}のプロフィール", color=target_user.color).set_thumbnail(url=target_user.display_avatar.url)
        for key, label in PROFILE_ITEMS.items():
            if key in user_data and user_data[key] is not None:
                embed.add_field(name=label, value=user_data[key], inline=True)

        if user_data.get('dmps_rank') is not None and user_data.get('dmps_points') is not None:
            embed.add_field(name="DMPSランキング", value=f"`{user_data['dmps_rank']}`位", inline=True)
            embed.add_field(name="DMPSポイント", value=f"`{user_data['dmps_points']}`pt", inline=True)

        credits = user_data.get('credits', 0)
        embed.add_field(name="所持GTV", value=f"**`{credits}`** GTV", inline=False)
        
        await interaction.response.send_message(embed=embed)

    # --- 管理者用コマンドグループ ---
    profile_admin = app_commands.Group(name="profile_admin", description="管理者用のプロフィール操作コマンド")

    @profile_admin.command(name="edit", description="指定したユーザーの情報を対話形式で編集します。")
    @app_commands.describe(user="情報を編集するユーザー")
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def profile_admin_edit(self, interaction: Interaction, user: discord.Member):
        await interaction.response.send_message(f"{user.display_name}の情報を編集するぞ！", view=RegisterView(target_user=user), ephemeral=True)

    @profile_admin.command(name="set", description="[旧] 指定したユーザーの情報を項目ごとに変更します。")
    @app_commands.describe(user="情報を変更するユーザー", item="変更する項目", value="新しい値")
    @app_commands.choices(item=[app_commands.Choice(name=label, value=key) for key, label in PROFILE_ITEMS.items()])
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def profile_admin_set(self, interaction: Interaction, user: discord.Member, item: app_commands.Choice[str], value: str):
        user_id, item_key, item_name = user.id, item.value, item.name
        
        processed_value = None
        if value.strip().lower() not in ['none', 'null', '']:
            if item_key in NUMERIC_ITEMS:
                try: processed_value = int(value)
                except ValueError: await interaction.response.send_message(f"「{item_name}」には数値を入力する必要があります。", ephemeral=True); return
            elif item_key == "birthday":
                if not re.fullmatch(r"\d{2}-\d{2}", value):
                    await interaction.response.send_message(f"「{item_name}」は `MM-DD` 形式で入力する必要があります。", ephemeral=True); return
                processed_value = value
            else:
                processed_value = value

        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                sql = f"INSERT INTO users (user_id, {item_key}) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET {item_key} = %s;"
                cur.execute(sql, (user_id, processed_value, processed_value))
            conn.commit()
            conn.close()
            await interaction.response.send_message(f"{user.display_name}の「{item_name}」を更新しました。", ephemeral=True)
        except Exception as e:
            print(f"DB Error on admin set: {e}")
            await interaction.response.send_message("DBエラーにより更新できませんでした。", ephemeral=True)

    @profile_admin.command(name="delete", description="指定したユーザーのプロフィール情報をすべて削除します。")
    @app_commands.describe(user="情報を削除するユーザー")
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def profile_admin_delete(self, interaction: Interaction, user: discord.Member):
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE user_id = %s", (user.id,))
            conn.commit()
            conn.close()
            await interaction.response.send_message(f"{user.display_name}のプロフィール情報を削除しました。", ephemeral=True)
        except Exception as e:
            print(f"DB Error on admin delete: {e}")
            await interaction.response.send_message("DBエラーにより削除できませんでした。", ephemeral=True)

async def setup(bot: commands.Bot):
    cog = ProfileCog(bot)
    bot.tree.add_command(cog.profile_admin)
    await bot.add_cog(cog)
