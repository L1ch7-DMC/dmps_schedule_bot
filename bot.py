
import os
import time
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from keep_alive import keep_alive
from dotenv import load_dotenv
from datetime import datetime, date, time as dt_time, timedelta, timezone
from urllib.parse import urljoin
import re
import threading
from flask import Flask

# Flaskアプリの初期化
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord bot is running!"

def run_flask():
    # RenderはPORT環境変数を使用します
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
    def keep_alive():
        t = Thread(target=run)
        t.start()

# --- 設定 ---
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID')) if os.getenv('DISCORD_CHANNEL_ID') else 0

BASE_URL = "https://dmps-tournament.takaratomy.co.jp/schedulehost.asp"

# 日本時間のタイムゾーン
JST = timezone(timedelta(hours=+9), 'JST')

# 通知を送る時間（日本時間の18時）
NOTIFY_TIME = dt_time(18, 0, 0, tzinfo=JST)
# --- 設定ここまで ---

# Botのセットアップ
intents = discord.Intents.default()
intents.message_content = True # コマンドのためにメッセージ内容の購読を有効化
bot = commands.Bot(command_prefix='!', intents=intents)

import re

def get_tonamel_url(details_page_url):
    """詳細ページにアクセスし、Tonamelの大会URLを取得する"""
    try:
        print(f"[LOG] get_tonamel_url: Checking detail page: {details_page_url}")
        response = requests.get(details_page_url)
        response.raise_for_status()
        # cp932はshift_jisのスーパーセットで、より堅牢な場合がある
        response.encoding = 'cp932'
        soup = BeautifulSoup(response.text, 'html.parser')

        # 検索するキーワード
        search_keywords = ["大会HP", "リモート使用アプリ"]
        
        for keyword in search_keywords:
            # キーワードを含むspanタグを正規表現で探す
            span_tag = soup.find('span', string=re.compile(keyword))
            
            if span_tag:
                # spanタグの親要素(td)からaタグを探す
                parent_td = span_tag.find_parent('td')
                if parent_td:
                    link_tag = parent_td.find('a')
                    if link_tag and link_tag.has_attr('href'):
                        url = link_tag['href']
                        if 'tonamel.com' in url:
                            print(f"[LOG] get_tonamel_url: Found Tonamel URL: {url}")
                            return url
        
        print(f"[LOG] get_tonamel_url: Tonamel URL not found on page.")
        return ""
    except requests.RequestException as e:
        print(f"[LOG] get_tonamel_url: Error accessing detail page: {e}")
        return ""
    except Exception as e:
        print(f"[LOG] get_tonamel_url: Error parsing detail page: {e}")
        return ""

def fetch_and_parse_tournaments():
    """ウェブサイトから大会情報を取得し、詳細ページからTonamel URLも取得する"""
    print("[LOG] fetch_and_parse_tournaments: 開始")
    try:
        response = requests.get(BASE_URL)
        print(f"[LOG] fetch_and_parse_tournaments: Webサイトへのアクセス結果: {response.status_code}")
        response.raise_for_status()
        response.encoding = 'shift_jis'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        schedule_table = soup.find('table', id='main')
        if not schedule_table:
            print("[LOG] fetch_and_parse_tournaments: 大会情報を含むテーブル (id='main') が見つかりませんでした。")
            return []

        tournaments = []
        tournament_rows = schedule_table.find_all('tr')[1:]

        for row in tournament_rows:
            cols = row.find_all('td')
            if len(cols) < 8:
                continue

            onclick_attr = row.get('onclick', '')
            relative_url = ""
            if onclick_attr:
                parts = onclick_attr.split("'")
                if len(parts) > 1:
                    relative_url = parts[1]
            
            details_page_url = urljoin(BASE_URL, relative_url)

            # Tonamel URLを取得
            tonamel_url = get_tonamel_url(details_page_url)
            time.sleep(0.5) # サーバーへの負荷を軽減

            try:
                date_str = cols[0].get_text(strip=True)
                name = cols[2].get_text(strip=True)
                format_type = cols[4].get_text(strip=True)
                capacity = cols[6].get_text(strip=True)
                start_time = cols[7].get_text(strip=True)

                parsed_date = datetime.strptime(date_str, '%y/%m/%d').date()
                raw_date_str = parsed_date.strftime('%Y年%m月%d日')

                # Tonamel URLがあればそれを使い、なければ詳細ページのURLを使う
                final_url = tonamel_url if tonamel_url else details_page_url

                tournaments.append({
                    "date": parsed_date,
                    "name": name,
                    "format": format_type,
                    "capacity": capacity,
                    "time": start_time,
                    "raw_date": raw_date_str,
                    "url": final_url
                })
            except (ValueError, IndexError) as e:
                print(f"[LOG] fetch_and_parse_tournaments: 大会情報の解析中にエラー: {e} on row '{row.get_text()}'")
                continue
        
        print(f"[LOG] fetch_and_parse_tournaments: {len(tournaments)}個の大会をリストに追加しました。")
        tournaments.sort(key=lambda x: (x['date'], x['time']))
        print("[LOG] fetch_and_parse_tournaments: 処理終了")
        return tournaments

    except requests.RequestException as e:
        print(f"[LOG] fetch_and_parse_tournaments: Webサイトへのアクセスでエラーが発生しました: {e}")
        return []
    except Exception as e:
        print(f"[LOG] fetch_and_parse_tournaments: 予期せぬエラーが発生しました: {e}")
        return []

@bot.command(name='hello')
async def hello(ctx):
    """簡単な挨拶を返すテストコマンド"""
    print(f"`!hello` command executed by {ctx.author}")
    await ctx.send('Hello!')

@bot.command(name='next')
async def next_tournament(ctx):
    """直近の大会情報を通知するコマンド"""
    print(f"--- `!next` command executed by {ctx.author} ---")
    await ctx.send("次の大会を探しているぞ... ")
    
    all_tournaments = fetch_and_parse_tournaments()
    print(f"[LOG] next_tournament: fetch_and_parse_tournamentsから {len(all_tournaments)} 件の大会情報を取得しました。")

    if not all_tournaments:
        await ctx.send("大会情報が取得できなかったぞ！")
        print("--- `!next` command finished: No tournaments found. ---")
        return

    today = datetime.now(JST).date()
    now_time = datetime.now(JST).time()
    print(f"[LOG] next_tournament: 現在の日時（JST）: {today} {now_time.strftime('%H:%M:%S')}")

    future_tournaments = []
    for t in all_tournaments:
        if t['date'] > today:
            future_tournaments.append(t)
        elif t['date'] == today:
            try:
                t_time = datetime.strptime(t['time'], '%H:%M').time()
                if t_time >= now_time:
                    future_tournaments.append(t)
            except ValueError:
                # 時刻が 'HH:MM' 形式でない場合も、とりあえず当日分として含める
                future_tournaments.append(t)
    
    print(f"[LOG] next_tournament: 未来の大会を {len(future_tournaments)} 件見つけました。")

    if future_tournaments:
        next_t = future_tournaments[0]
        print(f"[LOG] next_tournament: 次の大会が見つかりました: {next_t['name']} ({next_t['raw_date']})")
        message = (
            f"みんな！お知らせダピコだ！\n次の大会はこれだ！\n" + "-"*40 + "\n"
            f"開催日: {next_t['raw_date']}\n"
            f"大会名: **{next_t['name']}**\n"
            f"開始時刻: {next_t['time']}\n"
            f"フォーマット: {next_t['format']}\n"
            f"定員: {next_t['capacity']}人\n"
            f"大会HP: {next_t['url']}\n"
        )
        await ctx.send(message)
    else:
        print("[LOG] next_tournament: 未来の大会は見つかりませんでした。")
        await ctx.send("現在予定されている大会はないぞ！")
    
    print(f"--- `!next` command finished ---")

async def send_today_tournaments(channel):
    """今日の大会情報を指定されたチャンネルに送信する共通関数"""
    print(f"{datetime.now(JST)}: Checking for today's tournaments...")
    all_tournaments = fetch_and_parse_tournaments()
    if not all_tournaments:
        print("Could not retrieve tournament information.")
        # 大会情報が取得できない場合は通知しない
        return

    today = datetime.now(JST).date()
    todays_tournaments = [t for t in all_tournaments if t['date'] == today]

    if todays_tournaments:
        intro = "@everyone \nみんな！お知らせダピコだ！\n今日の公認大会の予定をお知らせするぞ！\n今日はこれだ！\n"
        message_parts = [intro]
        for t in todays_tournaments:
            message_parts.append(
                f"----------------------------------------\n"
                f"大会名: **{t['name']}**\n"
                f"開始時刻: {t['time']}\n"
                f"フォーマット: {t['format']}\n"
                f"定員: {t['capacity']}人\n"
                f"大会HP: {t['url']}\n"
            )
        message = "".join(message_parts)
        await channel.send(message)
    else:
        print("No tournaments scheduled for today.")
        # 大会がない場合は通知しない
        # await channel.send("みんな！お知らせダピコだ！\n今日の公認大会の予定はないみたいだぞ！") # この行を削除

@tasks.loop(time=NOTIFY_TIME)
async def check_tournaments_today():
    """毎日決まった時間に、その日の大会を通知する"""
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await send_today_tournaments(channel)
    else:
        print(f"Error: Channel ID {CHANNEL_ID} not found.")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    if not check_tournaments_today.is_running():
        check_tournaments_today.start()

if __name__ == '__main__':
    if TOKEN is None or CHANNEL_ID == 0:
        print("エラー: .envファイルで DISCORD_BOT_TOKEN または DISCORD_CHANNEL_ID を設定してください。")
    else:
        # Flaskサーバーを別スレッドで起動
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.start()
        # Discordボットを起動
        keep_alive()
        bot.run(TOKEN)
