# Pionex Crypto Scanner V2.2 — GitHub 自動補掃版

## 核心運作
- GitHub Actions 每 5 分鐘觸發一次檢查。
- 每次檢查讀取 Repository 根目錄 `state.json` 的 `last_successful_scan_utc`。
- 距離上次完整成功掃描未滿 20 分鐘：略過市場掃描，只留下 Actions log。
- 距離上次完整成功掃描已滿 20 分鐘：執行完整 USDT 永續合約掃描。
- 手動 `workflow_dispatch`：不論上次掃描時間，強制執行完整掃描。
- 只有所有合約均成功取得 K 線且掃描錯誤為 0，才更新成功時間。
- 部分失敗、API 429 或未完成掃描：不更新成功時間，後續排程再次嘗試。
- 若開始補掃時距離上次完整成功掃描超過 30 分鐘，會先嘗試發送 Telegram 異常提醒。

## 排程
- Cron：`2-57/5 * * * *`（UTC）
- 每小時 02、07、12、17、22、27、32、37、42、47、52、57 分觸發檢查。
- 這是每 5 分鐘檢查一次，不是每 5 分鐘掃描市場。
- 正常情況約每 20 分鐘完整掃描一次。
- GitHub Cron 仍可能延遲或漏觸發；如果 GitHub 連續漏掉所有檢查，本系統無法在沒有任何執行的情況下自行補救。

## GitHub 權限
Repository → Settings → Actions → General → Workflow permissions：
- 選擇 `Read and write permissions`。
- Workflow YAML 已指定 `contents: write` 與 `actions: read`。
- 使用 GitHub Actions 自動提供的 `GITHUB_TOKEN`，不需新增 PAT 或其他 Secret。
- `GITHUB_TOKEN` 會將 `state.json` 更新 commit 回目前分支。若 main 分支有禁止 GitHub Actions 推送的 branch protection/ruleset，需允許 Actions 更新 `state.json`，否則狀態無法保存。

## 策略及 API
- 保留 V2.1 原本的 4H、31 天、三個波段高點/低點、成交量遞減、RSI 遞減條件。
- 保留每次 Pionex API 請求至少間隔 1.15 秒，不以增加限流風險換取速度。
- 保留 Telegram TEST 輪詢、訊號格式及掃描統計。
- 不會自動下單。

## 注意
- `state.json` 會由 GitHub Actions 自動更新，請勿手動覆蓋掉最新的 `last_successful_scan_utc`。
- GitHub concurrency 同一 group 最多一個執行中與一個等待中工作；新的等待執行可能取代舊的等待執行。由於等待工作只負責檢查狀態，取代不會直接造成每個 5 分鐘檢查都必須保留。
- Private repository 的 GitHub Actions 免費額度需留意每 5 分鐘觸發所產生的使用量；Public repository 的標準 hosted runner 使用政策不同，請以 GitHub 當前方案為準。
