import discord
from discord.ext import commands
from discord import Interaction, app_commands, Embed
from typing import Optional
from datetime import datetime

from database import get_db_connection, get_user_profile
from utils.web_scraper import fetch_and_parse_tournaments, fetch_dmps_user_stats
from config import JST

class DMPSInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="load", description="DMPS大会成績を更新します。")
    async def load_dmps_stats_slash(self, interaction: Interaction):
        user_id = interaction.user.id
        user_data = get_user_profile(user_id)

        if not user_data or not user_data.get('dmps_player_id'):
            await interaction.response.send_message("DMPSプレイヤーIDが登録されていません。`/register`コマンドで個人情報を登録してください。", ephemeral=True)
            return

        dmps_player_id = user_data['dmps_player_id']
        await interaction.response.defer(ephemeral=True) # スクレイピングに時間がかかる場合があるため

        stats = await fetch_dmps_user_stats(dmps_player_id)

        if stats:
            new_rank = stats['rank']
            new_points = stats['points']
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users SET dmps_rank = %s, dmps_points = %s
                        WHERE user_id = %s;
                    """, (new_rank, new_points, user_id))
                conn.commit()
                await interaction.followup.send(f"""DMPS大会成績を更新したぞ！
現在のランキング: `{new_rank}`位
現在のポイント: `{new_points}`pt""", ephemeral=True)
            except Exception as e:
                if conn: conn.rollback()
                print(f"DB Error on /load command for user {user_id}: {e}")
                await interaction.followup.send("成績の更新中にエラーが発生しました。", ephemeral=True)
            finally:
                if conn: conn.close()
        else:
            await interaction.followup.send("DMPS大会成績の取得に失敗しました。プレイヤーIDが正しいか、またはサイトにアクセスできるか確認してください。", ephemeral=True)

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

async def setup(bot: commands.Bot):
    await bot.add_cog(DMPSInfo(bot))