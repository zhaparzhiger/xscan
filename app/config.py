"""Настройки сервиса. Всё читается из переменных окружения (или .env)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

API_KEY = os.getenv("API_KEY", "change-me")
# vlm — анализ мультимодальной моделью по API (app/pipeline/vlm.py), local — CLIP + детектор, полностью офлайн
ANALYZER = os.getenv("ANALYZER", "local").strip().lower()
SAMPLE_FPS = float(os.getenv("SAMPLE_FPS", "4"))
WORKERS = int(os.getenv("WORKERS", "1"))
DETECTOR_THRESHOLD = os.getenv("DETECTOR_THRESHOLD")  # None -> из модели
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
# Жёсткий бюджет на одно видео: жюри ждёт максимум 5 минут
JOB_TIME_BUDGET_SEC = float(os.getenv("JOB_TIME_BUDGET_SEC", "240"))

DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
JOBS_DIR = DATA_DIR / "jobs"
MODELS_DIR = ROOT / "models"
RULES_FILE = ROOT / "app" / "rules" / "violations.yaml"
STATIC_DIR = ROOT / "app" / "static"

CLIP_MODEL = os.getenv("CLIP_MODEL", "ViT-B-32")
CLIP_PRETRAINED = os.getenv("CLIP_PRETRAINED", "laion2b_s34b_b79k")

for d in (UPLOAD_DIR, JOBS_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)
