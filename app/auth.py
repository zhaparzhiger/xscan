"""Вход в веб-интерфейс: логин/пароль -> подписанная cookie-сессия. API жюри по-прежнему работает по X-API-Key.

Пользователи задаются в .env:  UI_USERS=ilya:pbkdf2$<salt>$<hash>,zhiger:pbkdf2$...
Строку для пользователя печатает:  python scripts/make_user.py <логин>
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets
import threading
import time

from fastapi import HTTPException, Request

from app import config  # noqa: F401 — подгружает .env до чтения переменных

log = logging.getLogger(__name__)

COOKIE = "cashier_session"
SESSION_TTL = 12 * 3600
MAX_FAILS, FAIL_WINDOW = 5, 300  # 5 неудачных попыток за 5 минут -> пауза

_secret = os.getenv("SESSION_SECRET", "").encode()
if not _secret:
    _secret = secrets.token_bytes(32)
    log.warning("SESSION_SECRET не задан: сессии сбросятся при перезапуске")

_fails: dict[str, list[float]] = {}
_lock = threading.Lock()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2${salt}${digest}"


def _users() -> dict[str, str]:
    out = {}
    for item in os.getenv("UI_USERS", "").split(","):
        if ":" in item:
            login, stored = item.strip().split(":", 1)
            out[login] = stored
    return out


def demo_credentials() -> dict | None:
    """Учётка для жюри: показывается на экране входа. Включать только на время проверки."""
    login, password = os.getenv("UI_DEMO_LOGIN", ""), os.getenv("UI_DEMO_PASSWORD", "")
    return {"login": login, "password": password} if login and password else None


def _check(login: str, password: str) -> bool:
    demo = demo_credentials()
    if demo and hmac.compare_digest(login, demo["login"]) and hmac.compare_digest(password, demo["password"]):
        return True
    stored = _users().get(login)
    if not stored or not stored.startswith("pbkdf2$"):
        hash_password(password)  # одинаковое время ответа для несуществующего логина
        return False
    _, salt, _digest = stored.split("$", 2)
    return hmac.compare_digest(hash_password(password, salt), stored)


def _sign(payload: str) -> str:
    return hmac.new(_secret, payload.encode(), hashlib.sha256).hexdigest()


def make_token(login: str) -> str:
    payload = f"{login}|{int(time.time()) + SESSION_TTL}"
    return base64.urlsafe_b64encode(f"{payload}|{_sign(payload)}".encode()).decode()


def read_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        login, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split("|")
    except Exception:  # noqa: BLE001 — битая cookie = нет сессии
        return None
    if not hmac.compare_digest(sig, _sign(f"{login}|{exp}")) or int(exp) < time.time():
        return None
    demo = demo_credentials()
    return login if login in _users() or (demo and login == demo["login"]) else None


def login(request: Request, user: str, password: str) -> str:
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
        _fails[ip] = recent
        if len(recent) >= MAX_FAILS:
            raise HTTPException(status_code=429, detail="Слишком много попыток. Подождите 5 минут.")
    if not _check(user, password):
        log.warning("неудачный вход: login=%r ip=%s", user[:64], ip)
        with _lock:
            _fails.setdefault(ip, []).append(now)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    log.info("вход: %s ip=%s", user, ip)
    return make_token(user)


def require_session(request: Request) -> str:
    user = read_token(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


def is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
