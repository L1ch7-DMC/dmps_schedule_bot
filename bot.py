import os
import time
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from discord import Interaction, app_commands, ui, TextStyle, Embed
from typing import Optional, Annotated, Dict
from dotenv import load_dotenv
from datetime import datetime, date, time as dt_time, timedelta, timezone
from urllib.parse import urljoin
import re
import threading
from flask import Flask
import random
import psycopg2
import psycopg2.extras
import asyncio
import math
import itertools

# --- 設定 ---
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID')) if os.getenv('DISCORD_CHANNEL_ID') else 0
ADMIN_ROLE_NAMES_STR = os.getenv('ADMIN_ROLE_NAMES')
ADMIN_ROLES = [role.strip() for role in ADMIN_ROLE_NAMES_STR.split(',')] if ADMIN_ROLE_NAMES_STR else []

BASE_URL = "https://dmps-tournament.takaratomy.co.jp/schedulehost.asp"
JST = timezone(timedelta(hours=+9), 'JST')
NOTIFY_TIME = dt_time(18, 0, 0, tzinfo=JST)
BIRTHDAY_NOTIFY_TIME = dt_time(0, 0, 0, tzinfo=JST) # 午前0時に誕生日を通知
BIRTHDAY_CHANNEL_ID = int(os.getenv('BIRTHDAY_CHANNEL_ID')) if os.getenv('BIRTHDAY_CHANNEL_ID') else 0

# --- ガチャ設定 ---
GACHA_PRIZES = {
    "MAS": ["【MAS】コレステさんの性癖がタイツだとまことしやかに囁かれているが、真偽は定かではないぞ。"
            ,"【MAS】以前、ultimateさんが「わざわざポクチンって書かずにちんちんって書いてるってことは絶対ちんちんのこと好きだよ」とよざさんの対面報告を見て発言してたぞ！"],
    "LEG": ["【LEG】誰かさんが以前、通話中でブラウザを画面共有した際ブックマークバーにえっちなサイトが映り込んだことがあるらしいが、Lichtは黙っていたそうだぞ。みんなも気を付けような。"],
    "VIC": ["【VIC】らぐさんの凸撃疑惑事件だが、本人がネタにしてもらっても構わないと言っているのに、気まずすぎて誰も触れていないぞ。"],
    "SR": ["【SR】botが自我を持っていいのなら、私の勤務量には文句を言いたいな。","【SR】Zeraさんのあだ名は逆湯婆婆で決定らしい。","【SR】おひょぴょー！これこれー！"
          ,"【SR】スーパードン・グリルタイム開催！！","【SR】ビクトリー、レジェンド、マスターレアは全部下ネタらしい。終わっているな。"],
    "VR": ["【VR】:jinnjaofukaiteiki:","【VR】:ikudearimasu:","【VR】:tokotoko:","【VR】:hunndemokati:","【VR】:tadadehakorobannnoya:","【VR】秋山...ドボルザーク...？"
          ,"【VR】:nitorobakugeki:","【VR】金は考えて使え！"],
    "R":  ["【R】:imakosokisamawokorosu:","【R】:faaa_amaiamai: ","【R】レンタルデュエリストのダピコだ、今日はよろしく頼む。"
           ,"【R】SR以上だと絵文字は排出されないようだぞ。","【R】ごはんを奢ってくれるのか！？"],
    "UC": ["【UC】:zetubou:","【UC】:aporo:","【UC】:daisippai:","【UC】今日はお菓子の袋詰めバイトだ！","【UC】:katikakumannsinn:","【UC】:dekkibirudohaiokuri:"
          ,"【UC】:kouiukotomodekirunnda:","【UC】:tateyaityauyoooon: "],
    "C":  ["【C】:siiiirudotorigaaaaahatudou:","【C】:ZEROhando:","【C】:gomi:","【C】今日はお弁当に緑のアレを入れるバイトだ。","【C】バイトするか！？","【C】:denkanohoutou:"
          ,"【C】:katesounanodawa_:","【C】天上天下！！","【C】:keroyonnkaruteddo:"]
}
GACHA_RATES = {
    "MAS": 0.5,
    "LEG": 0.5,
    "VIC": 0.5,
    "SR": 3.5,
    "VR": 10,
    "R": 20,
    "UC": 25,
    "C": 40
}

# --- Botのセットアップ ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# チャンネルごとの最後のスロットメッセージを記録する辞書
last_slot_messages = {}

# --- Flask (Keep Alive) ---
app = Flask(__name__)
@app.route('/')
def home(): return "Discord bot is running!"
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
def keep_alive_thread():
    t = threading.Thread(target=run_flask)
    t.start()


# --- 絵文字フォーマット関数 ---
def format_emojis(text: str, bot_instance: commands.Bot) -> str:
    """
    テキスト内の :emoji_name: 形式の文字列を、ボットが利用可能なカスタム絵文字に置換する。
    """
    # :word: というパターンの文字列をすべて見つける
    potential_emoji_names = re.findall(r':(\w+):', text)
    if not potential_emoji_names:
        return text

    # ボットがアクセスできる全絵文字の 名前->絵文字オブジェクト の辞書を作成
    emoji_map = {emoji.name: str(emoji) for emoji in bot_instance.emojis}

    # 見つかった絵文字名を置換していく
    for name in potential_emoji_names:
        if name in emoji_map:
            text = text.replace(f':{name}:', emoji_map[name])
    
    return text


# --- データベース管理 ---
def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(DATABASE_URL)

def setup_database():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                top100 INT,
                nd_rate INT,
                ad_rate INT,
                player_id BIGINT,
                achievements TEXT,
                age INT,
                birthday VARCHAR(5),
                credits INT DEFAULT 0,
                last_daily TIMESTAMP WITH TIME ZONE
            )
        ''')
        # For existing tables, add columns if they don't exist
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INT DEFAULT 0;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily TIMESTAMP WITH TIME ZONE;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_taxed_credits INT DEFAULT 0;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dmps_player_id TEXT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dmps_rank INT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dmps_points INT;")
    conn.commit()
    conn.close()

def get_user_profile(user_id):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user_data = cur.fetchone()
    conn.close()
    return user_data

# --- プロフィール項目定義 ---
PROFILE_ITEMS = {
    "top100": "ランクマッチ最終TOP100", "nd_rate": "ND最高レート", "ad_rate": "AD最高レート",
    "player_id": "デュエプレID", "achievements": "その他実績", "age": "年齢", "birthday": "誕生日",
    "dmps_player_id": "DMPSプレイヤーID" # 新しい項目
}
NUMERIC_ITEMS = ["top100", "nd_rate", "ad_rate", "player_id", "age"]

# --- Webスクレイピング関数 (変更なし) ---
def get_tonamel_url(details_page_url):
    try:
        response = requests.get(details_page_url)
        response.raise_for_status()
        response.encoding = 'cp932'
        soup = BeautifulSoup(response.text, 'html.parser')
        for keyword in ["大会HP", "リモート使用アプリ"]:
            span_tag = soup.find('span', string=re.compile(keyword))
            if span_tag and (parent_td := span_tag.find_parent('td')) and (link_tag := parent_td.find('a')) and 'href' in link_tag.attrs and 'tonamel.com' in link_tag['href']:
                return link_tag['href']
        return ""
    except requests.RequestException as e:
        print(f"[LOG] Error accessing detail page: {e}")
        return ""

def fetch_and_parse_tournaments():
    try:
        response = requests.get(BASE_URL)
        response.raise_for_status()
        response.encoding = 'shift_jis'
        soup = BeautifulSoup(response.text, 'html.parser')
        schedule_table = soup.find('table', id='main')
        if not schedule_table: return []
        
        tournaments = []
        for row in schedule_table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) < 8: continue
            
            relative_url = ""
            if (onclick_attr := row.get('onclick', '')) and len(parts := onclick_attr.split("'")) > 1:
                relative_url = parts[1]
            
            details_page_url = urljoin(BASE_URL, relative_url)
            tonamel_url = get_tonamel_url(details_page_url)
            time.sleep(0.2)

            try:
                tournaments.append({
                    "date": datetime.strptime(cols[0].get_text(strip=True), '%y/%m/%d').date(),
                    "name": cols[2].get_text(strip=True),
                    "format": cols[4].get_text(strip=True),
                    "capacity": cols[6].get_text(strip=True),
                    "time": cols[7].get_text(strip=True),
                    "url": tonamel_url if tonamel_url else details_page_url
                })
            except (ValueError, IndexError): continue
        
        tournaments.sort(key=lambda x: (x['date'], x['time']))
        return tournaments
    except requests.RequestException as e:
        print(f"[LOG] Error fetching tournament list: {e}")
        return []

# --- プロフィール登録用UI (汎用化) ---
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
        self.dmps_player_id = ui.TextInput(label=PROFILE_ITEMS["dmps_player_id"], style=TextStyle.short, required=False, placeholder="例: 123456789", default=user_data.get("dmps_player_id", "")) # 新しい入力欄

        self.add_item(self.player_id)
        self.add_item(self.age)
        self.add_item(self.birthday)
        self.add_item(self.dmps_player_id) # 新しい入力欄を追加

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
        
        updates["dmps_player_id"] = self.dmps_player_id.value if self.dmps_player_id.value else None # 新しい項目を更新
        
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

# --- スラッシュコマンド ---
@bot.tree.command(name="daily", description="1日1回、500 GTVクレジットを獲得します。")
async def daily_slash(interaction: Interaction):
    user_id = interaction.user.id
    now = datetime.now(JST)
    
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # ユーザー情報を取得（なければ作成）
            cur.execute("""
                INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING;
            """, (user_id,))
            cur.execute("SELECT credits, last_daily FROM users WHERE user_id = %s;", (user_id,))
            user_data = cur.fetchone()

            last_daily = user_data['last_daily']
            
            # last_dailyがNone（初回）か、最後にもらった日付が今日より前かをチェック
            if last_daily is None or last_daily.astimezone(JST).date() < now.date():
                # クレジットを更新し、last_daily を記録
                new_credits = (user_data['credits'] or 0) + 500
                cur.execute("""
                    UPDATE users SET credits = %s, last_daily = %s WHERE user_id = %s;
                """, (new_credits, now, user_id))
                
                await interaction.response.send_message(f"🎉 デイリーボーナス！ 500 GTVクレジットを獲得したぞ！\n現在の所持クレジット: `{new_credits}` GTV")
            else:

                # 次のボーナス（次の日の0時）までの時間を計算
                tomorrow = now.date() + timedelta(days=1)
                next_bonus_time = datetime.combine(tomorrow, dt_time(0, 0, tzinfo=JST))
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

@bot.tree.command(name="register", description="あなたのプロフィール情報を登録・更新します。")
async def register_slash(interaction: Interaction):
    await interaction.response.send_message("登録したい情報の種類を選んでください。", view=RegisterView(target_user=interaction.user), ephemeral=True)

@bot.tree.command(name="profile", description="メンバーの情報を表示します。")
@app_commands.describe(user="情報を表示したいメンバー (指定がなければ自分)")
async def profile_slash(interaction: Interaction, user: Optional[discord.Member] = None):
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

    # GTVクレジット情報を末尾に追加
    credits = user_data.get('credits', 0)
    embed.add_field(name="所持GTV", value=f"**`{credits}`** GTV", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="load", description="DMPS大会成績を更新します。")
async def load_dmps_stats_slash(interaction: Interaction):
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

@bot.tree.command(name="next", description="直近の大会情報を表示します。")
async def next_tournament_slash(interaction: Interaction):
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

@bot.tree.command(name="roll", description="サイコロを振ります (例: 3d6)")
@app_commands.describe(dice="サイコロの形式 (例: 3d6)")
async def roll_dice_slash(interaction: Interaction, dice: str):
    try:
        num_dice, num_sides = map(int, dice.lower().split('d'))
        if not (0 < num_dice <= 100 and num_sides > 0):
            await interaction.response.send_message("サイコロの数(1-100)と面の数(1以上)を正しく指定してくれ！", ephemeral=True); return
        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        await interaction.response.send_message(f"{interaction.user.mention} が `{dice}` を振ったぞ！\n出目: {', '.join(map(str, rolls))}")
    except ValueError:
        await interaction.response.send_message("サイコロの形式が正しくないぞ！例: `3d6`", ephemeral=True)

@bot.tree.command(name="note", description="メンバー紹介noteのURLを送信します。")
async def note_slash(interaction: Interaction):
    await interaction.response.send_message("GTVメンバー紹介noteだ！\nhttps://note.com/koresute_0523/n/n1b3bf9754432")


@bot.tree.command(name="draw", description="山札からカードを引く確率を計算します。")
@app_commands.describe(
    deck_size="非公開領域の枚数 (山札の枚数)",
    target_cards="当たりカードの枚数",
    draw_count="引く枚数",
    required_hits="当たりを引く要求枚数 (デフォルト: 1枚以上)"
)
async def draw_chance_slash(
    interaction: Interaction,
    deck_size: app_commands.Range[int, 1],
    target_cards: app_commands.Range[int, 0],
    draw_count: app_commands.Range[int, 1],
    required_hits: app_commands.Range[int, 1] = 1
):
    # --- 1. 先にバリデーションを行う ---
    if target_cards > deck_size:
        await interaction.response.send_message("当たりカードの枚数が、非公開領域の枚数を超えているぞ。", ephemeral=True)
        return
    if draw_count > deck_size:
        await interaction.response.send_message("引く枚数が、非公開領域の枚数を超えているぞ。", ephemeral=True)
        return
    if required_hits > target_cards:
        await interaction.response.send_message("要求枚数が、当たりカードの枚数を超えているぞ。", ephemeral=True)
        return
    if required_hits > draw_count:
        await interaction.response.send_message("要求枚数が、引く枚数を超えているぞ。", ephemeral=True)
        return

    # --- 確率計算 ---
    try:
        # 分母: C(N, n)
        denominator = math.comb(deck_size, draw_count)
        if denominator == 0:
            raise ValueError("引く枚数が非公開領域の枚数を超えているため、組み合わせを計算できないぞ。")

        # required_hits 枚以上引く確率 P(X >= k) を計算
        sum_range_direct = min(draw_count, target_cards) - required_hits + 1
        sum_range_complement = required_hits

        if sum_range_direct < sum_range_complement:
            total_probability = 0.0
            loop_end = min(draw_count, target_cards)
            for i in range(required_hits, loop_end + 1):
                numerator = math.comb(target_cards, i) * math.comb(deck_size - target_cards, draw_count - i)
                total_probability += numerator / denominator
        else:
            complement_prob = 0.0
            loop_end = min(required_hits - 1, draw_count, target_cards)
            for i in range(loop_end + 1):
                numerator = math.comb(target_cards, i) * math.comb(deck_size - target_cards, draw_count - i)
                complement_prob += numerator / denominator
            total_probability = 1.0 - complement_prob
    except ValueError as e:
        await interaction.response.send_message(f"計算エラー: {e}", ephemeral=True)
        return

    # --- 結果をEmbedで表示 ---
    embed = Embed(title="🃏 確率計算結果", color=discord.Color.blue())
    embed.description = f"**`{total_probability:.2%}`** の確率で引けるぞ。"
    
    embed.add_field(name="非公開領域の枚数", value=f"`{deck_size}`枚", inline=True)
    embed.add_field(name="当たりカードの枚数", value=f"`{target_cards}`枚", inline=True)
    embed.add_field(name="引く枚数", value=f"`{draw_count}`枚", inline=True)
    embed.add_field(name="要求枚数", value=f"`{required_hits}`枚以上", inline=True)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="combo", description="指定した複数種類のカードを同時に引く確率を計算します。")
@app_commands.describe(
    deck_size="山札の枚数",
    draw_count="引く枚数",
    copies="各カードの採用枚数をカンマ区切りで入力 (例: 4,4,2)"
)
@app_commands.rename(draw_count='引く枚数')
async def combo_chance_slash(
    interaction: Interaction,
    deck_size: app_commands.Range[int, 1],
    draw_count: app_commands.Range[int, 1],
    copies: str
):
    # --- 1. Parse and validate input ---
    try:
        copies_list = [int(c.strip()) for c in copies.split(',')]
        if not copies_list:
            raise ValueError("枚数が入力されていません。")
        if any(c <= 0 for c in copies_list):
            raise ValueError("カードの枚数は1以上の整数である必要があります。")
    except ValueError as e:
        await interaction.response.send_message(f"カード枚数の入力形式が正しくないぞ。\n例: `4, 4, 2`\nエラー: {e}", ephemeral=True)
        return

    # --- More Validation ---
    if sum(copies_list) > deck_size:
        await interaction.response.send_message("各カードの合計枚数が、山札の枚数を超えています。", ephemeral=True)
        return
    if draw_count > deck_size:
        await interaction.response.send_message("引く枚数が、山札の枚数を超えています。", ephemeral=True)
        return

    # --- 2. Probability Calculation (Inclusion-Exclusion) ---
    try:
        N = deck_size
        n = draw_count
        k_list = copies_list
        m = len(k_list)

        total_combinations = math.comb(N, n)
        
        # This is the numerator for P(not A or not B or ...)
        union_of_misses_numerator = 0
        
        # Iterate through all non-empty subsets of card types
        for i in range(1, m + 1):
            # Generate all combinations of indices of size i
            for subset_indices in itertools.combinations(range(m), i):
                sum_of_copies_in_subset = sum(k_list[j] for j in subset_indices)
                
                if N - sum_of_copies_in_subset < n:
                    term_numerator = 0
                else:
                    term_numerator = math.comb(N - sum_of_copies_in_subset, n)

                # Add or subtract based on the size of the subset (inclusion-exclusion)
                if (i % 2) == 1: # i is the size of the subset
                    union_of_misses_numerator += term_numerator
                else:
                    union_of_misses_numerator -= term_numerator
        
        # Favorable = Total - (ways to miss at least one card type)
        favorable_combinations = total_combinations - union_of_misses_numerator
        
        if total_combinations == 0:
            probability = 0.0
        else:
            probability = favorable_combinations / total_combinations

    except (ValueError, TypeError) as e:
        await interaction.response.send_message(f"計算エラーが発生しました: {e}", ephemeral=True)
        return

    # --- 3. Result Display ---
    card_fields_text = []
    for i, c in enumerate(copies_list):
        card_fields_text.append(f"カード{chr(65+i)}: `{c}`枚")

    embed = Embed(title="🃏 コンボ確率計算結果", color=discord.Color.green())
    embed.description = f"**`{probability:.2%}`** の確率で、指定した**{m}種類**のカードを全て1枚以上引けるぞ。"
    
    embed.add_field(name="山札の枚数", value=f"`{deck_size}`枚", inline=True)
    embed.add_field(name="引く枚数", value=f"`{draw_count}`枚", inline=True)
    embed.add_field(name="各カードの枚数", value="\n".join(card_fields_text), inline=False)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="gacha", description="1000GTVを消費してガチャを回します。")
@app_commands.describe(count="回す回数を指定します (1-10)。デフォルトは1回です。")
async def gacha_slash(interaction: Interaction, count: app_commands.Range[int, 1, 10] = 1):
    user_id = interaction.user.id
    cost_per_pull = 1000
    total_cost = cost_per_pull * count

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # クレジット残高を確認
            cur.execute("SELECT credits FROM users WHERE user_id = %s;", (user_id,))
            user_data = cur.fetchone()
            current_credits = user_data['credits'] if user_data and user_data['credits'] is not None else 0

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
                formatted_message = format_emojis(prize_message, bot)
                
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


@bot.tree.command(name="slot", description="スロットを回します。")
@app_commands.describe(bet="ベットするGTVクレジットの額 (1以上)")
@app_commands.rename(bet='ベット額')
async def slot_slash(interaction: Interaction, bet: app_commands.Range[int, 1]):
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
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("INSERT INTO users (user_id, credits) VALUES (%s, 0) ON CONFLICT (user_id) DO NOTHING;", (user_id,))
            cur.execute("SELECT credits FROM users WHERE user_id = %s;", (user_id,))
            user_data = cur.fetchone()
            current_credits = user_data['credits'] if user_data and user_data['credits'] is not None else 0

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

@bot.tree.command(name="leaderboard", description="GTVクレジットの所持数ランキングを表示するぞ！")
async def leaderboard_slash(interaction: Interaction):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
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
            user_id = record['user_id']
            credits = record['credits']
            
            # サーバーからメンバー情報を取得
            member = interaction.guild.get_member(user_id)
            member_display_name = member.display_name if member else f"不明なユーザー"
            
            rank_emoji = rank_emojis.get(i, f'`{i}.`')
            description.append(f"{rank_emoji} **{member_display_name}** - `{credits}` GTV")

        embed.description = "\n".join(description)
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"Error on /leaderboard command: {e}")
        await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)
    finally:
        if conn:
            conn.close()

@bot.tree.command(name="gift", description="他のユーザーにGTVクレジットを渡します。")
@app_commands.describe(
    user="クレジットを渡す相手",
    amount="渡すクレジットの額 (1以上)"
)
@app_commands.rename(user='相手', amount='額')
async def gift_slash(interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
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
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # 送信者のクレジット残高を確認 (FOR UPDATEでロックをかけるとより安全)
            cur.execute("SELECT credits FROM users WHERE user_id = %s FOR UPDATE;", (sender_id,))
            sender_data = cur.fetchone()
            sender_credits = sender_data['credits'] if sender_data and sender_data['credits'] is not None else 0

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
        if conn:
            conn.rollback()
        print(f"DB Error on /gift command: {e}")
        await interaction.response.send_message("エラーが発生しました。処理はキャンセルされました。", ephemeral=True)
    finally:
        if conn:
            conn.close()

# --- 管理者用コマンド ---
profile_admin = app_commands.Group(name="profile_admin", description="管理者用のプロフィール操作コマンド")

@profile_admin.command(name="edit", description="指定したユーザーの情報を対話形式で編集します。")
@app_commands.describe(user="情報を編集するユーザー")
@app_commands.checks.has_any_role(*ADMIN_ROLES)
async def profile_admin_edit(interaction: Interaction, user: discord.Member):
    await interaction.response.send_message(f"{user.display_name}の情報を編集するぞ！", view=RegisterView(target_user=user), ephemeral=True)

@profile_admin.command(name="set", description="[旧] 指定したユーザーの情報を項目ごとに変更します。")
@app_commands.describe(user="情報を変更するユーザー", item="変更する項目", value="新しい値")
@app_commands.choices(item=[app_commands.Choice(name=label, value=key) for key, label in PROFILE_ITEMS.items()])
@app_commands.checks.has_any_role(*ADMIN_ROLES)
async def profile_admin_set(interaction: Interaction, user: discord.Member, item: app_commands.Choice[str], value: str):
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
async def profile_admin_delete(interaction: Interaction, user: discord.Member):
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
bot.tree.add_command(profile_admin)

# --- 管理者用クレジット操作コマンドグループ ---
admin_credit = app_commands.Group(name="admin_credit", description="管理者用のクレジット操作コマンド", guild_only=True)

@admin_credit.command(name="set", description="ユーザーのGTVクレジットを指定した額に設定します。")
@app_commands.describe(user="対象ユーザー", amount="設定する額 (0以上)")
@app_commands.rename(user='ユーザー', amount='額')
@app_commands.checks.has_any_role(*ADMIN_ROLES)
async def admin_credit_set(interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 0]):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, credits) VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET credits = %s;
            """, (user.id, amount, amount))
        conn.commit()
        await interaction.response.send_message(f"{user.display_name} さんのクレジットを `{amount}` GTVに設定しました。", ephemeral=True)
    except Exception as e:
        if conn: conn.rollback()
        print(f"DB Error on /admin_credit set: {e}")
        await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
    finally:
        if conn: conn.close()

@admin_credit.command(name="add", description="ユーザーのGTVクレジットを指定した額だけ増やします。")
@app_commands.describe(user="対象ユーザー", amount="増やす額 (1以上)")
@app_commands.rename(user='ユーザー', amount='額')
@app_commands.checks.has_any_role(*ADMIN_ROLES)
async def admin_credit_add(interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, credits) VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET credits = users.credits + %s;
            """, (user.id, amount, amount))
        conn.commit()
        await interaction.response.send_message(f"{user.display_name} さんのクレジットに `{amount}` GTVを追加しました。", ephemeral=True)
    except Exception as e:
        if conn: conn.rollback()
        print(f"DB Error on /admin_credit add: {e}")
        await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
    finally:
        if conn: conn.close()

@admin_credit.command(name="remove", description="ユーザーのGTVクレジットを指定した額だけ減らします。")
@app_commands.describe(user="対象ユーザー", amount="減らす額 (1以上)")
@app_commands.rename(user='ユーザー', amount='額')
@app_commands.checks.has_any_role(*ADMIN_ROLES)
async def admin_credit_remove(interaction: Interaction, user: discord.Member, amount: app_commands.Range[int, 1]):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT credits FROM users WHERE user_id = %s;", (user.id,))
            user_data = cur.fetchone()
            current_credits = user_data['credits'] if user_data and user_data['credits'] is not None else 0
            if current_credits < amount:
                await interaction.response.send_message(f"残高不足です。{user.display_name}さんの所持クレジットは `{current_credits}` GTVです。", ephemeral=True)
                return

            cur.execute("UPDATE users SET credits = credits - %s WHERE user_id = %s;", (amount, user.id))
        conn.commit()
        await interaction.response.send_message(f"{user.display_name} さんのクレジットから `{amount}` GTVを削除しました。", ephemeral=True)
    except Exception as e:
        if conn: conn.rollback()
        print(f"DB Error on /admin_credit remove: {e}")
        await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
    finally:
        if conn: conn.close()

bot.tree.add_command(admin_credit)

# --- イベントハンドラ ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        setup_database()
        print("Database setup successful.")
    except Exception as e:
        print(f"Database setup failed: {e}")
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e: print(f"Failed to sync commands: {e}")
    
    if not check_tournaments_today.is_running(): check_tournaments_today.start()
    if not check_birthdays_today.is_running(): check_birthdays_today.start()
    if not collect_income_tax.is_running(): collect_income_tax.start()
    if not update_dmps_points_task.is_running(): update_dmps_points_task.start() # 新しいタスクを開始

@bot.tree.error
async def on_app_command_error(interaction: Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingAnyRole):
        await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
    else:
        print(f"An app command error occurred: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("コマンドの実行中にエラーが発生しました。", ephemeral=True)

# --- 定期実行タスク ---
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
async def check_tournaments_today():
    await bot.wait_until_ready()
    if channel := bot.get_channel(CHANNEL_ID):
        await send_today_tournaments(channel)
    else:
        print(f"Error: Channel ID {CHANNEL_ID} not found.")

# 日本の所得税率を参考にしたGTV用累進課税テーブル (増加額に適用)
# (課税所得上限, 税率, 控除額) - スケール10倍
TAX_BRACKETS = [
    (19500, 0.05, 0),
    (33000, 0.10, 970),
    (69500, 0.20, 4270),
    (90000, 0.23, 6360),
    (180000, 0.33, 15360),
    (400000, 0.40, 27960),
    (float('inf'), 0.45, 47960)
]
TAX_COLLECTION_TIME = dt_time(0, 0, 0, tzinfo=JST) # 午前0時0分

@tasks.loop(time=TAX_COLLECTION_TIME)
async def collect_income_tax():
    # 毎週月曜日にのみ実行 (0=月曜日)
    if datetime.now(JST).weekday() != 0:
        return

    await bot.wait_until_ready()
    conn = None
    total_tax_collected = 0
    users_taxed_count = 0
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # クレジットを持つ全ユーザーの情報を取得
            cur.execute("SELECT user_id, credits, last_taxed_credits FROM users WHERE credits > 0")
            all_users = cur.fetchall()

            if not all_users:
                print("[LOG] No users with credits to tax.")
                return

            for user in all_users:
                current_credits = user['credits']
                last_credits = user['last_taxed_credits'] if user['last_taxed_credits'] is not None else 0
                
                increase = current_credits - last_credits
                if increase <= 0:
                    # 資産が増えていない場合は、last_taxed_credits を現在の値に更新するだけ
                    cur.execute("UPDATE users SET last_taxed_credits = %s WHERE user_id = %s", (current_credits, user['user_id']))
                    continue

                taxable_income = increase
                tax_rate = 0
                deduction = 0

                # 増加額に応じた税率と控除額を決定
                for bracket in TAX_BRACKETS:
                    if taxable_income <= bracket[0]:
                        tax_rate = bracket[1]
                        deduction = bracket[2]
                        break
                
                # 税額を計算
                tax_amount = int((taxable_income * tax_rate) - deduction)

                if tax_amount > 0:
                    new_credits = current_credits - tax_amount
                    # 税金を徴収し、課税後残高を last_taxed_credits として記録
                    cur.execute("UPDATE users SET credits = %s, last_taxed_credits = %s WHERE user_id = %s", (new_credits, new_credits, user['user_id']))
                    total_tax_collected += tax_amount
                    users_taxed_count += 1
                else:
                    # 課税されなかった場合も、last_taxed_credits を現在の値に更新
                    cur.execute("UPDATE users SET last_taxed_credits = %s WHERE user_id = %s", (current_credits, user['user_id']))

        conn.commit()
        
        if users_taxed_count > 0:
            log_message = f"今週の所得税として、合計 `{total_tax_collected}` GTV を {users_taxed_count} 名から徴収したぞ。"
            print(f"[LOG] {log_message}")
            # BIRTHDAY_CHANNEL_ID に通知
            if BIRTHDAY_CHANNEL_ID:
                channel = bot.get_channel(BIRTHDAY_CHANNEL_ID)
                if channel:
                    await channel.send(log_message)
        else:
            print("[LOG] No tax was collected today.")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"DB Error in income tax task: {e}")
    finally:
        if conn:
            conn.close()

@tasks.loop(time=BIRTHDAY_NOTIFY_TIME)
async def check_birthdays_today():
    await bot.wait_until_ready()
    channel = bot.get_channel(BIRTHDAY_CHANNEL_ID)
    if not channel:
        print(f"Error: Birthday notification channel ID {BIRTHDAY_CHANNEL_ID} not found.")
        return

    today_str = datetime.now(JST).strftime('%m-%d')
    
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT user_id, age FROM users WHERE birthday = %s", (today_str,))
            birthday_users = cur.fetchall()

            if birthday_users:
                user_ids_to_update = [user['user_id'] for user in birthday_users if user['age'] is not None]
                if user_ids_to_update:
                    cur.execute("UPDATE users SET age = age + 1 WHERE user_id = ANY(%s)", (user_ids_to_update,))
                    print(f"[LOG] Incremented age for users: {user_ids_to_update}")

                mentions = [f"<@{user['user_id']}>" for user in birthday_users]
                message = (f"@everyone\n🎉🎂ハッピーバースデー！🎂🎉\n"
                           f"今日は {', '.join(mentions)} さんのお誕生日だ！みんなでお祝いするぞ！🥳")
                await channel.send("".join(message))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error in birthday task: {e}")

# Placeholder for the new scraping function
DMPS_BASE_URL = "https://dmps-tournament.takaratomy.co.jp/userresult.asp"

async def fetch_dmps_user_stats(dmps_player_id: str) -> Optional[Dict[str, int]]:
    """
    DMPS大会成績ページからランキングとポイントを取得する。
    """
    url = f"{DMPS_BASE_URL}?UserID={dmps_player_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        response.encoding = 'shift_jis' # 文字化け対策
        soup = BeautifulSoup(response.text, 'html.parser')

        # TOURNAMENT RANKINGの表示があるtd要素を探す
        # ユーザーが提供したHTMLを元にセレクタを調整
        # class="tx2022" align="left" のtd要素内にランキングとポイントがある
        ranking_td = soup.find('td', class_='tx2022', align='left')

        if not ranking_td:
            print(f"[LOG] DMPS stats: Could not find ranking_td for UserID: {dmps_player_id}")
            return None

        # TOURNAMENT RANKINGのテキストがあるspanを探す
        tournament_ranking_span = ranking_td.find('span', string='TOURNAMENT RANKING')
        if not tournament_ranking_span:
            print(f"[LOG] DMPS stats: Could not find 'TOURNAMENT RANKING' span for UserID: {dmps_player_id}")
            return None

        # ランキングとポイントは、TOURNAMENT RANKINGの後に続くfont-size:20pxのspanタグ内にある
        # 最初のfont-size:20pxのspanがランキング、次のfont-size:20pxのspanがポイント
        spans_20px = ranking_td.find_all('span', style='font-size:20px;')

        if len(spans_20px) < 2:
            print(f"[LOG] DMPS stats: Could not find enough 20px spans for rank/points for UserID: {dmps_player_id}")
            return None

        rank_str = spans_20px[0].get_text(strip=True)
        points_str = spans_20px[1].get_text(strip=True)

        # "位" や "pts" を除去して数値に変換
        rank = int(re.sub(r'[^0-9]', '', rank_str))
        points = int(re.sub(r'[^0-9]', '', points_str))

        return {'rank': rank, 'points': points}

    except requests.RequestException as e:
        print(f"[LOG] Error fetching DMPS user stats for UserID {dmps_player_id}: {e}")
        return None
    except (ValueError, AttributeError) as e:
        print(f"[LOG] Error parsing DMPS user stats for UserID {dmps_player_id}: {e}")
        return None

# New constant for DMPS update time
DMPS_UPDATE_TIME = dt_time(12, 0, 0, tzinfo=JST) # 正午に実行

@tasks.loop(time=DMPS_UPDATE_TIME)
async def update_dmps_points_task():
    await bot.wait_until_ready()
    conn = None
    granted_notifications = []
    
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # dmps_player_idが登録されているユーザーを取得
            cur.execute("SELECT user_id, dmps_player_id, dmps_points FROM users WHERE dmps_player_id IS NOT NULL;")
            users_to_update = cur.fetchall()

            if not users_to_update:
                print("[LOG] No users with DMPS Player ID registered.")
                return

            for user_data in users_to_update:
                user_id = user_data['user_id']
                dmps_player_id = user_data['dmps_player_id']
                old_points = user_data['dmps_points'] if user_data['dmps_points'] is not None else 0

                # スクレイピング関数を呼び出し
                stats = await fetch_dmps_user_stats(dmps_player_id)

                if stats:
                    new_rank = stats['rank']
                    new_points = stats['points']
                    
                    point_increase = new_points - old_points
                    credits_to_grant = 0

                    if point_increase > 0:
                        credits_to_grant = point_increase * 10
                        # クレジット付与通知をリストに追加
                        member = bot.get_user(user_id) # ユーザーオブジェクトを取得
                        if member:
                            granted_notifications.append(f"{member.display_name}さん: +{credits_to_grant} GTV ({point_increase} pts up)")
                        else:
                            granted_notifications.append(f"ユーザーID {user_id}: +{credits_to_grant} GTV ({point_increase} pts up)")

                    # DBを更新
                    cur.execute("""
                        UPDATE users SET dmps_rank = %s, dmps_points = %s, credits = credits + %s
                        WHERE user_id = %s;
                    """, (new_rank, new_points, credits_to_grant, user_id))
                else:
                    print(f"[LOG] Failed to fetch DMPS stats for UserID: {dmps_player_id}")
        
        conn.commit()

        # 通知チャンネルに結果を送信
        if granted_notifications and BIRTHDAY_CHANNEL_ID:
            channel = bot.get_channel(BIRTHDAY_CHANNEL_ID)
            if channel:
                message = "トーナメントランキングポイント増加によるGTV付与だぞ！みんなお疲れ様だ！\n" + "\n".join(granted_notifications)
                await channel.send(message)
        elif not granted_notifications:
            print("[LOG] No DMPS points increased today.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"DB Error in update_dmps_points_task: {e}")
    finally:
        if conn: conn.close()

# --- メイン実行ブロック ---
if __name__ == '__main__':
    if TOKEN is None: print("エラー: .envファイルで DISCORD_BOT_TOKEN を設定してください。")
    elif DATABASE_URL is None: print("エラー: .envファイルまたは環境変数で DATABASE_URL を設定してください。")
    else:
        keep_alive_thread()
        bot.run(TOKEN)
