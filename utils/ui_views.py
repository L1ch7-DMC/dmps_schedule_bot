import discord
from discord import Interaction, ui, TextStyle
from typing import Optional
import re
import asyncio
import random
import psycopg2
import psycopg2.extras

from config import PROFILE_ITEMS
from utils.database import get_db_connection, get_user_profile

# =====================
# プロフィール登録モーダル
# =====================

class AchievementModal(ui.Modal, title='実績情報の登録'):
    def __init__(self, target_user: discord.Member, user_data):
        super().__init__()
        self.target_user = target_user
        user_data = user_data or {}

        self.top100 = ui.TextInput(label=PROFILE_ITEMS["top100"], required=False, default=str(user_data.get("top100", "")))
        self.nd_rate = ui.TextInput(label=PROFILE_ITEMS["nd_rate"], required=False, default=str(user_data.get("nd_rate", "")))
        self.ad_rate = ui.TextInput(label=PROFILE_ITEMS["ad_rate"], required=False, default=str(user_data.get("ad_rate", "")))
        self.achievements = ui.TextInput(label=PROFILE_ITEMS["achievements"], style=TextStyle.paragraph, required=False, default=user_data.get("achievements", ""))

        for item in (self.top100, self.nd_rate, self.ad_rate, self.achievements):
            self.add_item(item)

    async def on_submit(self, interaction: Interaction):
        updates = {}
        for key, field in [("top100", self.top100), ("nd_rate", self.nd_rate), ("ad_rate", self.ad_rate)]:
            if field.value:
                if not field.value.isdigit():
                    await interaction.response.send_message("数値を入力してくれ！", ephemeral=True)
                    return
                updates[key] = int(field.value)
            else:
                updates[key] = None

        updates["achievements"] = self.achievements.value or None

        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, top100, nd_rate, ad_rate, achievements)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        top100=EXCLUDED.top100,
                        nd_rate=EXCLUDED.nd_rate,
                        ad_rate=EXCLUDED.ad_rate,
                        achievements=EXCLUDED.achievements
                """, (self.target_user.id, *updates.values()))
            conn.commit()
            conn.close()
            await interaction.response.send_message("更新したぞ！", ephemeral=True)
        except Exception as e:
            print(e)
            await interaction.response.send_message("DBエラーだぞ！", ephemeral=True)

# =====================
# Register View
# =====================

class RegisterView(ui.View):
    def __init__(self, target_user: discord.Member):
        super().__init__(timeout=180)
        self.target_user = target_user

    @ui.button(label="実績を登録", style=discord.ButtonStyle.primary)
    async def register_achievements(self, interaction: Interaction, _):
        data = get_user_profile(self.target_user.id)
        await interaction.response.send_modal(AchievementModal(self.target_user, data))

# =====================
# スロット View（429対策済）
# =====================

class SlotView(ui.View):
    def __init__(self, user_id: int, bet: int, interaction: Interaction):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.bet = bet
        self.interaction = interaction
        self.message: Optional[discord.Message] = None

        self.reels = ['🍒','🍊','🍇','🔔','７','🍉']
        self.result = ['🎰','🎰','🎰']
        self.active_reel = 0
        self.spin_task: Optional[asyncio.Task] = None

        for i in range(3):
            self.add_item(ui.Button(
                label=f"ストップ {i+1}",
                style=discord.ButtonStyle.primary,
                disabled=(i != 0),
                custom_id=str(i),
                callback=self.stop_callback
            ))

    async def start(self):
        self.message = await self.interaction.original_response()
        self.spin_task = asyncio.create_task(self.spin())

    async def safe_edit(self):
        if not self.message:
            return
        try:
            embed = self.message.embeds[0]
            embed.description = f"**> `{' | '.join(self.result)}` <**"
            await self.message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def spin(self):
        while True:
            self.result[self.active_reel] = random.choice(self.reels)
            await self.safe_edit()
            await asyncio.sleep(1.2)  # ← 429防止の要
            if not self.spin_task or self.spin_task.cancelled():
                break

    async def stop_callback(self, interaction: Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("君のスロットじゃないぞ！", ephemeral=True)
            return

        await interaction.response.defer()

        if self.spin_task:
            self.spin_task.cancel()

        self.result[self.active_reel] = random.choice(self.reels)

        self.active_reel += 1
        if self.active_reel >= 3:
            await self.finish()
            return

        for i, item in enumerate(self.children):
            item.disabled = (i != self.active_reel)

        self.spin_task = asyncio.create_task(self.spin())
        await self.safe_edit()

    async def finish(self):
        payout = self.bet * (10 if len(set(self.result)) == 1 else 0)

        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET credits = credits + %s WHERE user_id=%s RETURNING credits",
                    (payout, self.user_id)
                )
                credits = cur.fetchone()[0]
            conn.commit()
            conn.close()

            embed = self.message.embeds[0]
            embed.clear_fields()
            embed.add_field(name="結果", value=" | ".join(self.result))
            embed.add_field(name="配当", value=f"{payout} GTV")
            embed.add_field(name="残高", value=f"{credits} GTV")

            self.stop()
            await self.message.edit(embed=embed, view=None)

        except Exception as e:
            print(e)
