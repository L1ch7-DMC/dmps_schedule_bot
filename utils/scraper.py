import asyncio
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import Optional, Dict, List
from datetime import datetime

from config import BASE_URL, DMPS_BASE_URL

# =====================
# 共通：安全なHTTP取得
# =====================
def safe_get(url: str, encoding: str, timeout: int = 10) -> Optional[str]:
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"
            }
        )
        response.raise_for_status()
        response.encoding = encoding
        return response.text
    except requests.RequestException as e:
        print(f"[LOG] Request failed: {url} | {e}")
        return None


# =====================
# Tonamel URL取得
# =====================
async def get_tonamel_url(details_page_url: str) -> str:
    html = await asyncio.to_thread(
        safe_get,
        details_page_url,
        "cp932"
    )
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for keyword in ("大会HP", "リモート使用アプリ"):
        span = soup.find("span", string=re.compile(keyword))
        if not span:
            continue

        td = span.find_parent("td")
        if not td:
            continue

        a = td.find("a", href=True)
        if a and "tonamel.com" in a["href"]:
            return a["href"]

    return ""


# =====================
# 大会一覧取得（非同期）
# =====================
async def fetch_and_parse_tournaments() -> List[Dict]:
    html = await asyncio.to_thread(
        safe_get,
        BASE_URL,
        "shift_jis"
    )
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="main")
    if not table:
        return []

    tournaments: List[Dict] = []

    rows = table.find_all("tr")[1:]
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 8:
            continue

        onclick = row.get("onclick", "")
        relative_url = onclick.split("'")[1] if "'" in onclick else ""
        details_page_url = urljoin(BASE_URL, relative_url)

        tonamel_url = await get_tonamel_url(details_page_url)

        try:
            tournaments.append({
                "date": datetime.strptime(
                    cols[0].get_text(strip=True),
                    "%y/%m/%d"
                ).date(),
                "name": cols[2].get_text(strip=True),
                "format": cols[4].get_text(strip=True),
                "capacity": cols[6].get_text(strip=True),
                "time": cols[7].get_text(strip=True),
                "url": tonamel_url or details_page_url,
            })
        except ValueError:
            continue

        # Render対策：sleepは必ずasync
        await asyncio.sleep(0.2)

    tournaments.sort(key=lambda x: (x["date"], x["time"]))
    return tournaments


# =====================
# DMPS 成績取得（非同期）
# =====================
async def fetch_dmps_user_stats(dmps_player_id: str) -> Optional[Dict[str, int]]:
    url = f"{DMPS_BASE_URL}?UserID={dmps_player_id}"

    try:
        response = await asyncio.to_thread(
            requests.get,
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"
            }
        )
        response.raise_for_status()
        response.encoding = "shift_jis"
        soup = BeautifulSoup(response.text, "html.parser")

        ranking_td = soup.find("td", class_="tx2022", align="left")
        if not ranking_td:
            return None

        spans_20px = ranking_td.find_all("span", style="font-size:20px;")
        if len(spans_20px) < 2:
            return None

        rank = int(re.sub(r"\D", "", spans_20px[0].get_text()))
        points = int(re.sub(r"\D", "", spans_20px[1].get_text()))

        return {
            "rank": rank,
            "points": points
        }

    except Exception as e:
        print(f"[LOG] DMPS fetch error ({dmps_player_id}): {e}")
        return None
