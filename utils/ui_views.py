

import discord
from discord import Interaction, ui, TextStyle, Embed
from typing import Optional
import re
import asyncio
import random
import psycopg2
import psycopg2.extras

from config import PROFILE_ITEMS
from utils.database import get_db_connection, get_user_profile

# --- プロフィール登録用モーダル ---

class AchievementModal(ui.Modal, title='実績情報の登録'):
    def __init__(self, target_user: discord.Member, user_data: Optional[psycopg2.extras.DictCursor]):
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
    def __init__(self, target_user: discord.Member, user_data: Optional[psycopg2.extras.DictCursor]):
        super().__init__()
        self.target_user = target_user
        user_data = user_data or {}

        self.player_id = ui.TextInput(label=PROFILE_ITEMS["player_id"], style=TextStyle.short, required=False, placeholder="例: 123456789", default=str(user_data.get("player_id", "")))
        self.age = ui.TextInput(label=PROFILE_ITEMS["age"], style=TextStyle.short, required=False, placeholder="例: 20", default=str(user_data.get("age", "")))
        self.birthday = ui.TextInput(label=PROFILE_ITEMS["birthday"], style=TextStyle.short, required=False, placeholder="例: 01-15 (MM-DD形式)", default=user_data.get("birthday", ""))
        self.dmps_player_id = ui.TextInput(label=PROFILE_ITEMS["dmps_player_id"], style=TextStyle.short, required=False, placeholder="例: 123456789", default=str(user_data.get("dmps_player_id", "")))

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

# --- スロットUI ---
class SlotView(ui.View):
    def __init__(self, user_id: int, bet: int, original_interaction: Interaction):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.bet = bet
        self.original_interaction = original_interaction
        self.reels = ['🍒', '🍊', '🍇', '🔔', '７', '🍉']
        self.result = ['🎰', '🎰', '🎰']
        self.spinning_task = None
        self.active_reel = -1

        self.stop_button_1 = ui.Button(label="ストップ 1", style=discord.ButtonStyle.primary, custom_id="stop_1", disabled=True)
        self.stop_button_2 = ui.Button(label="ストップ 2", style=discord.ButtonStyle.primary, custom_id="stop_2", disabled=True)
        self.stop_button_3 = ui.Button(label="ストップ 3", style=discord.ButtonStyle.primary, custom_id="stop_3", disabled=True)

        self.stop_button_1.callback = self.stop_1_callback
        self.stop_button_2.callback = self.stop_2_callback
        self.stop_button_3.callback = self.stop_3_callback

        self.add_item(self.stop_button_1)
        self.add_item(self.stop_button_2)
        self.add_item(self.stop_button_3)

    async def start_game(self):
        await self.start_next_reel()

    async def start_next_reel(self):
        if self.spinning_task and not self.spinning_task.done():
            self.spinning_task.cancel()

        self.active_reel += 1
        if self.active_reel > 2:
            return

        buttons = [self.stop_button_1, self.stop_button_2, self.stop_button_3]
        for i, button in enumerate(buttons):
            button.disabled = (i != self.active_reel)

        try:
            message = await self.original_interaction.original_response()
            embed = message.embeds[0]
            embed.description = f"**> `{' | '.join(self.result)}` <**"
            await self.original_interaction.edit_original_response(embed=embed, view=self)
        except discord.NotFound:
            return

        self.spinning_task = asyncio.create_task(self.spin_animation(self.active_reel))

    async def spin_animation(self, reel_index: int):
        temp_result = list(self.result)
        while True:
            try:
                temp_result[reel_index] = random.choice(self.reels)
                message = await self.original_interaction.original_response()
                embed = message.embeds[0]
                embed.description = f"**> `{' | '.join(temp_result)}` <**"
                await self.original_interaction.edit_original_response(embed=embed)
                await asyncio.sleep(0.75)
            except (asyncio.CancelledError, discord.NotFound):
                break
            except Exception as e:
                print(f"Error during spin animation: {e}")
                break

    async def handle_stop(self, interaction: Interaction, reel_index: int):
        if reel_index != self.active_reel:
            await interaction.response.send_message("止めるリールが違うぞ！", ephemeral=True)
            return

        if self.spinning_task and not self.spinning_task.done():
            self.spinning_task.cancel()

        self.result[reel_index] = random.choice(self.reels)
        
        await interaction.response.defer()

        if self.active_reel == 2:
            self.stop_button_1.disabled = True
            self.stop_button_2.disabled = True
            self.stop_button_3.disabled = True
            await self.process_result()
        else:
            await self.start_next_reel()

    async def stop_1_callback(self, interaction: Interaction):
        await self.handle_stop(interaction, 0)
    async def stop_2_callback(self, interaction: Interaction):
        await self.handle_stop(interaction, 1)
    async def stop_3_callback(self, interaction: Interaction):
        await self.handle_stop(interaction, 2)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("他の人のスロットを止めることはできないぞ！", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.spinning_task and not self.spinning_task.done():
            self.spinning_task.cancel()
        
        for child in self.children:
            child.disabled = True
        
        try:
            message = await self.original_interaction.original_response()
            embed = message.embeds[0]
            if not any(field.name == "タイムアウト" for field in embed.fields):
                embed.add_field(name="タイムアウト", value="時間切れです。ベット額は返却されません。", inline=False)
                embed.color = discord.Color.dark_grey()
                await self.original_interaction.edit_original_response(embed=embed, view=self)
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"Error on slot timeout: {e}")

    async def process_result(self):
        result_text = ""
        payout_rate = 0
        if len(set(self.result)) == 1:
            if self.result[0] == '７':
                payout_rate = 20; result_text = "👑 **JACKPOT！** 👑\nおひょぴょー！７が揃ったぞ！"
            else:
                payout_rate = 10; result_text = "🎉 **大当たり！** 🎉\nすごい！3つ揃ったぞ！"
        elif len(set(self.result)) == 2:
            payout_rate = 3; result_text = "🎊 **当たり！** 🎊\n惜しい！あと1つだ！"
        else:
            result_text = "残念！また挑戦してくれ！"

        payout = self.bet * payout_rate

        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("UPDATE users SET credits = credits + %s WHERE user_id = %s RETURNING credits;", (payout, self.user_id))
                final_credits = cur.fetchone()['credits']
            conn.commit()

            message = await self.original_interaction.original_response()
            embed = message.embeds[0]
            embed.description = f"**> `{' | '.join(self.result)}` <**"
            embed.clear_fields()
            embed.add_field(name="結果", value=result_text, inline=False)
            embed.add_field(name="ベット額", value=f"`{self.bet}` GTV", inline=True)
            embed.add_field(name="配当", value=f"`{payout}` GTV", inline=True)
            embed.add_field(name="所持クレジット", value=f"`{final_credits}` GTV", inline=False)
            if payout > 0:
                embed.color = discord.Color.red()
                
            self.stop()
            await self.original_interaction.edit_original_response(embed=embed, view=self)
        except Exception as e:
            print(f"DB Error on slot result processing: {e}")
            await self.original_interaction.followup.send("結果の処理中にエラーが発生しました。", ephemeral=True)
        finally:
            if conn: conn.close()
