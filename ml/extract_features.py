"""Считает CLIP-эмбеддинги кадров для всех видео датасета и кэширует в data/features/*.npz.

Самая долгая часть (CPU: ~10–30 с на ролик). Запускается один раз; train.py потом учится за секунды.
--aug добавляет аугментированные "ракурсы" (отражение, кроп, перспектива) — для устойчивости к другому углу съёмки.

    python ml/extract_features.py --videos ~/Downloads/open/videos --aug
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.pipeline import features, video  # noqa: E402


def augment(frames: list[np.ndarray], kind: str, rng: np.random.Generator) -> list[np.ndarray]:
    h, w = frames[0].shape[:2]
    if kind == "flip":
        return [cv2.flip(f, 1) for f in frames]
    if kind == "crop":
        s = rng.uniform(0.75, 0.9)
        ch, cw = int(h * s), int(w * s)
        y, x = rng.integers(0, h - ch + 1), rng.integers(0, w - cw + 1)
        return [cv2.resize(f[y:y + ch, x:x + cw], (w, h)) for f in frames]
    if kind == "persp":  # имитация другого угла камеры
        d = 0.12
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        jitter = rng.uniform(-d, d, (4, 2)) * [w, h]
        M = cv2.getPerspectiveTransform(src, (src + jitter).astype(np.float32))
        return [cv2.warpPerspective(f, M, (w, h), borderMode=cv2.BORDER_REFLECT) for f in frames]
    raise ValueError(kind)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/features"))
    ap.add_argument("--fps", type=float, default=config.SAMPLE_FPS)
    ap.add_argument("--aug", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)

    with args.labels.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        dst = args.out / f"{r['video_id']}.npz"
        if dst.exists():
            continue
        t0 = time.time()
        times, frames = video.sample_frames(args.videos / r["file"], args.fps)
        views = {"orig": features.embed_frames(frames)}
        if args.aug:
            for kind in ("flip", "crop", "persp"):
                views[kind] = features.embed_frames(augment(frames, kind, rng))
        np.savez_compressed(dst, times=times, **views)
        print(f"{r['video_id']}: {len(frames)} кадров, {len(views)} вид(а), {time.time() - t0:.1f} с")


if __name__ == "__main__":
    main()
