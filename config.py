import os
from dotenv import load_dotenv
from datetime import datetime, date, time as dt_time, timedelta, timezone

# --- 設定 ---
load_dotenv()
TOKEN_CREDIT = os.getenv('DISCORD_BOT_TOKEN_CREDIT')
TOKEN_MAIN = os.getenv('DISCORD_BOT_TOKEN_MAIN')
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

# --- プロフィール項目定義 ---
PROFILE_ITEMS = {
    "top100": "ランクマッチ最終TOP100", "nd_rate": "ND最高レート", "ad_rate": "AD最高レート",
    "player_id": "デュエプレID", "achievements": "その他実績", "age": "年齢", "birthday": "誕生日",
    "dmps_player_id": "DMPSプレイヤーID"
}
NUMERIC_ITEMS = ["top100", "nd_rate", "ad_rate", "player_id", "age"]

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

# Placeholder for the new scraping function
DMPS_BASE_URL = "https://dmps-tournament.takaratomy.co.jp/userresult.asp"
DMPS_UPDATE_TIME = dt_time(12, 0, 0, tzinfo=JST) # 正午に実行
