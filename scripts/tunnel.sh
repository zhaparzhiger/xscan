#!/usr/bin/env bash
# Публичный URL без VPS и без аккаунта: Cloudflare quick tunnel -> https://xxxx.trycloudflare.com
# Установка cloudflared: https://github.com/cloudflare/cloudflared/releases (один бинарник)
exec cloudflared tunnel --url "http://localhost:${PORT:-8000}"
