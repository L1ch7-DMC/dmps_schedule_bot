import discord
from discord import app_commands, Interaction, Embed
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import random
import psycopg2.extras

from config import JST, GACHA_PRIZES, GACHA_RATES, ADMIN_ROLES, TAX_BRACKETS, TAX_COLLECTION_TIME, BIRTHDAY_CHANNEL_ID
from utils.database import get_db_connection
from utils.helpers import format_emojis
from utils.ui_views import SlotView

# チャンネルごとの最後のスロットメッセージを記録する辞書
last_slot_messages = {}

class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.collect_income_tax.start()

    def cog_unload(self):
        self.collect_income_tax.cancel()

    @app_commands.command(name="daily", description="1日1回、500 GTVクレジットを獲得します。")
    async def daily_slash(self, interaction: Interaction):
        user_id = interaction.user.id
        now = datetime.now(JST)
        
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING;", (user_id,))
                cur.execute("SELECT credits, last_daily FROM users WHERE user_id = %s;", (user_id,))
                user_data = cur.fetchone()

                if user_data['last_daily'] is None or user_data['last_daily'].astimezone(JST).date() < now.date():
                    new_credits = (user_data['credits'] or 0) + 500
                    cur.execute("UPDATE users SET credits = %s, last_daily = %s WHERE user_id = %s;", (new_credits, now, user_id))
                    await interaction.response.send_message(f"🎉 デイリーボーナス！ 500 GTVクレジットを獲得したぞ！\n現在の所持クレジット: `{new_credits}` GTV")
                else:
                    next_bonus_time = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=JST)
                    time_remaining = next_bonus_time - now
                    hours, rem = divmod(time_remaining.seconds, 3600)
                    mins, _ = divmod(rem, 60)
                    await interaction.response.send_message(f"次のデイリーボーナスは明日までお預けだ！\nあと {hours}時間{mins}分 だぞ。", ephemeral=True)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"DB Error on /daily command: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        finally:
            conn.close()

    @app_commands.command(name="gacha", description="1000GTVを消費してガチャを回します。")
    @app_commands.describe(count="回す回数を指定します (1-10)。デフォルトは1回です。")
    async def gacha_slash(self, interaction: Interaction, count: app_commands.Range[int, 1, 10] = 1):
        user_id = interaction.user.id
        total_cost = 1000 * count

        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT credits FROM users WHERE user_id = %s FOR UPDATE;", (user_id,))
                user_data = cur.fetchone()
                current_credits = user_data['credits'] if user_data else 0

                if current_credits < total_cost:
                    await interaction.response.send_message(f"GTVクレジットが足りないぞ！ {total_cost} GTV必要だ。\n所持クレジット: `{current_credits}` GTV", ephemeral=True)
                    return

                new_credits = current_credits - total_cost
                cur.execute("UPDATE users SET credits = %s WHERE user_id = %s;", (new_credits, user_id))
                
                results = []
                for _ in range(count):
                    rarities, weights = zip(*GACHA_RATES.items())
                    chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]
                    prize_message = random.choice(GACHA_PRIZES.get(chosen_rarity, ["エラー"]))
                    results.append({"rarity": chosen_rarity, "message": prize_message})

                rarity_order = ["MAS", "LEG", "VIC", "SR", "VR", "R", "UC", "C"]
                results.sort(key=lambda x: rarity_order.index(x["rarity"]))

                message_lines = [f"ガチャ結果 ({count}連)", "--------------------"]
                for res in results:
                    prize = res['message'].replace(f"【{res['rarity']}】", "").lstrip()
                    formatted_prize = format_emojis(prize, self.bot)
                    message_lines.append(f"**【{res['rarity']}】** {formatted_prize}")
                
                message_lines.append("--------------------")
                message_lines.append(f"{interaction.user.display_name} | 残り: {new_credits} GTV")
                
                await interaction.response.send_message("\n".join(message_lines))
            conn.commit()
        except Exception as e:
            if conn: conn.rollback()
            print(f"Error on /gacha command: {e}")
            await interaction.response.send_message("ガチャ処理中にエラーが発生したぞ。クレジットは消費されていない。", ephemeral=True)
        finally:
            if conn: conn.close()

    @app_commands.command(name="slot", description="スロットを回します。")
    @app_commands.describe(bet="ベットするGTVクレジットの額 (1以上)")
    async def slot_slash(self, interaction: Interaction, bet: app_commands.Range[int, 1]):
        user_id, channel_id = interaction.user.id, interaction.channel_id

        if channel_id in last_slot_messages and user_id in last_slot_messages[channel_id]:
            try:
                old_message = await interaction.channel.fetch_message(last_slot_messages[channel_id].pop(user_id))
                await old_message.delete()
            except discord.NotFound: pass

        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("INSERT INTO users (user_id, credits) VALUES (%s, 0) ON CONFLICT (user_id) DO NOTHING;", (user_id,))
                cur.execute("SELECT credits FROM users WHERE user_id = %s FOR UPDATE;", (user_id,))
                user_data = cur.fetchone()
                current_credits = user_data['credits'] or 0

                if current_credits < bet:
                    await interaction.response.send_message(f"GTVクレジットが足りないぞ！\n所持クレジット: `{current_credits}` GTV", ephemeral=True)
                    return

                new_credits = current_credits - bet
                cur.execute("UPDATE users SET credits = %s WHERE user_id = %s;", (new_credits, user_id))
            conn.commit()

            view = SlotView(user_id=user_id, bet=bet, original_interaction=interaction)
            embed = Embed(title="🎰 スロットゲーム 🎰", color=discord.Color.gold(), description=f"**> `{' | '.join(view.result)}` <**")
            embed.add_field(name="ベット額", value=f"`{bet}` GTV")
            embed.add_field(name="現在の所持クレジット", value=f"`{new_credits}` GTV")
            embed.set_footer(text=f"{interaction.user.display_name} が挑戦")

            await interaction.response.send_message(embed=embed, view=view)
            message = await interaction.original_response()
            last_slot_messages.setdefault(channel_id, {})[user_id] = message.id
            await view.start_game()

        except Exception as e:
            if conn: conn.rollback()
            print(f"Error on /slot command: {e}")
            # Attempt to refund
            try:
                refund_conn = get_db_connection()
                with refund_conn.cursor() as cur:
                    cur.execute("UPDATE users SET credits = credits + %s WHERE user_id = %s;", (bet, user_id))
                refund_conn.commit()
                refund_conn.close()
                await interaction.followup.send("エラーが発生したためベット額を返却したぞ。", ephemeral=True)
            except Exception as refund_e:
                print(f"Failed to refund bet: {refund_e}")
                await interaction.followup.send("重大なエラーが発生した。管理者に連絡してくれ。", ephemeral=True)
        finally:
            if conn and not conn.closed: conn.close()

    @app_commands.command(name="leaderboard", description="GTVクレジットの所持数ランキングを表示するぞ！")
    async def leaderboard_slash(self, interaction: Interaction):
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT user_id, credits FROM users WHERE credits > 0 ORDER BY credits DESC LIMIT 10;")
                leaderboard_data = cur.fetchall()

            if not leaderboard_data:
                await interaction.response.send_message("まだ誰もGTVクレジットを持っていないみたいだな。", ephemeral=True)
                return

            embed = Embed(title="🏆 GTVクレジット ランキング 🏆", color=discord.Color.gold())
            description = []
            rank_emojis = {1: '🥇', 2: '🥈', 3: '🥉'}
            
            for i, record in enumerate(leaderboard_data, 1):
                member = interaction.guild.get_member(record['user_id'])
                name = member.display_name if member else f"不明なユーザー"
                rank_emoji = rank_emojis.get(i, f"`{i}.`")
                description.append(f"{rank_emoji} **{name}** - `{record['credits']}` GTV")

            embed.description = "\n".join(description)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            print(f"Error on /leaderboard command: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        finally:
            if conn: conn.close()

    @app_commands.command(name="gift", description="他のユーザーにGTVクレジットを渡します。")
    @app_commands.describe(user="クレジットを渡す相手", amount="渡すクレジットの額 (1以上)")
    async def gift_slash(self, interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
        if interaction.user.id == user.id or user.bot:
            await interaction.response.send_message("自分自身やボットにはクレジットを渡せないぞ。", ephemeral=True)
            return

        sender_id, receiver_id = interaction.user.id, user.id
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT credits FROM users WHERE user_id = %s FOR UPDATE;", (sender_id,))
                sender_credits = (cur.fetchone() or {}).get('credits', 0)

                if sender_credits < amount:
                    await interaction.response.send_message(f"GTVクレジットが足りません！\n所持クレジット: `{sender_credits}` GTV", ephemeral=True)
                    return

                cur.execute("UPDATE users SET credits = credits - %s WHERE user_id = %s;", (amount, sender_id))
                cur.execute("INSERT INTO users (user_id, credits) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET credits = users.credits + %s;", (receiver_id, amount, amount))
            conn.commit()
            await interaction.response.send_message(f"✅ {interaction.user.display_name}が{user.display_name}さんに `{amount}` GTVクレジットを渡しました。")
        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error on /gift command: {e}")
            await interaction.response.send_message("エラーが発生し、処理はキャンセルされました。", ephemeral=True)
        finally:
            if conn: conn.close()

    # --- 管理者用クレジット操作コマンドグループ ---
    admin_credit = app_commands.Group(name="admin_credit", description="管理者用のクレジット操作コマンド", guild_only=True)

    @admin_credit.command(name="set", description="ユーザーのGTVクレジットを指定した額に設定します。")
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def admin_credit_set(self, interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 0]):
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (user_id, credits) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET credits = %s;", (user.id, amount, amount))
            conn.commit()
            await interaction.response.send_message(f"{user.display_name}さんのクレジットを `{amount}` GTVに設定しました。", ephemeral=True)
        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error on /admin_credit set: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        finally:
            if conn: conn.close()

    @admin_credit.command(name="add", description="ユーザーのGTVクレジットを指定した額だけ増やします。")
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def admin_credit_add(self, interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
        # `gift` と同様のロジックで実装
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (user_id, credits) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET credits = users.credits + %s;", (user.id, amount, amount))
            conn.commit()
            await interaction.response.send_message(f"{user.display_name}さんのクレジットに `{amount}` GTVを追加しました。", ephemeral=True)
        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error on /admin_credit add: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        finally:
            if conn: conn.close()

    @admin_credit.command(name="remove", description="ユーザーのGTVクレジットを指定した額だけ減らします。")
    @app_commands.checks.has_any_role(*ADMIN_ROLES)
    async def admin_credit_remove(self, interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT credits FROM users WHERE user_id = %s FOR UPDATE;", (user.id,))
                current_credits = (cur.fetchone() or {}).get('credits', 0)
                if current_credits < amount:
                    await interaction.response.send_message(f"残高不足です。{user.display_name}さんの所持クレジットは `{current_credits}` GTVです。", ephemeral=True)
                    return
                cur.execute("UPDATE users SET credits = credits - %s WHERE user_id = %s;", (amount, user.id))
            conn.commit()
            await interaction.response.send_message(f"{user.display_name}さんのクレジットから `{amount}` GTVを削除しました。", ephemeral=True)
        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error on /admin_credit remove: {e}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        finally:
            if conn: conn.close()

    @tasks.loop(time=TAX_COLLECTION_TIME)
    async def collect_income_tax(self):
        if datetime.now(JST).weekday() != 0: return # 月曜日のみ実行

        await self.bot.wait_until_ready()
        conn = None
        total_tax_collected, users_taxed_count = 0, 0
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT user_id, credits, last_taxed_credits FROM users WHERE credits > 0")
                all_users = cur.fetchall()
                if not all_users: return

                for user in all_users:
                    increase = user['credits'] - (user['last_taxed_credits'] or 0)
                    if increase <= 0:
                        cur.execute("UPDATE users SET last_taxed_credits = %s WHERE user_id = %s", (user['credits'], user['user_id']))
                        continue

                    tax_rate, deduction = 0, 0
                    for bracket in TAX_BRACKETS:
                        if increase <= bracket[0]:
                            tax_rate, deduction = bracket[1], bracket[2]
                            break
                    
                    tax_amount = int((increase * tax_rate) - deduction)
                    if tax_amount > 0:
                        new_credits = user['credits'] - tax_amount
                        cur.execute("UPDATE users SET credits = %s, last_taxed_credits = %s WHERE user_id = %s", (new_credits, new_credits, user['user_id']))
                        total_tax_collected += tax_amount
                        users_taxed_count += 1
                    else:
                        cur.execute("UPDATE users SET last_taxed_credits = %s WHERE user_id = %s", (user['credits'], user['user_id']))
            conn.commit()
            
            if users_taxed_count > 0 and BIRTHDAY_CHANNEL_ID:
                if channel := self.bot.get_channel(BIRTHDAY_CHANNEL_ID):
                    await channel.send(f"今週の所得税として、合計 `{total_tax_collected}` GTV を {users_taxed_count} 名から徴収したぞ。")
        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error in income tax task: {e}")
        finally:
            if conn: conn.close()

async def setup(bot: commands.Bot):
    cog = EconomyCog(bot)
    bot.tree.add_command(cog.admin_credit)
    await bot.add_cog(cog)
