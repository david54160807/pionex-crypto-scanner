# Pionex USDT 永續合約 4H 型態掃描器 V1.0

使用 Pionex 公開 API 掃描所有 `TRADING` 狀態的 USDT 永續合約，每 30 分鐘由 GitHub Actions 執行一次，符合條件時透過 Telegram 推播。

## V1.0 條件

1. 4H K 線，最近 31 天（186 根已完成 K 線）。
2. Pivot High / Pivot Low：左右各 3 根 K 線確認。
3. 最近三個已確認波段高點：`H1 < H2 < H3`。
4. 最近三個已確認波段低點：`L1 < L2 < L3`。
5. 三個高點所在 K 線的 base-asset 成交量：`V1 > V2 > V3`。
6. 三個高點所在 K 線的 Wilder RSI(14)：`R1 > R2 > R3`。
7. 最新已完成 K 線收盤價不得低於最近一個已確認波段低點。

> 這是型態掃描，不是交易訊號或獲利保證。成交量欄位依 Pionex K 線 API 定義為 base currency volume；不同幣種之間不可直接拿數值大小比較，本策略只比較同一幣種三個高點之間的量。

## 重要設計

- 不需要 Pionex API Key；只呼叫公開市場 API。
- 不具備下單功能，不會連接或操作 Pionex 帳戶。
- 不使用未完成的 4H K 線。
- 取得 220 根 K 線，為 RSI 提供暖機資料；型態高低點只在最近 186 根內尋找。
- 每個幣種只在新的高點/低點組合形成時通知一次；狀態保存於 `state.json`。
- GitHub Actions 每小時 :17、:47 執行。排程不是即時保證，GitHub 高負載時可能延遲。
- 每個 symbol 一次 K 線請求，併發限制 4；如市場合約數量大或遇到 API rate limit，需降低併發或改為分批掃描。

## 1. 建立 Telegram Bot

1. 在 Telegram 搜尋官方 `@BotFather`。
2. 傳送 `/newbot`。
3. 輸入 Bot 顯示名稱，例如 `Pionex 4H Scanner`。
4. 輸入唯一 username，必須以 `bot` 結尾，例如 `my_pionex_4h_scanner_bot`。
5. BotFather 會回傳 Token。把 Token 當成密碼，不要貼到公開 GitHub 或聊天群組。
6. 搜尋你剛建立的 Bot，按 **Start**，再傳送 `/start`。

### 取得 Chat ID

最簡單方式：使用瀏覽器開啟以下網址，將 `<BOT_TOKEN>` 換成自己的 Token：

`https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`

在回傳 JSON 中找：

`message` → `chat` → `id`

這個數字就是私人聊天的 `TELEGRAM_CHAT_ID`。若沒有結果，先對 Bot 傳送 `/start` 再重新整理。

也可本機執行 `get_chat_id.py`；先安裝 `pip install -r requirements.txt`，並設定環境變數 `TELEGRAM_BOT_TOKEN`。

## 2. 建立 GitHub 公開儲存庫

1. 登入 GitHub。
2. 點選 New repository。
3. Repository name：`pionex-crypto-scanner`。
4. 選擇 **Public**。
5. 建立儲存庫。
6. 將本專案所有檔案上傳，保留 `.github/workflows/scanner.yml` 路徑。
7. 確認 `main` 是預設分支。

## 3. 設定 GitHub Secrets

進入儲存庫：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

新增兩個 Secret：

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather 提供的 Token |
| `TELEGRAM_CHAT_ID` | 你的 Telegram 私人 chat ID |

不要把 Token 或 Chat ID 寫進 Python 原始碼。

## 4. 啟用 Actions

1. 點選儲存庫的 **Actions** 分頁。
2. 若 GitHub 要求啟用 Actions，請按啟用。
3. 找到 `Pionex 4H Crypto Scanner`。
4. 點選 `Run workflow`，手動執行第一次測試。
5. 查看執行紀錄；成功後，Telegram 應在出現新訊號時收到通知。
6. 確認 `state.json` 有被 Actions 更新提交。

## 5. GitHub 權限設定

在 `Settings` → `Actions` → `General` → `Workflow permissions`：
選擇 **Read and write permissions**，讓 Workflow 可以更新 `state.json`。

## 6. 掃描時間

Workflow cron 為 `17,47 * * * *`，即每小時第 17、47 分執行。GitHub Actions 的排程可能延遲，不是精準定時服務。

公開儲存庫若連續 60 天沒有儲存庫活動，GitHub 可能自動停用 scheduled workflow。請定期查看 Actions，並保持儲存庫有活動。

## 7. 常見問題

### Telegram 沒有收到訊息
- 確認你已經對 Bot 按 Start。
- 確認 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 完全正確。
- 在 Actions log 查看是否有 `缺少 ... Secrets` 或 Telegram API 錯誤。
- 只有新形成的訊號組合才會通知；不是每次掃描都重複推送。

### Actions 執行成功，但沒有訊號
代表目前沒有幣種同時符合四項條件及額外低點防守條件，不代表程式失效。可從 Actions log 確認掃描合約數與錯誤數。

### API 請求失敗
- Pionex 公開 API 或網路可能暫時不可用。
- 程式有簡單重試及 4 路併發限制。
- 如果大量合約造成 API 限流，將 `max_workers=4` 改為 `2`，或在 `pionex_api.py` 每次請求間增加短暫延遲。

### 想每次掃描都收到摘要
在 Workflow 的 `SEND_SCAN_SUMMARY` 改成 `"true"`。注意每30分鐘都會收到訊息，可能造成通知過多。

### 想修改策略
在 `strategy.py` 修改：
- `LOOKBACK_BARS = 186`
- `PIVOT_LEFT = 3`
- `PIVOT_RIGHT = 3`
- `RSI_PERIOD = 14`

## API 來源

- Pionex Futures Common：`GET /api/v1/common/symbols?type=PERP&status=TRADING`
- Pionex Futures Market Klines：`GET /api/v1/market/klines?symbol=...&interval=4H&limit=220`
- Telegram Bot API：`sendMessage`
- GitHub Actions schedule events

官方文件：
- https://www.pionex.com/docs/api-docs/futures-api/common
- https://www.pionex.com/docs/api-docs/futures-api/market
- https://core.telegram.org/bots/api
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
