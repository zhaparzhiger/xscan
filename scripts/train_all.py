"""Полный цикл обучения одной командой: разметка -> CLIP-признаки -> детектор (models/detector.joblib).

Датасет организаторов: папка XSCAN_VIDEOS (*.mov) и open_labels.xlsx уровнем выше (как в open.zip).

    python scripts/train_all.py            # признаки считаются один раз, потом кэш data/features
    python scripts/train_all.py --no-aug   # без аугментаций (в 4 раза быстрее)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402,F401  (подхватывает .env)

ap = argparse.ArgumentParser()
ap.add_argument("--no-aug", action="store_true")
a = ap.parse_args()

videos = Path(os.environ.get("XSCAN_VIDEOS", Path.home() / "Downloads/open/videos"))
xlsx = videos.parent / "open_labels.xlsx"
if not any(videos.glob("*.mov")) or not xlsx.exists():
    sys.exit(f"нет датасета: нужны {videos}\\*.mov и {xlsx}")


def run(*args):
    print("\n$", " ".join(map(str, args)), flush=True)
    subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True)


run("ml/prepare_labels.py", "--xlsx", xlsx, "--videos", videos)
run("ml/extract_features.py", "--videos", videos, *([] if a.no_aug else ["--aug"]))
run("ml/train.py", "--videos", videos)
