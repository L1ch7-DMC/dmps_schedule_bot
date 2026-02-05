import discord
from discord.ext import tasks, commands
from datetime import datetime, timedelta
import psycopg2.extras

from ..config import JST, TAX_BRACKETS, TAX_COLLECTION_TIME, BIRTHDAY_CHANNEL_ID
from ..database import get_db_connection

@tasks.loop(time=TAX_COLLECTION_TIME)
async def collect_income_tax(bot: commands.Bot):
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
