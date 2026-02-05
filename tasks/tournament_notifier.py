import discord
from discord.ext import tasks, commands
from datetime import datetime
import asyncio

from ..config import JST, CHANNEL_ID, NOTIFY_TIME
from ..utils.web_scraper import fetch_and_parse_tournaments

async def send_today_tournaments(channel):
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

@tasks.loop(time=NOTIFY_TIME)
async def check_tournaments_today(bot: commands.Bot):
    await bot.wait_until_ready()
    if channel := bot.get_channel(CHANNEL_ID):
        await send_today_tournaments(channel)
    else:
        print(f"Error: Channel ID {CHANNEL_ID} not found.")

