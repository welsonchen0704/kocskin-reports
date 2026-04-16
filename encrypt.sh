#!/bin/bash
# ============================================================
# KOCSKIN Reports - 加密腳本
# 用法：./encrypt.sh "你的密碼"
# 或：直接執行 ./encrypt.sh 會提示輸入密碼
# ============================================================

set -e  # 遇錯中止

# 取得密碼
if [ -z "$1" ]; then
  read -s -p "請輸入密碼: " PASSWORD
  echo
else
  PASSWORD="$1"
fi

# 檢查原始 HTML 存在
if [ ! -f "source/index.html" ]; then
  echo "❌ 找不到 source/index.html"
  echo "   請先把新版 HTML 報表存成 source/index.html"
  exit 1
fi

# 檢查 staticrypt 已安裝
if ! command -v staticrypt &> /dev/null; then
  echo "❌ 尚未安裝 staticrypt"
  echo "   請執行：npm install -g staticrypt"
  exit 1
fi

# 執行加密
echo "🔒 加密中..."
staticrypt source/index.html \
  -p "$PASSWORD" \
  -d . \
  -o index.html \
  --template-title "KOCSKIN Reports" \
  --template-instructions "請輸入內部密碼查看報表" \
  --template-button "查看報表" \
  --template-color-primary "#8c6b22" \
  --template-color-secondary "#f7f2e6" \
  --template-placeholder "密碼"

echo "✅ 完成！加密版已輸出為 index.html"
echo ""
echo "下一步："
echo "  git add ."
echo "  git commit -m \"update report $(date +%Y-%m-%d)\""
echo "  git push"
