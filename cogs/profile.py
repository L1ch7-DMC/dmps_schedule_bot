import discord
from discord.ext import commands
from discord import Interaction, app_commands, ui, TextStyle, Embed
from typing import Optional

from ..database import get_db_connection, get_user_profile
from ..config import PROFILE_ITEMS, NUMERIC_ITEMS

class AchievementModal(ui.Modal, title='実績情報の登録'):
    def __init__(self, target_user: discord.Member, user_data: Optional[dict]):
        super().__init__()
        self.target_user = target_user
        user_data = user_data or {}

        self.top100 = ui.TextInput(label=PROFILE_ITEMS["top100"], style=TextStyle.short, required=False, placeholder="例: 1", default=str(user_data.get("top100", "")))
        self.nd_rate = ui.TextInput(label=PROFILE_ITEMS["nd_rate"], style=TextStyle.short, required=False, placeholder="例: 1600", default=str(user_data.get("nd_rate", "")))
        self.ad_rate = ui.TextInput(label=PROFILE_ITEMS["ad_rate"], style=TextStyle.short, required=False, placeholder="例: 1600", default=str(user_data.get("ad_rate", "")))
        self.achievements = ui.TextInput(label=PROFILE_ITEMS["achievements"], style=TextStyle.paragraph, required=False, placeholder="例: ドルマゲドンXCUP最終1位", default=user_data.get("achievements", ""))
        
        self.add_item(self.top100)
        self.add_item(self.nd_rate)
        self.add_item(self.ad_rate)
        self.add_item(self.achievements)

    async def on_submit(self, interaction: Interaction):
        user_id = self.target_user.id
        updates = {}
        
        for item_key, text_input in [("top100", self.top100), ("nd_rate", self.nd_rate), ("ad_rate", self.ad_rate)]:
            if text_input.value:
                try: updates[item_key] = int(text_input.value)
                except ValueError: await interaction.response.send_message(f"「{PROFILE_ITEMS[item_key]}」には数値を入力してください。", ephemeral=True); return
            else: updates[item_key] = None

        updates["achievements"] = self.achievements.value if self.achievements.value else None

        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, top100, nd_rate, ad_rate, achievements)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        top100 = EXCLUDED.top100,
                        nd_rate = EXCLUDED.nd_rate,
                        ad_rate = EXCLUDED.ad_rate,
                        achievements = EXCLUDED.achievements;
                """, (user_id, updates.get("top100"), updates.get("nd_rate"), updates.get("ad_rate"), updates.get("achievements")))
            conn.commit()
            conn.close()
            message = f'{self.target_user.display_name}の実績情報を更新したぞ！'
            await interaction.response.send_message(message, ephemeral=True)
        except Exception as e:
            print(f"DB Error on AchievementModal submit: {e}")
            await interaction.response.send_message('エラーで更新できなかったぞ！', ephemeral=True)

class PersonalInfoModal(ui.Modal, title='個人情報の登録'):
    def __init__(self, target_user: discord.Member, user_data: Optional[dict]):
        super().__init__()
        self.target_user = target_user
        user_data = user_data or {}

        self.player_id = ui.TextInput(label=PROFILE_ITEMS["player_id"], style=TextStyle.short, required=False, placeholder="例: 123456789", default=str(user_data.get("player_id", "")))
        self.age = ui.TextInput(label=PROFILE_ITEMS["age"], style=TextStyle.short, required=False, placeholder="例: 20", default=str(user_data.get("age", "")))
        self.birthday = ui.TextInput(label=PROFILE_ITEMS["birthday"], style=TextStyle.short, required=False, placeholder="例: 01-15 (MM-DD形式)", default=user_data.get("birthday", ""))
        self.dmps_player_id = ui.TextInput(label=PROFILE_ITEMS["dmps_player_id"], style=TextStyle.short, required=False, placeholder="例: 123456789", default=user_data.get("dmps_player_id", ""))

        self.add_item(self.player_id)
        self.add_item(self.age)
        self.add_item(self.birthday)
        self.add_item(self.dmps_player_id)

    async def on_submit(self, interaction: Interaction):
        user_id = self.target_user.id
        updates = {}

        if self.player_id.value:
            try: updates["player_id"] = int(self.player_id.value)
            except ValueError: await interaction.response.send_message(f"「{PROFILE_ITEMS['player_id']}」には数値を入力してください。", ephemeral=True); return
        else: updates["player_id"] = None

        if self.age.value:
            try: updates["age"] = int(self.age.value)
            except ValueError: await interaction.response.send_message(f"「{PROFILE_ITEMS['age']}」には数値を入力してください。", ephemeral=True); return
        else: updates["age"] = None
        
        if self.birthday.value:
            import re
            if not re.fullmatch(r"\d{2}-\d{2}", self.birthday.value):
                await interaction.response.send_message(f"「{PROFILE_ITEMS['birthday']}」は `MM-DD` 形式で入力してください。", ephemeral=True); return
            updates["birthday"] = self.birthday.value
        else: updates["birthday"] = None
        
        updates["dmps_player_id"] = self.dmps_player_id.value if self.dmps_player_id.value else None
        
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, player_id, age, birthday, dmps_player_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        player_id = EXCLUDED.player_id,
                        age = EXCLUDED.age,
                        birthday = EXCLUDED.birthday,
                        dmps_player_id = EXCLUDED.dmps_player_id;
                """, (user_id, updates.get("player_id"), updates.get("age"), updates.get("birthday"), updates.get("dmps_player_id")))
            conn.commit()
            conn.close()
            message = f'{self.target_user.display_name}の個人情報を更新したぞ！'
            await interaction.response.send_message(message, ephemeral=True)
        except Exception as e:
            print(f"DB Error on PersonalInfoModal submit: {e}")
            await interaction.response.send_message('エラーで更新できなかったぞ！', ephemeral=True)

class RegisterView(ui.View):
    def __init__(self, target_user: discord.Member):
        super().__init__(timeout=180)
        self.target_user = target_user

    async def get_user_data(self):
        return get_user_profile(self.target_user.id)

    @ui.button(label="実績を登録", style=discord.ButtonStyle.primary)
    async def register_achievements(self, interaction: Interaction, button: ui.Button):
        user_data = await self.get_user_data()
        await interaction.response.send_modal(AchievementModal(target_user=self.target_user, user_data=user_data))

    @ui.button(label="個人情報を登録", style=discord.ButtonStyle.secondary)
    async def register_personal_info(self, interaction: Interaction, button: ui.Button):
        user_data = await self.get_user_data()
        await interaction.response.send_modal(PersonalInfoModal(target_user=self.target_user, user_data=user_data))

class Profile(commands.Cog):
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
        
        if not user_data or not any(user_data[key] for key in PROFILE_ITEMS):
            message = f"{target_user.display_name}の情報はまだ登録されていないぞ。" + ("\n`/register`で登録してみよう！" if target_user == interaction.user else "")
            await interaction.response.send_message(message, ephemeral=True); return

        embed = Embed(title=f"{target_user.display_name}のプロフィール", color=target_user.color).set_thumbnail(url=target_user.display_avatar.url)
        for key, label in PROFILE_ITEMS.items():
            if key in user_data and user_data[key] is not None:
                embed.add_field(name=label, value=user_data[key], inline=True)

        # DMPS成績情報を追加
        if user_data.get('dmps_rank') is not None and user_data.get('dmps_points') is not None:
            embed.add_field(name="DMPSランキング", value=f"`{user_data['dmps_rank']}`位", inline=True)
            embed.add_field(name="DMPSポイント", value=f"`{user_data['dmps_points']}`pt", inline=True)

        # GTVクレジット情報はクレジットボットが管理するため、ここでは表示しない
        # credits = user_data.get('credits', 0)
        # embed.add_field(name="所持GTV", value=f"**`{credits}`** GTV", inline=False)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
