"""SigLIP 2 эмбеддинги кадров: целиком + сетка 2x2 (мелкие действия руками теряются в глобальном эмбеддинге).

Для каждого вида (orig/flip/crop/persp) сохраняется массив (T, 5, D): [весь кадр, 4 тайла] -> data/siglip/<id>.npz

    python ml/extract_siglip.py --videos ~/Downloads/open/videos --aug
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.pipeline import video  # noqa: E402
from ml.extract_features import augment  # noqa: E402

MODEL_DIR = config.MODELS_DIR / "siglip2"


def load(device: str):
    from transformers import AutoImageProcessor, AutoModel

    model = AutoModel.from_pretrained(MODEL_DIR, torch_dtype=torch.float16).to(device).eval()
    proc = AutoImageProcessor.from_pretrained(MODEL_DIR)
    return model, proc


def views_of(frame: np.ndarray) -> list[np.ndarray]:
    h, w = frame.shape[:2]
    tiles = [frame[:h // 2, :w // 2], frame[:h // 2, w // 2:], frame[h // 2:, :w // 2], frame[h // 2:, w // 2:]]
    return [frame] + tiles


@torch.inference_mode()
def embed(model, proc, frames: list[np.ndarray], device: str, batch: int = 64) -> np.ndarray:
    imgs = [cv2.cvtColor(v, cv2.COLOR_BGR2RGB) for f in frames for v in views_of(f)]
    out = []
    for i in range(0, len(imgs), batch):
        px = proc(images=imgs[i:i + batch], return_tensors="pt")["pixel_values"].to(device, torch.float16)
        e = model.get_image_features(pixel_values=px)
        e = e.pooler_output if hasattr(e, "pooler_output") else e
        out.append(torch.nn.functional.normalize(e.float(), dim=-1).cpu().numpy())
    return np.concatenate(out).reshape(len(frames), 5, -1).astype(np.float16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/siglip"))
    ap.add_argument("--fps", type=float, default=config.SAMPLE_FPS)
    ap.add_argument("--aug", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, proc = load(device)
    rng = np.random.default_rng(0)
    for r in csv.DictReader(args.labels.open(encoding="utf-8")):
        dst = args.out / f"{r['video_id']}.npz"
        if dst.exists():
            continue
        t0 = time.time()
        times, frames = video.sample_frames(args.videos / r["file"], args.fps, max_side=512)
        views = {"orig": embed(model, proc, frames, device)}
        if args.aug:
            for kind in ("flip", "crop", "persp"):
                views[kind] = embed(model, proc, augment(frames, kind, rng), device)
        np.savez_compressed(dst, times=times, **views)
        print(f"{r['video_id']}: {len(frames)} кадров, {time.time() - t0:.1f} с", flush=True)


if __name__ == "__main__":
    main()
