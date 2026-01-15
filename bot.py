import os
import time
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from discord import Interaction, app_commands, ui, TextStyle, Embed
from typing import Optional
from dotenv import load_dotenv
from datetime import datetime, date, time as dt_time, timedelta, timezone
from urllib.parse import urljoin
import re
import threading
from flask import Flask
import random
import psycopg2
import psycopg2.extras

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

# --- Botのセットアップ ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

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
                birthday VARCHAR(5)
            )
        ''')
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
    "player_id": "デュエプレID", "achievements": "その他実績", "age": "年齢", "birthday": "誕生日"
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

        self.add_item(self.player_id)
        self.add_item(self.age)
        self.add_item(self.birthday)

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
        
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, player_id, age, birthday)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        player_id = EXCLUDED.player_id,
                        age = EXCLUDED.age,
                        birthday = EXCLUDED.birthday;
                """, (user_id, updates.get("player_id"), updates.get("age"), updates.get("birthday")))
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

# --- スラッシュコマンド ---
@bot.tree.command(name="register", description="あなたのプロフィール情報を登録・更新します。")
async def register_slash(interaction: Interaction):
    await interaction.response.send_message("登録したい情報の種類を選んでください。", view=RegisterView(target_user=interaction.user), ephemeral=True)

@bot.tree.command(name="profile", description="メンバーの情報を表示します。")
@app_commands.describe(user="情報を表示したいメンバー (指定がなければ自分)")
async def profile_slash(interaction: Interaction, user: Optional[discord.Member] = None):
    target_user = user or interaction.user
    user_data = get_user_profile(target_user.id)
    
    if not user_data or not any(user_data[key] for key in PROFILE_ITEMS):
        message = f"{target_user.display_name}の情報はまだ登録されていません。" + ("\n`/register`で登録してみよう！" if target_user == interaction.user else "")
        await interaction.response.send_message(message, ephemeral=True); return

    embed = Embed(title=f"{target_user.display_name}のプロフィール", color=target_user.color).set_thumbnail(url=target_user.display_avatar.url)
    for key, label in PROFILE_ITEMS.items():
        if key in user_data and user_data[key] is not None:
            embed.add_field(name=label, value=user_data[key], inline=True)
    await interaction.response.send_message(embed=embed)

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

# --- 管理者用コマンド ---
profile_admin = app_commands.Group(name="profile_admin", description="管理者用のプロフィール操作コマンド")

@profile_admin.command(name="edit", description="指定したユーザーの情報を対話形式で編集します。")
@app_commands.describe(user="情報を編集するユーザー")
@app_commands.checks.has_any_role(*ADMIN_ROLES)
async def profile_admin_edit(interaction: Interaction, user: discord.Member):
    await interaction.response.send_message(f"{user.display_name}の情報を編集します。", view=RegisterView(target_user=user), ephemeral=True)

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

# --- メイン実行ブロック ---
if __name__ == '__main__':
    if TOKEN is None: print("エラー: .envファイルで DISCORD_BOT_TOKEN を設定してください。")
    elif DATABASE_URL is None: print("エラー: .envファイルまたは環境変数で DATABASE_URL を設定してください。")
    else:
        keep_alive_thread()
        bot.run(TOKEN)