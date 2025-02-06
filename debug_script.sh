#!/bin/sh

echo "\n=== Telegram Service Debug Info ==="
echo "Python version: $(python3 --version)"
echo "Current directory: $(pwd)"
echo "Files in current directory:"
ls -la

echo "\n=== Environment Variables ==="
echo "TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:0:10}..."
echo "TELEGRAM_CHAT_ID: $TELEGRAM_CHAT_ID"
echo "PORT: $PORT"

echo "\n=== Redis Connection Test ==="
python3 -c "
import redis
try:
    r = redis.Redis(host='redis', port=6379, db=0)
    r.ping()
    print('Redis connection: Success')
except Exception as e:
    print(f'Redis connection failed: {str(e)}')
"

echo "\n=== Network Info ==="
echo "Checking connection to other services..."
nc -zv redis 6379 2>&1
nc -zv tradingview-chart-service 5000 2>&1
nc -zv tradingview-news-ai-service 5000 2>&1
nc -zv tradingview-calendar-service 5000 2>&1

echo "\n=== Service Logs ==="
tail -n 50 /var/log/telegram-service.log 2>/dev/null || echo "No log file found"

echo "\n=== End Debug Info ===" 