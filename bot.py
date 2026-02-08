import requests
import time
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# 載入 .env 檔案 (本地開發用)
load_dotenv()

# ===== 設定區（請填入你自己的資訊）=====
# 優先讀取環境變數 (GitHub Actions 或 .env)，若未設定則為空 (避免上傳 Key)
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
    """備用方案：直接從 Steam API 抓取"""
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


def get_game_header_image(app_id):
    """取得遊戲的封面圖片"""
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"


def send_discord_notification(game):
    """發送 Discord 通知"""
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
    payload = {
        "embeds": [{
            "title": "🤖 Steam 免費遊戲通知機器人已啟動",
            "description": f"每 {CHECK_INTERVAL // 60} 分鐘檢查一次 Steam 免費遊戲",
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
    log("Steam 免費遊戲通知機器人啟動中...")
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

        # 主要來源：IsThereAnyDeal
        free_games = get_free_games_itad()
        log(f"ITAD 找到 {len(free_games)} 款免費遊戲")

        # 備用來源：Steam 官方
        steam_games = get_free_games_steam()
        log(f"Steam 找到 {len(steam_games)} 款免費遊戲")

        # 合併結果（用遊戲名稱去重）
        all_games = {}
        for game in free_games + steam_games:
            key = game.get("name", game.get("id", ""))
            if key and key not in all_games:
                all_games[key] = game

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
