import discord
from discord.ext import tasks, commands
import psycopg2.extras

from ..config import JST, DMPS_UPDATE_TIME, BIRTHDAY_CHANNEL_ID
from ..database import get_db_connection
from ..utils.web_scraper import fetch_dmps_user_stats

@tasks.loop(time=DMPS_UPDATE_TIME)
async def dmps_credit_updater(bot: commands.Bot):
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
        print(f"DB Error in dmps_credit_updater task: {e}")
    finally:
        if conn: conn.close()