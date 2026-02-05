import discord
from discord.ext import commands
from discord import Interaction, app_commands, ui, TextStyle, Embed
from typing import Optional, Annotated, Dict
import random
import asyncio
import math

from config import GACHA_PRIZES, GACHA_RATES
from database import get_db_connection, get_user_profile
from utils.helpers import format_emojis

# チャンネルごとの最後のスロットメッセージを記録する辞書
last_slot_messages = {}

class SlotView(ui.View):
    def __init__(self, user_id: int, bet: int, original_interaction: Interaction):
        super().__init__(timeout=120) # タイムアウトを少し長めに設定
        self.user_id = user_id
        self.bet = bet
        self.original_interaction = original_interaction
        self.reels = ['🍒', '🍊', '🍇', '🔔', '７', '🍉']
        self.result = ['🎰', '🎰', '🎰']
        self.spinning_task = None
        self.active_reel = -1

        # ボタンを定義
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
        """ゲームを開始し、最初のリールの回転を始める"""
        await self.start_next_reel()

    async def start_next_reel(self):
        """次のリールの回転を開始する"""
        if self.spinning_task and not self.spinning_task.done():
            self.spinning_task.cancel()

        self.active_reel += 1
        if self.active_reel > 2:
            return

        # 対応するボタンを有効化
        buttons = [self.stop_button_1, self.stop_button_2, self.stop_button_3]
        for i, button in enumerate(buttons):
            button.disabled = (i != self.active_reel)

        # メッセージを更新して、回転開始を通知
        try:
            message = await self.original_interaction.original_response()
            embed = message.embeds[0]
            embed.description = f"**> `{' | '.join(self.result)}` <**"
            await self.original_interaction.edit_original_response(embed=embed, view=self)
        except discord.NotFound:
            return # メッセージが見つからなければ終了

        # 新しいリールの回転アニメーションを開始
        self.spinning_task = asyncio.create_task(self.spin_animation(self.active_reel))

    async def spin_animation(self, reel_index: int):
        """指定されたリールの回転アニメーション（メッセージ更新ループ）"""
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
                break # タスクがキャンセルされたか、メッセージが削除されたらループを抜ける
            except Exception as e:
                print(f"Error during spin animation: {e}")
                break

    async def handle_stop(self, interaction: Interaction, reel_index: int):
        """ストップボタンが押された時の共通処理"""
        if reel_index != self.active_reel:
            await interaction.response.send_message("止めるリールが違うぞ！", ephemeral=True)
            return

        # 現在の回転タスクを停止
        if self.spinning_task and not self.spinning_task.done():
            self.spinning_task.cancel()

        # リールの結果を確定
        self.result[reel_index] = random.choice(self.reels)
        
        await interaction.response.defer() # ボタンへの応答

        # 最後のリールかチェック
        if self.active_reel == 2:
            # 全てのボタンを無効化し、最終結果を処理
            self.stop_button_1.disabled = True
            self.stop_button_2.disabled = True
            self.stop_button_3.disabled = True
            await self.process_result()
        else:
            # 次のリールへ
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
        """最終結果を計算し、メッセージを更新する"""
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
            with conn.cursor() as cur:
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

class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="daily", description="1日1回、500 GTVクレジットを獲得します。")
    async def daily_slash(self, interaction: Interaction):
        user_id = interaction.user.id
        now = discord.utils.utcnow() # Use discord.utils.utcnow() for timezone-aware datetime
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # ユーザー情報を取得（なければ作成）
                cur.execute("""
                    INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING;
                """, (user_id,))
                cur.execute("SELECT credits, last_daily FROM users WHERE user_id = %s;", (user_id,))
                user_data = cur.fetchone()

                last_daily = user_data[1] # last_daily is the second column
                
                # last_dailyがNone（初回）か、最後にもらった日付が今日より前かをチェック
                if last_daily is None or last_daily.date() < now.date():
                    # クレジットを更新し、last_daily を記録
                    new_credits = (user_data[0] or 0) + 500 # credits is the first column
                    cur.execute("""
                        UPDATE users SET credits = %s, last_daily = %s WHERE user_id = %s;
                    """, (new_credits, now, user_id))
                    
                    await interaction.response.send_message(f"🎉 デイリーボーナス！ 500 GTVクレジットを獲得したぞ！\n現在の所持クレジット: `{new_credits}` GTV")
                else:
                    # 次のボーナス（次の日の0時）までの時間を計算
                    tomorrow = now.date() + timedelta(days=1)
                    next_bonus_time = datetime.combine(tomorrow, dt_time(0, 0, 0, tzinfo=now.tzinfo)) # Use current timezone info
                    time_remaining = next_bonus_time - now
                    hours, remainder = divmod(time_remaining.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    
                    await interaction.response.send_message(f"次のデイリーボーナスは明日までお預けだ！\nあと {hours}時間{minutes}分 だぞ。", ephemeral=True)
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"DB Error on /daily command: {e}")
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)
        finally:
            conn.close()

    @app_commands.command(name="gacha", description="1000GTVを消費してガチャを回します。")
    @app_commands.describe(count="回す回数を指定します (1-10)。デフォルトは1回です。")
    async def gacha_slash(self, interaction: Interaction, count: app_commands.Range[int, 1, 10] = 1):
        user_id = interaction.user.id
        cost_per_pull = 1000
        total_cost = cost_per_pull * count

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # クレジット残高を確認
                cur.execute("SELECT credits FROM users WHERE user_id = %s;", (user_id,))
                user_data = cur.fetchone()
                current_credits = user_data[0] if user_data and user_data[0] is not None else 0

                if current_credits < total_cost:
                    await interaction.response.send_message(f"GTVクレジットが足りないぞ！{count}回回すには {total_cost} GTV必要だ。\nあなたの所持クレジット: `{current_credits}` GTV", ephemeral=True)
                    return

                # コストを引く
                new_credits = current_credits - total_cost
                cur.execute("UPDATE users SET credits = %s WHERE user_id = %s;", (new_credits, user_id))
                
                # --- ガチャの抽選ロジック ---
                results = []
                for _ in range(count):
                    rarities = list(GACHA_RATES.keys())
                    weights = list(GACHA_RATES.values())
                    chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]
                    
                    prize_pool = GACHA_PRIZES.get(chosen_rarity, [])
                    if not prize_pool:
                        chosen_message = f"エラー: {chosen_rarity}の景品がありません。"
                    else:
                        chosen_message = random.choice(prize_pool)
                    
                    results.append({"rarity": chosen_rarity, "message": chosen_message})

                # --- 結果表示 ---
                rarity_order = ["MAS", "LEG", "VIC", "SR", "VR", "R", "UC", "C"]
                results.sort(key=lambda x: rarity_order.index(x["rarity"]))

                message_lines = [f"ガチャ結果 ({count}連)", "--------------------"]
                for result in results:
                    # Remove the rarity prefix from the message itself if it exists
                    prize_message = result['message']
                    if prize_message.startswith(f"【{result['rarity']}】"):
                        prize_message = prize_message[len(f"【{result['rarity']}】"):].lstrip()
                    
                    # テキスト内のカスタム絵文字をフォーマット
                    formatted_message = format_emojis(prize_message, self.bot)
                    
                    message_lines.append(f"**【{result['rarity']}】** {formatted_message}")
                
                message_lines.append("--------------------")
                message_lines.append(f"{interaction.user.display_name} | 残り: {new_credits} GTV")
                
                await interaction.response.send_message("\n".join(message_lines))

            conn.commit()

        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error or other error on /gacha command: {e}")
            await interaction.response.send_message("ガチャの処理中にエラーが発生しました。クレジットは消費されていません。", ephemeral=True)
        finally:
            if conn: conn.close()

    @app_commands.command(name="slot", description="スロットを回します。")
    @app_commands.describe(bet="ベットするGTVクレジットの額 (1以上)")
    @app_commands.rename(bet='ベット額')
    async def slot_slash(self, interaction: Interaction, bet: app_commands.Range[int, 1]):
        user_id = interaction.user.id
        channel_id = interaction.channel_id

        if channel_id in last_slot_messages and user_id in last_slot_messages[channel_id]:
            try:
                old_message_id = last_slot_messages[channel_id].pop(user_id)
                old_message = await interaction.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.NotFound: pass
            except discord.HTTPException as e: print(f"Warning: Failed to delete old slot message: {e}")

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (user_id, credits) VALUES (%s, 0) ON CONFLICT (user_id) DO NOTHING;", (user_id,))
                cur.execute("SELECT credits FROM users WHERE user_id = %s;", (user_id,))
                user_data = cur.fetchone()
                current_credits = user_data[0] if user_data and user_data[0] is not None else 0

                if current_credits < bet:
                    await interaction.response.send_message(f"GTVクレジットが足りないぞ！\nあなたの所持クレジット: `{current_credits}` GTV", ephemeral=True)
                    return

                new_credits = current_credits - bet
                cur.execute("UPDATE users SET credits = %s WHERE user_id = %s;", (new_credits, user_id))
            conn.commit()

            view = SlotView(user_id=user_id, bet=bet, original_interaction=interaction)
            
            embed = Embed(title="🎰 スロットゲーム 🎰", color=discord.Color.gold())
            embed.description = f"**> `{' | '.join(view.result)}` <**"
            embed.add_field(name="ベット額", value=f"`{bet}` GTV")
            embed.add_field(name="現在の所持クレジット", value=f"`{new_credits}` GTV")
            embed.set_footer(text=f"{interaction.user.display_name} が挑戦")

            await interaction.response.send_message(embed=embed, view=view)
            
            message = await interaction.original_response()
            if channel_id not in last_slot_messages: last_slot_messages[channel_id] = {}
            last_slot_messages[channel_id][user_id] = message.id

            await view.start_game()

        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error or other error on /slot command: {e}")
            try:
                conn_revert = get_db_connection()
                with conn_revert.cursor() as cur_revert:
                    cur_revert.execute("UPDATE users SET credits = credits + %s WHERE user_id = %s;", (bet, user_id))
                conn_revert.commit()
                conn_revert.close()
                if not interaction.response.is_done():
                    await interaction.response.send_message("エラーが発生したため、ベット額を返却したぞ。", ephemeral=True)
                else:
                    await interaction.followup.send("エラーが発生したため、ベット額を返却したぞ。", ephemeral=True)
            except Exception as revert_e:
                print(f"Error reverting bet: {revert_e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("重大なエラーが発生したそうだ。管理者に連絡してくれ。", ephemeral=True)
                else:
                    await interaction.followup.send("重大なエラーが発生したそうだ。管理者に連絡してくれ。", ephemeral=True)
        finally:
            if conn and not conn.closed:
                conn.close()

    @app_commands.command(name="leaderboard", description="GTVクレジットの所持数ランキングを表示するぞ！")
    async def leaderboard_slash(self, interaction: Interaction):
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # クレジットが多い順に上位10名を取得
                cur.execute("SELECT user_id, credits FROM users WHERE credits > 0 ORDER BY credits DESC LIMIT 10;")
                leaderboard_data = cur.fetchall()

            if not leaderboard_data:
                await interaction.response.send_message("まだ誰もGTVクレジットを持っていないみたいだな。", ephemeral=True)
                return

            embed = Embed(title="🏆 GTVクレジット ランキング 🏆", color=discord.Color.gold())
            
            description = []
            rank_emojis = {1: '🥇', 2: '🥈', 3: '🥉'}
            
            for i, record in enumerate(leaderboard_data, 1):
                user_id = record[0] # user_id is the first column
                credits = record[1] # credits is the second column
                
                # サーバーからメンバー情報を取得
                member = interaction.guild.get_member(user_id)
                member_display_name = member.display_name if member else f"不明なユーザー"
                
                rank_emoji = rank_emojis.get(i, f"`{i}.`")
                description.append(f"{rank_emoji} **{member_display_name}** - `{credits}` GTV")

            embed.description = "\n".join(description)
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            print(f"Error on /leaderboard command: {e}")
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)
        finally:
            if conn:
                conn.close()

    @app_commands.command(name="gift", description="他のユーザーにGTVクレジットを渡します。")
    @app_commands.describe(
        user="クレジットを渡す相手",
        amount="渡すクレジットの額 (1以上)"
    )
    @app_commands.rename(user='相手', amount='額')
    async def gift_slash(self, interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
        sender_id = interaction.user.id
        receiver_id = user.id

        if sender_id == receiver_id:
            await interaction.response.send_message("自分自身にクレジットを渡すことはできないぞ。", ephemeral=True)
            return
        
        if user.bot:
            await interaction.response.send_message("ボットにクレジットを渡すことはできないぞ。", ephemeral=True)
            return

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # 送信者のクレジット残高を確認 (FOR UPDATEでロックをかけるとより安全)
                cur.execute("SELECT credits FROM users WHERE user_id = %s FOR UPDATE;", (sender_id,))
                sender_data = cur.fetchone()
                sender_credits = sender_data[0] if sender_data and sender_data[0] is not None else 0

                if sender_credits < amount:
                    await interaction.response.send_message(f"GTVクレジットが足りません！\nあなたの所持クレジット: `{sender_credits}` GTV", ephemeral=True)
                    conn.rollback() # ロックを解放するためにロールバック
                    return

                # 送信者のクレジットを減らす
                cur.execute("UPDATE users SET credits = credits - %s WHERE user_id = %s;", (amount, sender_id))
                
                # 受信者のユーザーレコードが存在しない可能性があるので、INSERT ON CONFLICT を使う
                cur.execute("""
                    INSERT INTO users (user_id, credits) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET credits = users.credits + %s;
                """, (receiver_id, amount, amount))

            # トランザクションを確定
            conn.commit()

            await interaction.response.send_message(f"✅ {interaction.user.display_name}が{user.display_name}さんに `{amount}` GTVクレジットを渡しました。")

        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error on /gift command: {e}")
            await interaction.response.send_message("エラーが発生しました。処理はキャンセルされました。", ephemeral=True)
        finally:
            if conn:
                conn.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))