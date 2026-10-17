"""Люди и позы по всем видео: KeypointRCNN (torchvision, BSD) на GPU -> data/pose/<id>.joblib.

Для каждого кадра (SAMPLE_FPS): рамки людей, 17 ключевых точек COCO, яркость и энергия движения.
На этом строятся структурные признаки (ml/pose_features.py), не зависящие от «вида» сцены целиком.

    python ml/extract_pose.py --videos ~/Downloads/open/videos
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import cv2
import joblib
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.pipeline import video  # noqa: E402

SCORE_MIN = 0.6


def load_model(device: str):
    from torchvision.models.detection import KeypointRCNN_ResNet50_FPN_Weights, keypointrcnn_resnet50_fpn

    m = keypointrcnn_resnet50_fpn(weights=KeypointRCNN_ResNet50_FPN_Weights.DEFAULT, min_size=640, max_size=1100)
    return m.eval().to(device)


@torch.inference_mode()
def detect(model, frames: list[np.ndarray], device: str, batch: int = 6) -> list[dict]:
    out = []
    for i in range(0, len(frames), batch):
        chunk = frames[i:i + batch]
        x = [torch.from_numpy(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255).to(device) for f in chunk]
        for r in model(x):
            keep = r["scores"] >= SCORE_MIN
            out.append({
                "boxes": r["boxes"][keep].cpu().numpy().astype(np.float32),
                "scores": r["scores"][keep].cpu().numpy().astype(np.float32),
                "kps": r["keypoints"][keep].cpu().numpy().astype(np.float32),
            })
    return out


def low_level(frames: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    gray = [cv2.cvtColor(cv2.resize(f, (96, 160)), cv2.COLOR_BGR2GRAY).astype(np.float32) for f in frames]
    bright = np.array([g.mean() for g in gray], dtype=np.float32)
    motion = np.zeros(len(gray), dtype=np.float32)
    for i in range(1, len(gray)):
        motion[i] = np.abs(gray[i] - gray[i - 1]).mean()
    return bright, motion


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/pose"))
    ap.add_argument("--fps", type=float, default=config.SAMPLE_FPS)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_model(device)
    rows = list(csv.DictReader(args.labels.open(encoding="utf-8")))
    for r in rows:
        dst = args.out / f"{r['video_id']}.joblib"
        if dst.exists():
            continue
        t0 = time.time()
        times, frames = video.sample_frames(args.videos / r["file"], args.fps, max_side=640)
        dets = detect(model, frames, device)
        bright, motion = low_level(frames)
        joblib.dump({"times": times, "dets": dets, "bright": bright, "motion": motion,
                     "hw": frames[0].shape[:2]}, dst)
        print(f"{r['video_id']}: {len(frames)} кадров, {time.time() - t0:.1f} с", flush=True)


if __name__ == "__main__":
    main()
