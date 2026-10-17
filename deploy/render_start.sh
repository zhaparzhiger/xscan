#!/bin/sh
# Render: секрет с ключом сервисного аккаунта -> файл; сводка замера -> страница «Замер»; сервер на $PORT
mkdir -p data
if [ -n "$GOOGLE_CREDENTIALS_JSON" ]; then
  printf '%s' "$GOOGLE_CREDENTIALS_JSON" > /tmp/sa.json
  export GOOGLE_APPLICATION_CREDENTIALS=/tmp/sa.json
fi
[ -f data/eval_report.json ] || cp deploy/eval_summary.json data/eval_report.json 2>/dev/null || true
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"
