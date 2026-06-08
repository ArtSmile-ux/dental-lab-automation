#!/bin/bash
set -e
cd "$(dirname "$0")"

VENV="venv"
PORT=8000

if [ ! -d "$VENV" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"
pip install -q -r backend/requirements.txt

echo ""
echo "  ArtSmile Lab — сервер запущен"
echo "  Открой в браузере: http://localhost:$PORT"
echo "  Ctrl+C для остановки"
echo ""

cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
