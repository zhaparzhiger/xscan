"""Агент «Движение» для XScan Bot API: берёт задачу, ищет пики движения в кадре, шлёт их как находки.

Пики движения — кандидаты событий (вход человека, уход кассира, передача ценностей). Это подсказка проверяющему,
а не вердикт: по HANDOFF топ-3 пика попадают в ±3 с от таймкода нарушения в 86% роликов (случайно — 60%).

    python scripts/agent_motion.py --server http://127.0.0.1:8010 --name "Движение"          # создаст агента
    python scripts/agent_motion.py --server http://127.0.0.1:8010 --agent <uuid> --once     # одна задача и выход
Ключ берётся из .env (API_KEY) или --key.
"""
import argparse
import base64
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402  (подхватывает .env)


def call(srv, key, method, path, body=None, raw=False):
    req = urllib.request.Request(srv + path, method=method, headers={"X-API-Key": key, "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=120) as r:
        if raw:
            return r.read()
        return json.loads(r.read() or b"null") if r.status != 204 else None


def motion_peaks(path: Path, fps: float = 4.0, top: int = 5, min_gap: float = 4.0):
    """Энергия разности соседних кадров (серые 160 px) -> top пиков с разносом min_gap сек."""
    cap = cv2.VideoCapture(str(path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / fps)))
    times, energy, frames, prev, i = [], [], {}, None, 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            _, f = cap.retrieve()
            g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(f, (160, 90)), cv2.COLOR_BGR2GRAY), (5, 5), 0)
            if prev is not None:
                t = i / src_fps
                times.append(t)
                energy.append(float(np.mean(cv2.absdiff(g, prev))))
                frames[t] = f
            prev = g
        i += 1
    cap.release()
    if not energy:
        return []
    e = np.convolve(energy, np.ones(3) / 3, mode="same")  # сгладить одиночные всплески
    lo, hi = np.percentile(e, 10), e.max()
    peaks = []
    for j in np.argsort(-e):
        t = times[j]
        if all(abs(t - p[0]) >= min_gap for p in peaks):
            conf = float((e[j] - lo) / (hi - lo + 1e-6))
            peaks.append((t, conf, frames[t]))
        if len(peaks) >= top:
            break
    return sorted(peaks)


def jpeg_b64(frame) -> str:
    h, w = frame.shape[:2]
    frame = cv2.resize(frame, (640, int(640 * h / w)))
    return base64.b64encode(cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1]).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8010")
    ap.add_argument("--key", default=os.getenv("API_KEY", config.API_KEY))
    ap.add_argument("--agent", help="uuid существующего агента")
    ap.add_argument("--name", default="Движение")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=float, default=5.0)
    a = ap.parse_args()

    print("ping:", call(a.server, a.key, "GET", "/bot-api/ping"))
    agent = a.agent or call(a.server, a.key, "POST", "/agents",
                            {"name": a.name, "kind": "other", "description": "пики движения в кадре"})["uuid"]
    print("агент:", agent)
    while True:
        task = call(a.server, a.key, "PUT", "/bot-api/tasks-get", {"agent_uuid": agent})
        if task is None:
            if a.once:
                print("задач нет")
                return
            time.sleep(a.poll)
            continue
        t0 = time.time()
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "video.mov"
            video.write_bytes(call(a.server, a.key, "GET", task["video_url"], raw=True))
            peaks = motion_peaks(video)
        for t, conf, frame in peaks:
            call(a.server, a.key, "POST", f"/bot-api/task-result/{agent}",
                 {"task_uuid": task["task_uuid"], "timecode_sec": round(t, 2), "confidence": round(conf, 3),
                  "label": "пик движения", "note": "резкое изменение в кадре: проверить, что произошло",
                  "frame_base64": jpeg_b64(frame)})
        done = call(a.server, a.key, "POST", f"/bot-api/task-done/{task['task_uuid']}", {"agent_uuid": agent})
        print(f"задача {task['task_uuid'][:8]} (видео {task['job_id']}): {len(peaks)} находок, "
              f"{time.time() - t0:.1f} с; {done}")
        if a.once:
            return


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')}")
