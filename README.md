# KOCSKIN 銷售週報自動產生器 (v3)

自動化腳本 + GitHub Actions 組合，功能：

1. 定時從 Google Drive 的 `KOCSKIN_週報` 讀取 **2 個 91APP 報表**
   - 商店銷售統計表*.xlsx
   - 商品報表*.csv
2. 自動從 **Facebook Marketing API** 拉廣告成效（不用再手動下載 CSV）
3. 自動從 **GA4 Data API** 拉流量分析（新分頁）
4. 三個資料來源若有更新，重新產出 HTML 儀表板
5. 解析時剔除所有「成本 / 毛利 / 利潤」相關欄位
6. 用 **staticrypt** 做 AES-256 前端密碼加密
7. Commit 回 repo 並透過 GitHub Pages 發布
8. 每次執行在 `logs/` 留記錄

---

## 一次性部署步驟

### 1. 建立 private GitHub repo

```bash
# 名稱: kocskin-weekly-report
# 可見度: Private
```

把這整個資料夾 push：

```bash
cd kocskin-weekly-report
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin git@github.com:<你的帳號>/kocskin-weekly-report.git
git push -u origin main
```

### 2. 啟用 GitHub Pages

Repo → Settings → Pages → Source: `GitHub Actions`

> ⚠️ Private repo 的 Pages 網址仍對外公開，因此必須開 staticrypt 加密。

### 3. Google Service Account（同時給 Drive + GA4 用）

1. <https://console.cloud.google.com/> → 新建或選既有專案
2. 「API 和服務」→ 啟用：
   - **Google Drive API**
   - **Google Analytics Data API**
3. 「IAM → 服務帳戶」→ 建立 → 名稱 `kocskin-report-reader`
4. 進入服務帳戶 → 「金鑰」→ 新增金鑰 → JSON → 下載
5. 複製服務帳戶 email（`xxx@xxx.iam.gserviceaccount.com`）
6. 到 Google Drive 的 `KOCSKIN_週報` 資料夾 → 共用 → 把這個 email 加進去（檢視者）
7. 到 GA4 → 管理 → 屬性存取管理 → 新增使用者 → 貼上這個 email → 角色「檢視者」即可

### 4. Facebook 存取權杖（Long-Lived User Token，60 天）

1. 到 <https://developers.facebook.com/tools/explorer/>
2. 右上角選擇你的應用程式（沒有的話先建一個 Business 類型 App）
3. User or Page → 選 `User Token`
4. 權限勾：
   - `ads_read`
   - `business_management`（如果廣告帳號屬於 BM）
5. 按 `Generate Access Token` → 拿到短期 token（1 小時）
6. 換長期 token：開 <https://developers.facebook.com/tools/debug/accesstoken/> → 貼入短期 token → 按「Extend Access Token」→ 拿到 60 天的 Long-Lived User Token
7. 廣告帳號 ID: `act_2053421094961197`

> ⚠️ **60 天後會過期**。腳本會在到期前 10 天自動在 log 中紅字提醒。到期後：重複 5–6 步再換一次 token，更新 GitHub Secret `FB_ACCESS_TOKEN` 即可。
>
> 更永久解法：在 Business Manager 建立 System User Token → 永不過期。之後有需要可再切換。

### 5. GA4 Property ID

GA4 後台 → 管理 → 屬性設定 → 屬性詳細資料 → **屬性 ID**（9 位數字，例如 `320123456`）

### 6. 設定 GitHub Repo Secrets

Repo → Settings → Secrets and variables → Actions → New repository secret

| Secret 名稱 | 內容 |
|---|---|
| `GDRIVE_SERVICE_ACCOUNT_JSON` | 步驟 3 下載的 JSON 檔完整內容 |
| `REPORT_PASSWORD` | 員工解鎖 HTML 的密碼（12 碼以上） |
| `FB_ACCESS_TOKEN` | 步驟 4 的 Long-Lived User Token |
| `FB_AD_ACCOUNT_ID` | `act_2053421094961197`（已預設） |
| `GA4_PROPERTY_ID` | 步驟 5 的屬性 ID（9 位數字或 `properties/xxx` 都行） |

（選配）Variables：

| Variable | 內容 |
|---|---|
| `DRIVE_FOLDER_NAME` | 若 Drive 資料夾名不是 `KOCSKIN_週報` |

### 7. 測試執行

Repo → Actions → `Generate KOCSKIN Weekly Report` → `Run workflow`

第一次會讀 Drive 的兩個 91APP 檔、拉 FB 與 GA 資料、產生 `dist/index.html` 並部署到 Pages。

網址：`https://<你的帳號>.github.io/kocskin-weekly-report/`

---

## 日常使用

每週把兩份最新檔案丟進 Google Drive 的 `KOCSKIN_週報`：

- `商店銷售統計表_*.xlsx`
- `商品報表*.csv`

（FB 廣告與 GA 流量都走 API，不用再手動下載）

**檔案可以覆蓋或新增不同檔名都 OK**，程式會挑最新 mtime 的那份。

排程：每天 UTC 02:10（台灣 10:10 AM）自動跑。

## Exit code

| Exit code | 意義 |
|---|---|
| 0 | 成功產出並發布 |
| 2 | 2 個檔沒集齊（缺檔） |
| 3 | 檔案沒更新，不重跑 |
| 1 | 錯誤（看 Actions log） |

## FB Token 到期處理

- Log 中每次執行會顯示目前 token 有效天數
- ≤10 天會紅字警告
- 失效就重做上面第 4 步，更新 `FB_ACCESS_TOKEN` Secret

## 本地測試

```bash
pip install -r requirements.txt
npm install -g staticrypt   # 或讓 npx 自動抓

# 把兩份 91APP 檔放到 downloads/
mkdir -p downloads
cp /path/to/商店銷售統計表_*.xlsx downloads/
cp /path/to/商品報表*.csv downloads/

# 設環境變數
export SERVICE_ACCOUNT_JSON="$(cat /path/to/service_account.json)"
export FB_ACCESS_TOKEN="EAAxxxxxxx..."
export FB_AD_ACCOUNT_ID="act_2053421094961197"
export GA4_PROPERTY_ID="320123456"

# 跑（不加密）
LOCAL_ONLY=1 SKIP_ENCRYPT=1 python3 generate_report.py

# 加密
LOCAL_ONLY=1 REPORT_PASSWORD=yourpassword python3 generate_report.py

# 產出: dist/index.html
```

## 報表內容

**銷售資料分頁**：訂單數、訂單金額（ECOM 實際營收）、取消金額、淨銷售、客單價、取消率、退貨率、商品數

**廣告資料分頁**：廣告花費、Blended ROAS、Meta 歸因 ROAS、Meta 歸因購買、曝光、Active/Inactive 廣告 ROAS、Meta 歸因 / ECOM 實際比

**GA 流量分頁**：Sessions / Users / PV、每日趨勢、流量來源、裝置分布、Top Landing Pages

**絕不會出現**：成本、毛利、毛利率、利潤（腳本在解析階段就剔除）

## 檔案結構

```
.
├── generate_report.py            # 主腳本
├── fb_api_client.py              # FB Marketing API
├── ga_api_client.py              # GA4 Data API
├── requirements.txt
├── .github/workflows/weekly.yml  # GitHub Actions (cron)
├── templates/report_template.html
├── state/
│   ├── history.json              # 累積歷史
│   └── last_run.json
├── logs/YYYYMM.log
├── dist/index.html               # 加密成品 (發布到 Pages)
└── downloads/                    # 執行時暫存 (.gitignore)
```

## 安全

- 原始 xlsx/csv 不會 commit 到 repo（`.gitignore` 已排除）
- 所有 token / password / service account 只存 GitHub Secrets
- `history.json` 在 private repo
- 對外只有加密 HTML
- staticrypt 用 AES-256 + PBKDF2；**密碼外流等於全公開**，請定期輪換

## 調整執行頻率

編輯 `.github/workflows/weekly.yml` 的 cron（UTC）：

```yaml
- cron: '10 2 * * *'   # 每天 UTC 02:10 = 台灣 10:10（目前）
- cron: '10 */6 * * *' # 每 6 小時
- cron: '0 2 * * 1'    # 每週一 UTC 02:00
```
