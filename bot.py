import requests
import time
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# 載入 .env 檔案 (本地開發用)
load_dotenv()

# ===== 設定區（請填入你自己的資訊）=====
# 優先讀取環境變數 (GitHub Actions 或 .env)，若未設定則為空
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
ITAD_API_KEY = os.environ.get("ITAD_API_KEY", "")

CHECK_INTERVAL = 1800  # 檢查間隔（秒），1800 = 30 分鐘
SEEN_FILE = "seen_deals.json"
# ==========================================


def log(message):
    """印出帶時間戳的日誌"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


def load_seen():
    """讀取已通知過的遊戲清單"""
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    """儲存已通知過的遊戲清單"""
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def get_free_games_itad():
    """從 IsThereAnyDeal 取得 Steam 上 100% 折扣的遊戲"""
    if not ITAD_API_KEY:
        log("未設定 ITAD_API_KEY，跳過 ITAD 檢查")
        return []

    url = "https://api.isthereanydeal.com/deals/list/v2"
    params = {
        "key": ITAD_API_KEY,
        "shops": "61",       # 61 = Steam 的 shop ID
        "sort": "cut:desc",
        "cut": 100,           # 100% 折扣
        "limit": 50
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log(f"ITAD API 錯誤: {e}")
        return []

    free_games = []
    for deal in data.get("list", []):
        game_id = deal.get("id", "")
        title = deal.get("title", "未知遊戲")

        # 取得價格資訊
        deal_info = deal.get("deal", {})
        price_cut = deal_info.get("cut", 0)
        regular_price = deal_info.get("regular", {}).get("amount", 0)
        store_url = deal_info.get("url", "")

        if price_cut == 100:
            free_games.append({
                "id": game_id,
                "name": title,
                "original_price": regular_price,
                "url": store_url if store_url else f"https://store.steampowered.com/search/?term={title}",
            })

    return free_games


def get_free_games_steam():
    """備用方案：直接從 Steam API 抓取 (精選分類)"""
    url = "https://store.steampowered.com/api/featuredcategories"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log(f"Steam API 錯誤: {e}")
        return []

    free_games = []

    for category_key in ["specials", "coming_soon", "top_sellers"]:
        category = data.get(category_key, {})
        items = category.get("items", [])
        for game in items:
            if game.get("discount_percent") == 100:
                app_id = game.get("id")
                free_games.append({
                    "id": str(app_id),
                    "name": game.get("name", "未知遊戲"),
                    "original_price": game.get("original_price", 0) / 100,
                    "url": f"https://store.steampowered.com/app/{app_id}",
                    "header_image": game.get("header_image", ""),
                })

    return free_games


def get_free_games_steam_search():
    """地毯式搜索：直接爬取 Steam 搜尋結果 (抓漏網之魚)"""
    # 搜尋條件：特價中 + 價格從低到高排序
    url = "https://store.steampowered.com/search/results/"
    params = {
        "query": "",
        "start": 0,
        "count": 50,
        "dynamic_data": "",
        "sort_by": "Price_ASC",
        "specials": 1,
        "infinite": 1
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        
        # Steam 搜尋 API 返回的是 JSON，其中 'results_html' 包含 HTML 片段
        data = resp.json()
        html_content = data.get("results_html", "")
        
        soup = BeautifulSoup(html_content, "html.parser")
        games = []
        
        # 遍歷每一個搜尋結果
        for item in soup.find_all("a", class_="search_result_row"):
            try:
                # 檢查折扣趴數
                discount_div = item.find("div", class_="search_discount")
                if not discount_div:
                    continue
                    
                discount_text = discount_div.get_text(strip=True) # 例如 "-100%"
                
                # 嚴格判定：必須是 -100%
                if "-100%" in discount_text:
                    game_id = item.get("data-ds-appid")
                    title_span = item.find("span", class_="title")
                    title = title_span.get_text(strip=True) if title_span else "未知遊戲"
                    
                    # 取得連結
                    store_url = item.get("href", "")
                    # 去除連結中的 tracking 參數
                    if "?" in store_url:
                        store_url = store_url.split("?")[0]

                    # 取得原價
                    price_div = item.find("strike")
                    original_price = 0
                    if price_div:
                        price_str = price_div.get_text(strip=True).replace("$", "").replace(",", "")
                        try:
                            original_price = float(price_str)
                        except:
                            original_price = 0
                            
                    games.append({
                        "id": game_id,
                        "name": title,
                        "original_price": original_price,
                        "url": store_url,
                        "header_image": get_game_header_image(game_id)
                    })
            except Exception as e:
                log(f"解析遊戲出錯: {e}")
                continue
                
        return games

    except Exception as e:
        log(f"Steam 地毯式搜索錯誤: {e}")
        return []


def get_game_header_image(app_id):
    """取得遊戲的封面圖片"""
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"


def send_discord_notification(game):
    """發送 Discord 通知"""
    if not DISCORD_WEBHOOK_URL:
        log("未設定 Webhook URL，跳過通知")
        return

    # 嘗試取得封面圖
    image_url = game.get("header_image", "")
    if not image_url and game.get("id", "").isdigit():
        image_url = get_game_header_image(game["id"])

    # 原價顯示
    original = game.get("original_price", 0)
    if isinstance(original, (int, float)) and original > 0:
        price_text = f"~~${original:.2f}~~ → **免費**"
    else:
        price_text = "**免費**"

    embed = {
        "embeds": [{
            "title": f"🎮  {game['name']}",
            "url": game.get("url", ""),
            "description": "這款遊戲目前 **100% 折扣**，限時免費領取！\n快去 Steam 領取吧！",
            "color": 0x00ff00,  # 綠色
            "fields": [
                {
                    "name": "💰 價格",
                    "value": price_text,
                    "inline": True
                },
                {
                    "name": "🔗 連結",
                    "value": f"[點此前往 Steam]({game.get('url', '')})",
                    "inline": True
                }
            ],
            "image": {"url": image_url} if image_url else {},
            "footer": {
                "text": f"Steam 免費遊戲通知 • {datetime.now().strftime('%Y/%m/%d %H:%M')}"
            }
        }]
    }

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=embed, timeout=10)
        if resp.status_code == 204:
            log(f"✅ 通知成功: {game['name']}")
        elif resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 5)
            log(f"⚠️ 被限速，等待 {retry_after} 秒...")
            time.sleep(retry_after)
            requests.post(DISCORD_WEBHOOK_URL, json=embed, timeout=10)
        else:
            log(f"❌ 通知失敗 ({resp.status_code}): {resp.text}")
    except Exception as e:
        log(f"❌ 發送錯誤: {e}")


def send_startup_message():
    """機器人啟動通知"""
    if not DISCORD_WEBHOOK_URL:
        return

    payload = {
        "embeds": [{
            "title": "🤖 Steam 免費遊戲通知機器人已啟動",
            "description": f"每 {CHECK_INTERVAL // 60} 分鐘檢查一次 Steam 免費遊戲 (含地毯式搜索)",
            "color": 0x3498db,
            "footer": {
                "text": datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            }
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass


def main():
    log("=" * 50)
    log("Steam 免費遊戲通知機器人啟動中... (已啟用地毯式搜索)")
    log(f"檢查間隔: {CHECK_INTERVAL} 秒 ({CHECK_INTERVAL // 60} 分鐘)")
    log("=" * 50)
    
    # 清理舊紀錄 (保留30天內)
    seen = load_seen()
    cutoff = datetime.now().timestamp() - (30 * 86400)
    seen = {
        k: v for k, v in seen.items()
        if datetime.fromisoformat(v.get("found_at", datetime.now().isoformat())).timestamp() > cutoff
    }

    send_startup_message()

    while True:
        log("開始檢查免費遊戲...")

        # 1. IsThereAnyDeal
        free_games = get_free_games_itad()
        log(f"ITAD 找到 {len(free_games)} 款免費遊戲")

        # 2. Steam 官方 (精選分類)
        steam_games = get_free_games_steam()
        log(f"Steam (官方API) 找到 {len(steam_games)} 款免費遊戲")
        
        # 3. Steam 地毯式搜索 (新功能)
        search_games = get_free_games_steam_search()
        log(f"Steam (地毯搜索) 找到 {len(search_games)} 款免費遊戲")

        # 合併結果（用遊戲名稱去重）
        all_games = {}
        # 合併順序：API -> ITAD -> 搜索 (確保資訊最豐富的優先)
        for game in steam_games + free_games + search_games:
            key = game.get("name", game.get("id", ""))
            # 用 ID 當 Key 比較準，如果沒有 ID 才用 Name
            game_id = game.get("id")
            if game_id and game_id not in all_games:
                 all_games[game_id] = game
            elif key and key not in all_games:
                 all_games[key] = game
        
        log(f"去除重複後共 {len(all_games)} 款遊戲")

        new_count = 0
        for key, game in all_games.items():
            game_id = game.get("id", key)
            if game_id not in seen:
                send_discord_notification(game)
                seen[game_id] = {
                    "name": game.get("name"),
                    "found_at": datetime.now().isoformat()
                }
                new_count += 1
                time.sleep(2)  # 避免 Discord 限速

        save_seen(seen)

        if new_count == 0:
            log("沒有新的免費遊戲")
        else:
            log(f"本次新通知 {new_count} 款遊戲")

        # GitHub Actions 模式：執行一次後就結束 (避免無限迴圈佔用資源)
        if os.environ.get("RUN_ONCE") == "true":
            log("GitHub Actions 模式：執行完畢，自動結束")
            break

        log(f"下次檢查: {CHECK_INTERVAL // 60} 分鐘後")
        log("-" * 40)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
