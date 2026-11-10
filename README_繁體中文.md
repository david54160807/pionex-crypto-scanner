# Pionex Crypto Scanner V2.0

以 Pionex USDT 永續合約市場為資料來源，掃描 4H K 線最近 31 天的型態，符合條件時透過 Telegram 發送通知。

## V2.0 策略條件

必須同時符合以下四項：

1. 最近三個已確認 Swing High 高點逐次抬高。
2. 最近三個已確認 Swing Low 低點逐次抬高。
3. 三個 Swing High 所在 K 線的成交量逐次縮小。
4. 三個 Swing High 對應的 RSI(14) 逐次下降。

參數：
- K 線：4H
- 觀察區間：最近 31 天
- Swing High / Low：前後各 3 根 K 線確認
- RSI：Wilder RSI(14)
- 僅使用已收盤 K 線
- 每 30 分鐘由 GitHub Actions 排程掃描

## 通知規則

- 不做通知去重。
- 每一輪掃描，只要某幣符合四項條件，就重新發送 Telegram 通知。
- 不設 B 級階段。
- 不會自動下單，只發送型態通知。

## 專案結構

```text
pionex-crypto-scanner/
├── .github/
│   └── workflows/
│       └── scanner.yml
├── main.py
├── pionex_api.py
├── strategy.py
├── telegram_bot.py
├── get_chat_id.py
├── requirements.txt
├── .gitignore
└── README_繁體中文.md
```

## GitHub Secrets

在 GitHub Repository → Settings → Secrets and variables → Actions 新增：

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

不需要設定 Pionex API Key，因為本程式只讀取公開市場行情，不執行交易。

## 更新步驟

1. 將本專案檔案上傳或覆蓋到 GitHub Repository 根目錄。
2. 確認兩個 Telegram Secrets 已存在。
3. 開啟 Actions。
4. 選擇 `Pionex 4H Crypto Scanner V2.0`。
5. 點擊 `Run workflow` 進行第一次測試。

## 限流保護

- 單線程逐一請求 K 線。
- 每次請求至少間隔 1.15 秒。
- 遇到 HTTP 429，依 Retry-After 或至少 60 秒冷卻後重試一次。
- 冷卻後仍收到 HTTP 429，停止本輪掃描。
- 暫時性網路或 5xx 錯誤有限次重試。

## 注意事項

本工具為技術型態篩選器，不是交易指令。縮量與 RSI 背離不保證價格反轉。合約交易涉及槓桿、爆倉與資金損失風險，請自行評估。
