


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
import json

# --- 設定 ---
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID')) if os.getenv('DISCORD_CHANNEL_ID') else 0
ADMIN_ROLE_NAMES_STR = os.getenv('ADMIN_ROLE_NAMES')
ADMIN_ROLES = [role.strip() for role in ADMIN_ROLE_NAMES_STR.split(',')] if ADMIN_ROLE_NAMES_STR else []

BASE_URL = "https://dmps-tournament.takaratomy.co.jp/schedulehost.asp"
MEMBERS_DATA_FILE = "members_data.json"
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

# --- JSONデータ管理 ---
def load_members_data():
    if not os.path.exists(MEMBERS_DATA_FILE): return {}
    try:
        with open(MEMBERS_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {}

def save_members_data(data):
    with open(MEMBERS_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- プロフィール項目定義 ---
PROFILE_ITEMS = {
    "top100": "ランクマッチ最終TOP100", "nd_rate": "ND最高レート", "ad_rate": "AD最高レート",
    "player_id": "デュエプレID", "achievements": "その他実績", "age": "年齢", "birthday": "誕生日"
}
NUMERIC_ITEMS = ["top100", "nd_rate", "ad_rate", "player_id", "age"]

# --- Webスクレイピング関数 ---
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

# --- プロフィール登録用UI ---
class AchievementModal(ui.Modal, title='実績情報の登録'):
    def __init__(self, user: discord.User):
        super().__init__()
        user_data = load_members_data().get(str(user.id), {})

        self.top100 = ui.TextInput(label=PROFILE_ITEMS["top100"], style=TextStyle.short, required=False, placeholder="例: 1", default=str(user_data.get("top100", "")))
        self.nd_rate = ui.TextInput(label=PROFILE_ITEMS["nd_rate"], style=TextStyle.short, required=False, placeholder="例: 1600", default=str(user_data.get("nd_rate", "")))
        self.ad_rate = ui.TextInput(label=PROFILE_ITEMS["ad_rate"], style=TextStyle.short, required=False, placeholder="例: 1600", default=str(user_data.get("ad_rate", "")))
        self.achievements = ui.TextInput(label=PROFILE_ITEMS["achievements"], style=TextStyle.paragraph, required=False, placeholder="例: ドルマゲドンXCUP最終1位", default=user_data.get("achievements", ""))
        
        self.add_item(self.top100)
        self.add_item(self.nd_rate)
        self.add_item(self.ad_rate)
        self.add_item(self.achievements)

    async def on_submit(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        data = load_members_data()
        user_data = data.setdefault(user_id, {})
        
        # 数値項目を処理
        for item_key, text_input in [("top100", self.top100), ("nd_rate", self.nd_rate), ("ad_rate", self.ad_rate)]:
            if text_input.value:
                try:
                    user_data[item_key] = int(text_input.value)
                except ValueError:
                    await interaction.response.send_message(f"「{PROFILE_ITEMS[item_key]}」には数値を入力してください。", ephemeral=True); return
            elif item_key in user_data:
                del user_data[item_key]
        
        # テキスト項目を処理
        if self.achievements.value:
            user_data["achievements"] = self.achievements.value
        elif "achievements" in user_data:
            del user_data["achievements"]
            
        save_members_data(data)
        await interaction.response.send_message('実績情報を更新したぞ！', ephemeral=True)

class PersonalInfoModal(ui.Modal, title='個人情報の登録'):
    def __init__(self, user: discord.User):
        super().__init__()
        user_data = load_members_data().get(str(user.id), {})

        self.player_id = ui.TextInput(label=PROFILE_ITEMS["player_id"], style=TextStyle.short, required=False, placeholder="例: 123456789", default=str(user_data.get("player_id", "")))
        self.age = ui.TextInput(label=PROFILE_ITEMS["age"], style=TextStyle.short, required=False, placeholder="例: 20", default=str(user_data.get("age", "")))
        self.birthday = ui.TextInput(label=PROFILE_ITEMS["birthday"], style=TextStyle.short, required=False, placeholder="例: 01-15 (MM-DD形式)", default=user_data.get("birthday", ""))

        self.add_item(self.player_id)
        self.add_item(self.age)
        self.add_item(self.birthday)

    async def on_submit(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        data = load_members_data()
        user_data = data.setdefault(user_id, {})

        if self.player_id.value:
            try:
                user_data["player_id"] = int(self.player_id.value)
            except ValueError:
                await interaction.response.send_message(f"「{PROFILE_ITEMS['player_id']}」には数値を入力してください。", ephemeral=True); return
        elif "player_id" in user_data:
            del user_data["player_id"]

        if self.age.value:
            try:
                user_data["age"] = int(self.age.value)
            except ValueError: await interaction.response.send_message(f"「{PROFILE_ITEMS['age']}」には数値を入力してください。", ephemeral=True); return
        elif "age" in user_data: del user_data["age"]
        
        if self.birthday.value:
            if not re.fullmatch(r"\d{2}-\d{2}", self.birthday.value):
                await interaction.response.send_message(f"「{PROFILE_ITEMS['birthday']}」は `MM-DD` 形式で入力してください。", ephemeral=True); return
            user_data["birthday"] = self.birthday.value
        elif "birthday" in user_data: del user_data["birthday"]
        
        save_members_data(data)
        await interaction.response.send_message('個人情報を更新したぞ！', ephemeral=True)

class RegisterView(ui.View):
    def __init__(self): super().__init__(timeout=180)
    @ui.button(label="実績を登録", style=discord.ButtonStyle.primary)
    async def register_achievements(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(AchievementModal(user=interaction.user))
    @ui.button(label="個人情報を登録", style=discord.ButtonStyle.secondary)
    async def register_personal_info(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(PersonalInfoModal(user=interaction.user))

# --- スラッシュコマンド ---
@bot.tree.command(name="register", description="あなたのプロフィール情報を登録・更新します。")
async def register_slash(interaction: Interaction): await interaction.response.send_message("登録したい情報の種類を選んでください。", view=RegisterView(), ephemeral=True)

@bot.tree.command(name="profile", description="メンバーの情報を表示します。")
@app_commands.describe(user="情報を表示したいメンバー (指定がなければ自分)")
async def profile_slash(interaction: Interaction, user: Optional[discord.Member] = None):
    target_user = user or interaction.user
    user_data = load_members_data().get(str(target_user.id))
    if not user_data:
        message = f"{target_user.display_name}の情報はまだ登録されていません。" + ("\n`/register`で登録してみよう！" if target_user == interaction.user else "")
        await interaction.response.send_message(message, ephemeral=True); return
    embed = Embed(title=f"{target_user.display_name}のプロフィール", color=target_user.color).set_thumbnail(url=target_user.display_avatar.url)
    for key, label in PROFILE_ITEMS.items():
        if key in user_data: embed.add_field(name=label, value=user_data[key], inline=True)
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

# --- 管理者用コマンド ---
profile_admin = app_commands.Group(name="profile_admin", description="管理者用のプロフィール操作コマンド")
@profile_admin.command(name="set", description="指定したユーザーの情報を変更します。")
@app_commands.describe(user="情報を変更するユーザー", item="変更する項目", value="新しい値")
@app_commands.choices(item=[app_commands.Choice(name=label, value=key) for key, label in PROFILE_ITEMS.items()])
@app_commands.checks.has_any_role(*ADMIN_ROLES)
async def profile_admin_set(interaction: Interaction, user: discord.Member, item: app_commands.Choice[str], value: str):
    user_id, item_key, item_name = str(user.id), item.value, item.name
    data = load_members_data()
    user_data = data.setdefault(user_id, {})
    if item_key in NUMERIC_ITEMS:
        try: user_data[item_key] = int(value)
        except ValueError: await interaction.response.send_message(f"「{item_name}」には数値を入力する必要があります。", ephemeral=True); return
    elif item_key == "birthday":
        if not re.fullmatch(r"\d{2}-\d{2}", value):
            await interaction.response.send_message(f"「{item_name}」は `MM-DD` 形式で入力する必要があります。", ephemeral=True); return
        user_data[item_key] = value
    else: user_data[item_key] = value
    save_members_data(data)
    await interaction.response.send_message(f"{user.display_name}の「{item_name}」を更新しました。", ephemeral=True)

@profile_admin.command(name="delete", description="指定したユーザーのプロフィール情報をすべて削除します。")
@app_commands.describe(user="情報を削除するユーザー")
@app_commands.checks.has_any_role(*ADMIN_ROLES)
async def profile_admin_delete(interaction: Interaction, user: discord.Member):
    user_id = str(user.id)
    data = load_members_data()
    if user_id in data:
        del data[user_id]
        save_members_data(data)
        await interaction.response.send_message(f"{user.display_name}のプロフィール情報を削除しました。", ephemeral=True)
    else:
        await interaction.response.send_message(f"{user.display_name}のプロフィール情報は登録されていません。", ephemeral=True)
bot.tree.add_command(profile_admin)

# --- イベントハンドラ ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
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
    all_data = load_members_data()
    birthday_members = [user_id for user_id, user_data in all_data.items() if user_data.get('birthday') == today_str]

    if birthday_members:
        # 年齢をインクリメントする処理
        for user_id in birthday_members:
            user_data = all_data.get(user_id)
            if user_data and 'age' in user_data:
                try:
                    current_age = int(user_data['age'])
                    user_data['age'] = current_age + 1
                    print(f"[LOG] Incremented age for user {user_id} to {user_data['age']}")
                except (ValueError, TypeError):
                    print(f"[LOG] Could not increment age for user {user_id}. 'age' is not a valid number.")
        
        # 変更を保存
        save_members_data(all_data)

        # 誕生日通知メッセージを送信
        mentions = [f"<@{user_id}>" for user_id in birthday_members]
        message = (f"@everyone\n🎉🎂ハッピーバースデー！🎂🎉\n"
                   f"今日は {', '.join(mentions)} さんのお誕生日だ！みんなでお祝いするぞ！🥳")
        await channel.send(message)

# --- メイン実行ブロック ---
if __name__ == '__main__':
    if TOKEN is None: print("エラー: .envファイルで DISCORD_BOT_TOKEN を設定してください。")
    else:
        keep_alive_thread()
        bot.run(TOKEN)

