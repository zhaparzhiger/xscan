"""Чтение видео: выборка кадров с заданной частотой и извлечение кадров-доказательств."""
import base64
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class VideoInfo:
    fps: float
    frame_count: int
    duration_sec: float
    width: int
    height: int


def probe(path: Path) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("не удалось открыть видео")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return VideoInfo(fps=fps, frame_count=n, duration_sec=n / fps if fps else 0.0, width=w, height=h)


def sample_frames(path: Path, sample_fps: float, max_side: int | None = 512) -> tuple[np.ndarray, list[np.ndarray]]:
    """Возвращает (таймкоды в секундах, кадры BGR). Читаем последовательно — seek в .mov бывает неточным."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("не удалось открыть видео")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps / sample_fps))
    times, frames = [], []
    idx = 0
    while True:
        if idx % step == 0:
            ok, frame = cap.read()
            if not ok:
                break
            if max_side:
                frame = _resize(frame, max_side)
            times.append(idx / fps)
            frames.append(frame)
        else:
            if not cap.grab():
                break
        idx += 1
    cap.release()
    return np.asarray(times, dtype=np.float32), frames


def frames_at(path: Path, timestamps: list[float]) -> dict[float, np.ndarray]:
    """Кадры в полном разрешении для указанных моментов (для доказательств)."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    out = {}
    for t in timestamps:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(t * fps))))
        ok, frame = cap.read()
        if ok:
            out[t] = frame
    cap.release()
    return out


def annotate(frame: np.ndarray, text: str, boxes: list[tuple[int, int, int, int]] | None = None) -> np.ndarray:
    img = frame.copy()
    for x1, y1, x2, y2 in boxes or []:
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
    cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(img, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def to_jpeg_b64(frame: np.ndarray, quality: int = 85) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _resize(frame: np.ndarray, max_side: int) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return frame
    return cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def fmt_tc(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"
