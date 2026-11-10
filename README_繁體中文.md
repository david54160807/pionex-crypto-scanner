# Pionex Crypto Scanner V2.0 — TEST 指令版

## 策略條件
- Pionex USDT 永續合約
- 4H K 線、最近 31 天
- 最近三個已確認 Swing High 持續抬高
- 最近三個已確認 Swing Low 持續抬高
- 三個高點對應 K 線成交量持續縮小
- 三個高點對應 RSI(14) 持續下降
- Swing High / Low 前後各 3 根 K 線確認
- 只使用已收盤 K 線

## 通知規則
- 不做訊號去重；每輪符合就重新通知。
- 不設 B 級階段。
- 不自動下單，只發送訊號。

## Telegram TEST 指令
在設定的 Telegram 對話傳送 `TEST`（大小寫不拘），程式會回傳一則測試通知。
- 只有 `TELEGRAM_CHAT_ID` 設定的對話可以觸發。
- 測試通知不是交易訊號，不會下單。
- 目前由 GitHub Actions 每 30 分鐘執行時輪詢 Telegram，因此不是即時回覆，通常在下一輪 Workflow 執行時回覆。
- 若 Bot 已設定 Telegram Webhook，`getUpdates` 輪詢可能無法使用，需先移除 Webhook。

## GitHub Secrets
設定：
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 更新
將本專案所有檔案覆蓋至 GitHub Repository，保留上述兩個 Secrets，然後在 Actions 手動執行測試。

## API 限流
- 單線程逐一請求。
- 每次請求至少間隔 1.15 秒。
- HTTP 429 冷卻後重試一次；仍失敗則停止本輪。
- 暫時性網路與 5xx 錯誤有限次重試。

本程式為技術型態篩選工具，不構成投資建議。

## 自動掃描排程
GitHub Actions 使用 UTC 排程 `0,30 * * * *`，台灣時間（UTC+8）對應每小時整點及 30 分執行，例如 09:00、09:30、10:00、10:30。GitHub Actions 可能因系統負載而稍有延遲。

## Telegram 通知版面（科技金融風格）
- 掃描完成後會發送科技金融風格的全市場統計報告。
- 符合策略的幣種會以獨立訊號卡片格式通知，保留三個 Swing High、三個 Swing Low、最新收盤價與 RSI。
- TEST 測試訊息也採用相同的 HTML 視覺格式。
- 使用 Telegram Bot API 支援的 HTML parse_mode，不會以圖片方式發送。
- 本次只調整通知呈現與啟用掃描摘要通知，不更動策略判斷、API 節流、TEST 輪詢或排程。
