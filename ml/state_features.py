"""Состояния объектов во времени по рамкам из data/boxes.json -> data/state/<id>.npz.

Признаки на кадр (4 fps):
  экран ноутбука: яркость, доля белых пикселей, доля синих (экран блокировки), контраст
  сейф:   отличие от базового вида, доля тёмных пикселей (открытая дверца/нутро)
  стол:   отличие от базового вида, доля светлых малонасыщенных пикселей (бумага, купюры)
  люди:   есть ли человек у стола, сколько человек в комнате (по позам, без отражений)

    python -m ml.state_features
"""
import json
import sys
from pathlib import Path

import cv2
import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.labels2 import ROOT, VIDEOS, unique_videos  # noqa: E402

FEATS = ["scr_gray", "scr_white", "scr_blue", "scr_std", "safe_diff", "safe_dark", "desk_diff", "desk_paper",
         "p_desk", "p_room", "p_move"]


def crop(img, box, pad=0.0):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = (x2 - x1) * pad, (y2 - y1) * pad
    xa, ya = max(0, int((x1 - bw) / 1000 * w)), max(0, int((y1 - bh) / 1000 * h))
    xb, yb = min(w, int((x2 + bw) / 1000 * w)), min(h, int((y2 + bh) / 1000 * h))
    return img[ya:yb, xa:xb]


def person_feats(det, h, w, desk):
    """p_desk: человек пересекает зону стола; p_room: уверенные люди с видимым телом (без отражений)."""
    dx1, dy1, dx2, dy2 = desk[0] / 1000 * w, desk[1] / 1000 * h, desk[2] / 1000 * w, desk[3] / 1000 * h
    dy1 -= (dy2 - dy1) * 0.8  # зона над столом, где сидит/стоит кассир
    pd = pr = 0
    for b, s, k in zip(det["boxes"], det["scores"], det["kps"]):
        if s < 0.9 or (b[3] - b[1]) / h < 0.12:
            continue
        pr += 1
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if dx1 - 20 <= cx <= dx2 + 20 and dy1 <= cy <= dy2:
            pd += 1
    return float(pd > 0), float(pr)


def main():
    boxes = json.loads((ROOT / "data/boxes.json").read_text(encoding="utf-8"))
    out = ROOT / "data/state"
    out.mkdir(parents=True, exist_ok=True)
    for v in unique_videos():
        dst = out / f"{v['id']}.npz"
        if dst.exists():
            continue
        b = boxes[v["id"]]
        pose = joblib.load(ROOT / f"data/pose/{v['id']}.joblib")
        cap = cv2.VideoCapture(str(VIDEOS / v["file"]))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps / 4))
        rows, times, safe_base, desk_base, i = [], [], [], [], 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if i % step == 0:
                ok, f = cap.retrieve()
                h, w = f.shape[:2]
                scr = crop(f, b["laptop_screen"], 0.05) if b["laptop_screen"] else None
                sf = crop(f, b["safe"], 0.0)
                dk = crop(f, b["desk"], 0.0)
                r = []
                if scr is not None and scr.size:
                    g = cv2.cvtColor(scr, cv2.COLOR_BGR2GRAY).astype(np.float32)
                    hsv = cv2.cvtColor(scr, cv2.COLOR_BGR2HSV)
                    r += [g.mean() / 255, float((g > 200).mean()), float(((hsv[..., 0] > 95) & (hsv[..., 0] < 130) & (hsv[..., 1] > 60)).mean()), g.std() / 255]
                else:
                    r += [0, 0, 0, 0]
                sg = cv2.resize(cv2.cvtColor(sf, cv2.COLOR_BGR2GRAY), (48, 64)).astype(np.float32)
                dg = cv2.resize(cv2.cvtColor(dk, cv2.COLOR_BGR2GRAY), (96, 48)).astype(np.float32)
                safe_base.append(sg); desk_base.append(dg)
                hsvd = cv2.cvtColor(dk, cv2.COLOR_BGR2HSV)
                r += [0, float((sg < 60).mean())]  # safe_diff заполним ниже
                r += [0, float(((hsvd[..., 2] > 190) & (hsvd[..., 1] < 50)).mean())]
                t = i / fps
                j = int(np.argmin(np.abs(pose["times"] - t)))
                pdsk, prm = person_feats(pose["dets"][j], *pose["hw"], b["desk"])
                r += [pdsk, prm, float(pose["motion"][j]) / 50]
                rows.append(r); times.append(t)
            i += 1
        cap.release()
        X = np.array(rows, np.float32)
        base_n = max(3, min(8, len(X) // 4))
        sb, db = np.median(safe_base[:base_n], 0), np.median(desk_base[:base_n], 0)
        X[:, FEATS.index("safe_diff")] = [np.abs(s - sb).mean() / 255 for s in safe_base]
        X[:, FEATS.index("desk_diff")] = [np.abs(d - db).mean() / 255 for d in desk_base]
        np.savez_compressed(dst, times=np.array(times, np.float32), X=X)
        print(v["id"], X.shape, flush=True)


if __name__ == "__main__":
    main()
