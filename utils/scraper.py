
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from typing import Optional, Dict, List
from datetime import datetime
from config import BASE_URL, DMPS_BASE_URL

def get_tonamel_url(details_page_url: str) -> str:
    """大会詳細ページからTonamelのURLを取得します。"""
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

def fetch_and_parse_tournaments() -> List[Dict]:
    """大会スケジュールページから大会情報を取得・解析します。"""
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
            time.sleep(0.2) # サーバーへの負荷軽減

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

async def fetch_dmps_user_stats(dmps_player_id: str) -> Optional[Dict[str, int]]:
    """DMPS大会成績ページからランキングとポイントを取得します。"""
    url = f"{DMPS_BASE_URL}?UserID={dmps_player_id}"
    try:
        # aiohttp を使うのが望ましいが、リファクタリングの範囲を超えるため requests を維持
        # 本来は非同期I/Oライブラリを使うべき
        response = await asyncio.to_thread(requests.get, url)
        response.raise_for_status()
        response.encoding = 'shift_jis'
        soup = BeautifulSoup(response.text, 'html.parser')

        ranking_td = soup.find('td', class_='tx2022', align='left')
        if not ranking_td:
            print(f"[LOG] DMPS stats: Could not find ranking_td for UserID: {dmps_player_id}")
            return None

        tournament_ranking_span = ranking_td.find('span', string='TOURNAMENT RANKING')
        if not tournament_ranking_span:
            print(f"[LOG] DMPS stats: Could not find 'TOURNAMENT RANKING' span for UserID: {dmps_player_id}")
            return None

        spans_20px = ranking_td.find_all('span', style='font-size:20px;')
        if len(spans_20px) < 2:
            print(f"[LOG] DMPS stats: Could not find enough 20px spans for rank/points for UserID: {dmps_player_id}")
            return None

        rank_str = spans_20px[0].get_text(strip=True)
        points_str = spans_20px[1].get_text(strip=True)

        rank = int(re.sub(r'[^0-9]', '', rank_str))
        points = int(re.sub(r'[^0-9]', '', points_str))

        return {'rank': rank, 'points': points}

    except requests.RequestException as e:
        print(f"[LOG] Error fetching DMPS user stats for UserID {dmps_player_id}: {e}")
        return None
    except (ValueError, AttributeError, IndexError) as e:
        print(f"[LOG] Error parsing DMPS user stats for UserID {dmps_player_id}: {e}")
        return None

# 非同期処理のための asyncio のインポート
import asyncio
