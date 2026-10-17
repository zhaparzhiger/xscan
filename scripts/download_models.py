"""Скачать веса заранее (один раз, с интернетом). После этого сервис работает офлайн."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.pipeline import features  # noqa: E402

features.embed_texts(["warmup"])
print("веса CLIP скачаны в models/clip")
