# Steam Free Games Discord Bot

這是一個用 Python 寫的簡單機器人，可以自動偵測 Steam 上的限時免費遊戲，並發送通知到你的 Discord 頻道。

## 準備工作

### 1. 安裝環境
確保你的電腦已經安裝了 **Python 3.11+**。

在資料夾中打開終端機 (cmd)，執行以下指令來安裝需要的套件：
```bash
pip install -r requirements.txt
```

### 2. 取得 API Key 與 Webhook URL

#### Discord Webhook
1.  在你的 Discord 伺服器建立一個新頻道 (例如 `#free-games`)。
2.  編輯頻道 -> 整合 -> Webhooks -> 建立 Webhook。
3.  複製 **Webhook URL**。

#### IsThereAnyDeal API Key
1.  前往 [IsThereAnyDeal Developer](https://isthereanydeal.com/dev/app/)。
2.  建立一個 App (Personal)。
3.  複製 **API Key**。

### 3. 設定 Bot
打開 `bot.py` 檔案，找到最上方的設定區，填入你的資訊：

```python
# ===== 設定區（請填入你自己的資訊）=====
DISCORD_WEBHOOK_URL = "在這裡貼上你的Webhook URL"
ITAD_API_KEY = "在這裡貼上你的IsThereAnyDeal API Key"
# ==========================================
```

## 執行機器人
在終端機中執行：
```bash
python bot.py
```
機器人啟動後，會立即檢查一次，之後每 30 分鐘檢查一次。

## 部署建議
如果要 24 小時運行，建議部署到雲端主機 (如 Oracle Cloud Free Tier) 並使用 `screen` 工具讓它在背景執行。
