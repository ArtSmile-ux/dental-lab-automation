#!/bin/bash
# Запускать на ВАШЕМ MAC
# Использование: ./upload_to_server.sh <IP_СЕРВЕРА>

SERVER_IP="$1"
if [ -z "$SERVER_IP" ]; then
    echo "Укажите IP сервера: ./upload_to_server.sh 12.34.56.78"
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Отправка файлов на сервер $SERVER_IP ==="

# Создаём папку на сервере
ssh root@$SERVER_IP "mkdir -p /root/dental-lab"

# Копируем проект (без venv и лишних файлов)
rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.git' --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal' \
    --exclude='*.db.bak_*' --exclude='node_modules' \
    "$PROJECT_DIR/" root@$SERVER_IP:/root/dental-lab/

echo "=== Файлы загружены ==="
echo ""
echo "Теперь выполните на сервере:"
echo "  ssh root@$SERVER_IP"
echo "  cd /root/dental-lab"
echo "  bash deploy.sh"
