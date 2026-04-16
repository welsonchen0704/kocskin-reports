# KOCSKIN Reports · 加密報表部署

內部儀表板，使用 staticrypt 前端加密 + GitHub Pages 託管。
同事只要記住一個網址和一組密碼即可查看。

---

## 第一次設定（一次性，約 15 分鐘）

### 1. 檢查環境

先確認電腦已安裝 Node.js（macOS 終端機）：

```bash
node -v
```

若顯示 `v18` 以上版本即可。若沒有，到 [nodejs.org](https://nodejs.org/) 下載 LTS 版本安裝。

### 2. 安裝 staticrypt

```bash
npm install -g staticrypt
staticrypt --version   # 確認顯示版本號即安裝成功
```

### 3. 在 GitHub 建立 repo

- 登入 GitHub，建立新 repo，名稱：`kocskin-reports`
- 設為 **Public**（私人 repo 無法用免費版 GitHub Pages，但即使 Public 內容也已被 staticrypt 加密）
- 先**不要**勾選 Add README / .gitignore，保持空白

### 4. Clone 並放入工具

```bash
cd ~/Documents   # 或你想放的位置
git clone https://github.com/welsonchen0704/kocskin-reports.git
cd kocskin-reports
```

然後把本資料夾的內容（`encrypt.sh`、`.gitignore`、`README.md`、`source/` 空資料夾）複製進去。

### 5. 給腳本執行權限

```bash
chmod +x encrypt.sh
```

### 6. 放入報表原始檔

把 Claude 產出的 `KOCSKIN_4月上半月_銷售廣告檢視.html` 改名為 `index.html`，放進 `source/` 資料夾：

```
kocskin-reports/
├── source/
│   └── index.html   ← 原始未加密版本（不會推上 GitHub）
├── encrypt.sh
├── .gitignore
└── README.md
```

### 7. 決定密碼並加密

**密碼建議**：12 字以上、英數混合、避免常見單字。例如 `Kocskin2026Review!`。

```bash
./encrypt.sh "Kocskin2026Review!"
```

執行後會產出 `index.html`（加密版），這個才是要上 GitHub 的檔案。

**密碼保存位置**：存在 Notion 的「品牌知識庫」或 1Password / Bitwarden，不要放在聊天記錄或 commit message。

### 8. 推上 GitHub

```bash
git add .
git commit -m "initial report 2026-04"
git push
```

### 9. 啟用 GitHub Pages

1. 到 repo 頁面 → **Settings** → 左側 **Pages**
2. **Source** 選 `Deploy from a branch`
3. **Branch** 選 `main`、資料夾選 `/ (root)`
4. 點 **Save**
5. 等 1–2 分鐘，頁面上方會顯示網址：`https://welsonchen0704.github.io/kocskin-reports/`

### 10. 告訴同事

Slack 私訊給 Vivian、派大、KK：

> 📊 KOCSKIN 內部報表入口
> 網址：https://welsonchen0704.github.io/kocskin-reports/
> 密碼：（單獨傳）
> 建議加入瀏覽器書籤，往後每週更新後，同一個網址即可看到最新版。

---

## 每週更新流程（5 分鐘）

### 步驟

1. 請 Claude 產出新一週的 HTML 報表
2. 把新 HTML 改名為 `index.html`，覆蓋 `source/index.html`
3. 終端機進入專案資料夾：
   ```bash
   cd ~/Documents/kocskin-reports
   ```
4. 執行加密：
   ```bash
   ./encrypt.sh "Kocskin2026Review!"
   ```
5. 推上 GitHub：
   ```bash
   git add .
   git commit -m "update 2026-04-30 report"
   git push
   ```
6. 1–2 分鐘後同事的網址會自動看到新版，不需通知

### 懶人一鍵版

把以下儲存為 `update.sh`（可選）：

```bash
#!/bin/bash
./encrypt.sh "$1" && \
git add . && \
git commit -m "update $(date +%Y-%m-%d)" && \
git push
```

執行：`./update.sh "你的密碼"`

---

## 常見狀況

### Q：同事打開網址只看到密碼輸入框？
正常，輸入密碼後即會解密顯示報表。勾選「Remember me」後 30 天內不需再輸入。

### Q：密碼不小心外流怎麼辦？
1. 決定新密碼
2. 重新執行 `./encrypt.sh "新密碼"`
3. `git add . && git commit -m "rotate password" && git push`
4. Slack 通知同事新密碼
舊密碼即失效。

### Q：報表太多人要存取，想要區分權限？
staticrypt 是單一密碼設計，無法區分角色。若要有個別帳號與權限，需升級到方案 C（Railway + Basic Auth）。

### Q：我還想要做舊版封存？
在 repo 內建立 `archive/2026-04/` 等資料夾，把舊的加密版 HTML 搬進去。URL 會變成 `/archive/2026-04/index.html`，同樣用現有密碼即可解鎖。

### Q：GitHub Pages 網址可以換成自有網域嗎？
可以。在 repo Settings > Pages 設定 Custom domain（例如 `reports.kocskin.com`），並在 Cloudflare 新增 CNAME 指向 `welsonchen0704.github.io`。這步可選。

---

## 安全性說明

- **加密強度**：AES-256 + PBKDF2 15,000 iterations。對短密碼（< 10 字）可被暴力破解，**務必用 12 字以上複雜密碼**。
- **原始未加密檔**：`source/` 在 `.gitignore` 內，不會被推上 GitHub。加密版 `index.html` 即使公開也無法讀取內容。
- **適用等級**：一般商業營運數據、月報、週報。若有個資、銀行帳戶、上市公司級機密，需改用伺服器端驗證（方案 C）。
- **密碼管理**：建議用 1Password / Bitwarden 管理，不要用 email、LINE、聊天工具傳遞密碼，改用面對面或 Slack 私訊且事後刪除。

---

## 資料夾結構（最終）

```
kocskin-reports/
├── source/                ← 本機原始檔（gitignore，不上傳）
│   └── index.html
├── archive/               ← 可選，歷史版本（上傳）
│   └── 2026-04/
│       └── index.html
├── encrypt.sh             ← 加密腳本
├── update.sh              ← 一鍵更新腳本（可選）
├── .gitignore
├── .staticrypt.json       ← salt 設定（上傳）
├── index.html             ← 加密版主入口（上傳）
└── README.md
```
