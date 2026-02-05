

import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from datetime import datetime

from config import JST, NOTIFY_TIME, CHANNEL_ID, DMPS_UPDATE_TIME, BIRTHDAY_CHANNEL_ID
from utils.database import get_db_connection, get_user_profile
from utils.scraper import fetch_and_parse_tournaments, fetch_dmps_user_stats

class TournamentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_tournaments_today.start()
        self.update_dmps_points_task.start()

    def cog_unload(self):
        self.check_tournaments_today.cancel()
        self.update_dmps_points_task.cancel()

    @app_commands.command(name="next", description="直近の大会情報を表示します。")
    async def next_tournament_slash(self, interaction: Interaction):
        await interaction.response.defer()
        all_tournaments = fetch_and_parse_tournaments()
        if not all_tournaments:
            await interaction.followup.send("大会情報が取得できなかったぞ！"); return
        
        today, now_time = datetime.now(JST).date(), datetime.now(JST).time()
        future_tournaments = [t for t in all_tournaments if t['date'] > today or (t['date'] == today and datetime.strptime(t['time'], '%H:%M').time() >= now_time)]
        
        if future_tournaments:
            next_t = future_tournaments[0]
            message = (f"みんな！お知らせダピコだ！\n次の大会はこれだ！\n" + "-"*40 + "\n"
                       f"開催日: {next_t['date'].strftime('%Y年%m月%d日')}\n大会名: **{next_t['name']}**\n"
                       f"開始時刻: {next_t['time']}\nフォーマット: {next_t['format']}\n"
                       f"定員: {next_t['capacity']}人\n大会HP: {next_t['url']}\n")
            await interaction.followup.send(message)
        else:
            await interaction.followup.send("現在予定されている大会はないぞ！")

    @app_commands.command(name="load", description="DMPS大会成績を更新します。")
    async def load_dmps_stats_slash(self, interaction: Interaction):
        user_id = interaction.user.id
        user_data = get_user_profile(user_id)

        if not user_data or not user_data.get('dmps_player_id'):
            await interaction.response.send_message("DMPSプレイヤーIDが登録されていません。`/register`コマンドで個人情報を登録してください。", ephemeral=True)
            return

        dmps_player_id = user_data['dmps_player_id']
        await interaction.response.defer(ephemeral=True)

        stats = await fetch_dmps_user_stats(dmps_player_id)

        if stats:
            new_rank, new_points = stats['rank'], stats['points']
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET dmps_rank = %s, dmps_points = %s WHERE user_id = %s;", (new_rank, new_points, user_id))
                conn.commit()
                await interaction.followup.send(f"DMPS大会成績を更新したぞ！\n現在のランキング: `{new_rank}`位\n現在のポイント: `{new_points}`pt", ephemeral=True)
            except Exception as e:
                if conn: conn.rollback()
                print(f"DB Error on /load command for user {user_id}: {e}")
                await interaction.followup.send("成績の更新中にエラーが発生しました。", ephemeral=True)
            finally:
                if conn: conn.close()
        else:
            await interaction.followup.send("DMPS大会成績の取得に失敗しました。プレイヤーIDが正しいか、またはサイトにアクセスできるか確認してください。", ephemeral=True)

    @tasks.loop(time=NOTIFY_TIME)
    async def check_tournaments_today(self):
        await self.bot.wait_until_ready()
        if not (channel := self.bot.get_channel(CHANNEL_ID)):
            print(f"Error: Channel ID {CHANNEL_ID} not found.")
            return

        all_tournaments = fetch_and_parse_tournaments()
        if not all_tournaments: return
        
        today = datetime.now(JST).date()
        todays_tournaments = [t for t in all_tournaments if t['date'] == today]
        
        if todays_tournaments:
            intro = "@everyone \nみんな！お知らせダピコだ！\n今日の公認大会の予定をお知らせするぞ！\n"
            message_parts = [intro]
            for t in todays_tournaments:
                message_parts.append(f"----------------------------------------\n"
                                   f"大会名: **{t['name']}**\n開始時刻: {t['time']}\n"
                                   f"フォーマット: {t['format']}\n定員: {t['capacity']}人\n"
                                   f"大会HP: {t['url']}\n")
            await channel.send("".join(message_parts))

    @tasks.loop(time=DMPS_UPDATE_TIME)
    async def update_dmps_points_task(self):
        await self.bot.wait_until_ready()
        conn = None
        granted_notifications = []
        
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=discord.psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT user_id, dmps_player_id, dmps_points FROM users WHERE dmps_player_id IS NOT NULL;")
                users_to_update = cur.fetchall()

                if not users_to_update:
                    print("[LOG] No users with DMPS Player ID registered.")
                    return

                for user_data in users_to_update:
                    user_id, dmps_player_id = user_data['user_id'], user_data['dmps_player_id']
                    old_points = user_data['dmps_points'] or 0
                    stats = await fetch_dmps_user_stats(dmps_player_id)

                    if stats:
                        new_rank, new_points = stats['rank'], stats['points']
                        point_increase = new_points - old_points
                        credits_to_grant = point_increase * 10 if point_increase > 0 else 0

                        if credits_to_grant > 0:
                            if member := self.bot.get_user(user_id):
                                granted_notifications.append(f"{member.display_name}さん: +{credits_to_grant} GTV ({point_increase} pts up)")
                            else:
                                granted_notifications.append(f"ユーザーID {user_id}: +{credits_to_grant} GTV ({point_increase} pts up)")

                        cur.execute("UPDATE users SET dmps_rank = %s, dmps_points = %s, credits = credits + %s WHERE user_id = %s;",
                                    (new_rank, new_points, credits_to_grant, user_id))
                    else:
                        print(f"[LOG] Failed to fetch DMPS stats for UserID: {dmps_player_id}")
            
            conn.commit()

            if granted_notifications and BIRTHDAY_CHANNEL_ID:
                if channel := self.bot.get_channel(BIRTHDAY_CHANNEL_ID):
                    message = "トーナメントランキングポイント増加によるGTV付与だぞ！みんなお疲れ様だ！\n" + "\n".join(granted_notifications)
                    await channel.send(message)
            elif not granted_notifications:
                print("[LOG] No DMPS points increased today.")

        except Exception as e:
            if conn: conn.rollback()
            print(f"DB Error in update_dmps_points_task: {e}")
        finally:
            if conn: conn.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(TournamentCog(bot))

