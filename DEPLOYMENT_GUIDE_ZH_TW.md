# OKX SMART TRADING V1.2 部署說明（繁體中文）

## 1. 環境需求
- Python 3.11/3.12
- Git
- Render Web Service
- 建議使用 Render PostgreSQL（正式環境不要依賴 ephemeral filesystem 的 SQLite）

## 2. 本機安裝
1. 解壓 ZIP。
2. 在專案根目錄建立虛擬環境：`python -m venv .venv`
3. 啟用虛擬環境。
4. 執行 `pip install -r requirements.txt`。
5. 複製 `.env.example` 為 `.env`。
6. 設定 `APP_SECRET_KEY`、`ADMIN_API_KEY`；LINE 尚未設定時保持 `LINE_ENABLED=false`。
7. 執行 `python app.py`。
8. 開啟 `http://127.0.0.1:5000`。

## 3. 測試
依序執行：
- `python -m compileall -q .`
- `python -m pytest -q`

測試必須在完整安裝 requirements 的環境執行。若有任何測試收集錯誤或失敗，不可宣稱驗收通過。

## 4. Render
1. 將專案上傳至 GitHub（不可上傳 `.env`）。
2. Render → New → Blueprint → 選擇 GitHub repository。
3. 確認 `render.yaml` 的 build/start command。
4. 建立 PostgreSQL，將內部連線 URL 設為 `DATABASE_URL`。
5. 設定 `APP_SECRET_KEY` 及 `ADMIN_API_KEY`。
6. 如需 LINE 通知，設定三項 LINE 環境變數並在測試成功後啟用 `LINE_ENABLED=true`。
7. 部署後先測 `/health`，再測 Dashboard、API、資料庫及 LINE。

## 5. 安全注意
- 不需要 OKX 私有 API 金鑰。
- 不允許真實下單；保持 `AUTO_TRADING_ENABLED=false`、`LIVE_ORDER_ENABLED=false`。
- 首次部署先保持 LINE 關閉，確認收件人及通知內容後再啟用。
- 若 Render 使用多個 web instances，確認排程不會重複啟動；建議掃描排程獨立成單一 worker。
- 設定 `TOP_N_SYMBOLS` 時需考慮 OKX rate limits 及掃描耗時，先以較小值測試。
