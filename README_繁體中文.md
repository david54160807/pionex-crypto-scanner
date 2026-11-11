# Pionex Crypto Scanner V2.1

## 策略條件
- Pionex USDT 永續合約
- 4H K 線、最近 31 天
- 最近三個已確認 Swing High 持續抬高
- 最近三個已確認 Swing Low 持續抬高
- 三個高點對應 K 線成交量持續縮小
- 三個高點對應 RSI(14) 持續下降
- Swing High / Low 前後各 3 根 K 線確認
- 只使用已收盤 K 線

## 自動排程
- GitHub Actions Cron：`7,27,47 * * * *`（UTC）
- 台灣時間：每小時 07、27、47 分執行。
- GitHub Actions 排程可能受平台負載影響而延遲；Cron 不是準時執行保證。
- 本版本會查詢 GitHub Actions Run API，記錄 Workflow 建立時間、開始時間與 Queue Time，協助分辨平台排隊延遲與程式掃描耗時。
- 若 Queue Time 超過 5 分鐘，會在 Actions log 顯示警告。
- 手動執行仍可透過 `workflow_dispatch` 使用。

## 執行與 API
- 保留逐一請求及每次請求至少間隔 1.15 秒，避免未經驗證地提高 Pionex API 請求頻率。
- K 線下載、策略條件與訊號判斷不變。
- 單次工作逾時上限 25 分鐘。
- 保留 concurrency，避免同一時間多個掃描工作同時呼叫 API。
- 更新 GitHub Actions checkout/setup-python 至支援較新 Node runtime 的版本。

## Telegram 通知
- Secrets 必須設定 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`。
- 符合策略的幣種逐一發送訊號。
- 每輪掃描完成後發送全市場統計。
- `TEST` 指令由每輪 Actions 執行時輪詢，並非即時 webhook。
- 不做訊號去重；每輪符合就重新通知。
- 不自動下單。

## GitHub 權限
Repository → Settings → Actions → General：
- Actions permissions：允許 Actions 執行。
- Workflow permissions：Read and write 或 Read repository contents 均可；本版本額外在 workflow 層明確指定 `actions: read`、`contents: read`，用於讀取本次 Workflow Run 的排隊時間。
- `GITHUB_TOKEN` 由 GitHub Actions 自動提供，不需要新增 Repository Secret。

## 安裝更新
將本 ZIP 內 `pionex-crypto-scanner-main` 資料夾中的所有檔案覆蓋至 Repository 的 `main` 分支，保留原有兩組 Telegram Secrets。確認 `.github/workflows/scanner.yml` 位於預設分支後，至 Actions 手動執行一次測試。

## 重要限制
Queue Time 診斷能指出 GitHub Workflow 從建立到開始的等待時間，但無法強制 GitHub 在 Cron 指定分鐘準時啟動。若 GitHub 平台本身延遲，仍需考慮外部排程器或常駐 VPS。
