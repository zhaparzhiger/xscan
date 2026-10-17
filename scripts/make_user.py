"""Печатает строку пользователя для UI_USERS в .env.

    python scripts/make_user.py ilya          # спросит пароль
Несколько пользователей — через запятую: UI_USERS=ilya:pbkdf2$...,zhiger:pbkdf2$...
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.auth import hash_password  # noqa: E402

login = sys.argv[1] if len(sys.argv) > 1 else input("логин: ")
password = getpass.getpass("пароль: ")
if len(password) < 8:
    sys.exit("пароль короче 8 символов")
print(f"{login}:{hash_password(password)}")
