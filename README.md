# OKX SMART TRADING V1.2 — Final Integration Candidate

繁體中文量化掃描與模擬交易系統。此版本以 V1.1 Stage 3 ROUND8 為基礎增量整合，保留原始 LONG-A / LONG-B / SHORT-A / SHORT-B、四個 V1.1 雷達及形態掃描模組。

> **安全模式：SIMULATION ONLY。** 專案不包含 OKX 私有交易 API、下單、撤單或槓桿設定端點。不要自行加入真實下單功能。訊號及回測結果不是獲利保證。

## 功能

- OKX V5 公開行情：USDT 線性永續合約清單、ticker、K 線。
- 原始四策略：LONG-A、LONG-B、SHORT-A、SHORT-B。
- V1.1 四雷達：RADAR-LONG-A、RADAR-LONG-B、RADAR-SHORT-A、RADAR-SHORT-B。
- 指標及市場分析：EMA、Supertrend、RSI、MACD、OBV、ADX/DMI、ATR、Bollinger Bands、成交量均線、BTC 相對強弱。
- 形態：Gartley、Bat、Alternate Bat、Butterfly、Crab、Deep Crab、Cypher、5-0、Shark（O-X-A-B-C）、AB=CD/PRZ 相關模組，以及雙頂雙底、頭肩型態、三驅動、通道、楔形/三角形、旗形、突破/回踩/假突破候選。
- 週期：1W、1D、4H、1H；15M 僅作為輔助進場時機週期，無法取得時不應中斷高週期掃描。
- 提前預警與確認訊號分離；確認訊號只使用已收盤 K 線。
- 模擬風險管理、歷史回測、LINE Messaging API 通知、Flask 手機 Dashboard、SQLite/PostgreSQL 資料層。

## 本輪整合修改

- OKX `15M` 週期映射為 V5 API 要求的 `15m` bar 字串。
- PatternScanner 接受 15M 輔助週期。
- SignalEngine 以 best-effort 方式取得已收盤 15M K 線；15M 取數失敗不會把高週期分析判成失敗。
- 更新應用程式名稱為 V1.2。

## 本地安裝

Python 3.11 或 3.12：

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env  # Windows 可手動複製
```

編輯 `.env`，至少設定 `APP_SECRET_KEY`、`ADMIN_API_KEY`。測試階段可先不啟用 LINE。

啟動：

```bash
python app.py
```

## 測試

```bash
python -m compileall -q .
python -m pytest -q
```

完整測試需要安裝 `requirements.txt` 中的 Flask、psycopg[binary] 等套件。沒有成功執行完整測試前，不可將版本標示為已通過最終驗收。請參閱 `FINAL_ACCEPTANCE_REPORT.md` 的本次實際執行結果及未完成驗證項目。

## Render 部署

1. 將專案根目錄推送至自己的 GitHub repository。
2. Render 選擇 New → Blueprint，連接 repository，讀取 `render.yaml`。
3. 設定 `APP_SECRET_KEY`、`ADMIN_API_KEY`。
4. 建立 PostgreSQL 資料庫，將 Render Internal Database URL 設定為 `DATABASE_URL`。
5. 需要 LINE 時再設定 `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`、`LINE_TO_USER_ID`，最後才將 `LINE_ENABLED=true`。
6. 部署後先測試 `/health`、`/api/status`，再用 Dashboard 管理密碼測試掃描。
7. Render 背景排程/多 worker 啟動方式需避免多實例重複掃描；正式使用前確認只啟動一個 scheduler worker。

**不要將 `.env`、Token、密碼或任何 API secret 上傳 GitHub。** 本系統只需要 OKX 公開市場資料，不需要 OKX API Key/Secret/Passphrase。

## 驗收邊界

此工作環境沒有 Flask、psycopg 套件且無法透過網路安裝，因此本次無法誠實宣稱 Flask 測試、PostgreSQL 實際連線、LINE 實際推播、OKX 線上 API 或 Render 部署已驗證。此 ZIP 是整合候選包，不應被當成已完成全部驗收的 production final。
