"""Деплой на Hugging Face Spaces (Docker, бесплатный CPU): только сервер и интерфейс, без весов моделей.

Перед запуском один раз войти: .venv/Scripts/hf auth login  (токен с правом write).
    python deploy/hf_space.py <имя-space>            # например cashier-ai
Секреты (ключ API, вход в интерфейс, сервисный аккаунт) берутся из .env и передаются в Space как secrets —
в публичный репозиторий Space они не попадают. Данные датасета (data/) в Space не копируются.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent / "space"

SECRET_KEYS = ["API_KEY", "SESSION_SECRET", "UI_USERS", "UI_DEMO_LOGIN", "UI_DEMO_PASSWORD"]
VARIABLE_KEYS = ["ANALYZER", "GEMINI_MODEL", "WORKERS", "SAMPLE_FPS"]


def build(dst: Path) -> None:
    shutil.copytree(ROOT / "app", dst / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "design", dst / "design", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "requirements.txt", dst / "requirements.txt")
    for f in HERE.iterdir():
        shutil.copy(f, dst / f.name)


def eval_summary() -> str | None:
    """Замер без кадров датасета (кадры и видео организаторов публиковать нельзя) — для страницы «Замер»."""
    f = ROOT / "data" / "eval_report.json"
    if not f.exists():
        return None
    r = json.loads(f.read_text(encoding="utf-8"))
    for row in r["rows"]:
        row["still"] = ""
    return json.dumps(r, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "cashier-ai"
    env = dotenv_values(ROOT / ".env")
    api = HfApi()
    user = api.whoami()["name"]
    repo_id = f"{user}/{name}"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True, private=False)

    for k in VARIABLE_KEYS:
        if env.get(k):
            api.add_space_variable(repo_id, k, env[k])
    if "--no-secrets" not in sys.argv:
        for k in SECRET_KEYS:
            if env.get(k):
                api.add_space_secret(repo_id, k, env[k])
        sa = env.get("GOOGLE_APPLICATION_CREDENTIALS")
        if sa:
            api.add_space_secret(repo_id, "GOOGLE_CREDENTIALS_JSON", Path(sa).read_text(encoding="utf-8"))
        report = eval_summary()
        if report:
            api.add_space_secret(repo_id, "EVAL_REPORT_JSON", report)

    with tempfile.TemporaryDirectory() as d:
        build(Path(d))
        api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=d, commit_message="deploy")
    host = repo_id.replace("/", "-").replace("_", "-").lower()
    print(f"Space: https://huggingface.co/spaces/{repo_id}")
    print(f"Web interface URL: https://{host}.hf.space/design/")
    print(f"API base URL: https://{host}.hf.space")


if __name__ == "__main__":
    main()
