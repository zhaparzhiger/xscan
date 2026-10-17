#!/usr/bin/env bash
# Запуск сервиса: http://localhost:8000
set -e
cd "$(dirname "$0")/.."
[ -f .env ] || { cp .env.example .env; echo "создан .env — поменяй API_KEY"; }
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
