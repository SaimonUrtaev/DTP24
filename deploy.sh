#!/bin/bash
set -e

# Загружаем переменные из .env
set -a
source "$(dirname "$0")/.env"
set +a

YC=/Users/mac/yandex-cloud/bin/yc

echo "📦 Собираю zip..."
cd cloud_function
zip -j ../function.zip index.py requirements.txt credentials.json
cd ..

echo "☁️  Деплою функцию..."
$YC serverless function version create \
  --function-id "$YC_FUNCTION_ID" \
  --runtime python312 \
  --entrypoint index.handler \
  --memory 128m \
  --execution-timeout 20s \
  --source-path function.zip \
  --environment BOT_TOKEN="$BOT_TOKEN",SPREADSHEET_ID="$SPREADSHEET_ID",SHEET_NAME="$SHEET_NAME",CHAT_ID="$ALLOWED_USERS"

echo "🤖 Перезапускаю бота..."
pkill -TERM -f "python3 bot.py" 2>/dev/null || true
sleep 4
pkill -9 -f "python3 bot.py" 2>/dev/null || true
nohup python3 bot.py >> /tmp/bot.log 2>&1 &
sleep 2
tail -3 /tmp/bot.log
echo "✅ Готово!"
