"""Скачивает модели «нового стека» в models/ (нужны на новой машине): Qwen3-VL-4B, SigLIP 2, SAM 2.1.

    python scripts/download_extra_models.py            # всё (~9 ГБ)
    python scripts/download_extra_models.py qwen3vl4b  # только одну
Все три — Apache 2.0. После загрузки интернет не нужен (HF_HUB_OFFLINE=1).
"""
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

MODELS = {
    "qwen3vl4b": "Qwen/Qwen3-VL-4B-Instruct",
    "siglip2": "google/siglip2-base-patch16-224",
    "sam21": "facebook/sam2.1-hiera-small",
}
root = Path(__file__).resolve().parent.parent / "models"
for name in sys.argv[1:] or MODELS:
    print("->", name, MODELS[name], flush=True)
    snapshot_download(MODELS[name], local_dir=root / name)
print("готово")
