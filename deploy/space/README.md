---
title: XScan
emoji: 🏦
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

XScan — проверка видео кассы на признаки нарушений кассовой дисциплины.

- Веб-интерфейс: `/design/`
- API: `POST /api/v1/analyze` (multipart `file`, заголовок `X-API-Key`), `GET /api/v1/jobs/{job_id}`
