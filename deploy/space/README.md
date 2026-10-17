---
title: Cashier AI
emoji: 🏦
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

Cashier AI — проверка видео кассы на признаки нарушений кассовой дисциплины.

- Веб-интерфейс: `/design/`
- API: `POST /api/v1/analyze` (multipart `file`, заголовок `X-API-Key`), `GET /api/v1/jobs/{job_id}`
