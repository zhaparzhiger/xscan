#!/bin/sh
# секреты Space -> файлы, которые ждёт сервис
[ -n "$GOOGLE_CREDENTIALS_JSON" ] && printf '%s' "$GOOGLE_CREDENTIALS_JSON" > /tmp/sa.json
[ -n "$EVAL_REPORT_JSON" ] && printf '%s' "$EVAL_REPORT_JSON" > data/eval_report.json
exec uvicorn app.main:app --host 0.0.0.0 --port 7860
