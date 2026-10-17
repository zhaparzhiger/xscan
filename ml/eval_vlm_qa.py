"""Что дают ответы Qwen3-VL (data/vlm_qa/*.json): AUC по каждому вопросу и простая модель поверх них.

    python -m ml.eval_vlm_qa
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
Q = ["cashier_present", "safe_open", "cash_on_desk", "extra_person", "person_standing_far"]


def load():
    data = []
    for r in csv.DictReader((ROOT / "data/labels.csv").open(encoding="utf-8")):
        p = ROOT / "data/vlm_qa" / f"{r['video_id']}.json"
        if not p.exists():
            continue
        rows = json.loads(p.read_text(encoding="utf-8"))
        t = np.array([x["t"] for x in rows])
        X = np.array([[x[q] for q in Q] for x in rows])
        data.append({"id": r["video_id"], "t": t, "X": X, "tc": float(r["timecode_sec"]) if r["timecode_sec"] else None})
    return data


def target(t, tc, before=1.5, after=3.0, margin=3.0):
    y = np.zeros(len(t), int)
    if tc is not None:
        y[t >= tc - margin] = -1
        y[(t >= tc - before) & (t <= tc + after)] = 1
    return y


def feats(d, k=2):
    """признаки кадра: ответы + изменения относительно соседних кадров (событие = смена состояния)."""
    X = d["X"]
    n = len(X)
    prev = np.vstack([X[:1]] * k + [X[:-k]]) if n > k else X
    nxt = np.vstack([X[k:]] + [X[-1:]] * k) if n > k else X
    return np.hstack([X, np.abs(X - prev), np.abs(nxt - X), np.minimum(X, np.minimum(prev, nxt)), np.maximum(X, np.maximum(prev, nxt))])


if __name__ == "__main__":
    data = load()
    print("видео:", len(data), "кадров:", sum(len(d["t"]) for d in data))
    Y = np.concatenate([target(d["t"], d["tc"]) for d in data])
    XA = np.vstack([d["X"] for d in data])
    m = Y >= 0
    print("\nAUC по вопросам (кадр нарушения против обычных кадров):")
    for j, q in enumerate(Q):
        a = roc_auc_score(Y[m], XA[m, j])
        print(f"  {q:20s} AUC={a:.2f} (знак {'+' if a >= .5 else '-'})")

    idx = np.arange(len(data))
    fy, fp, vs, loc = [], [], np.zeros(len(data)), []
    for tr, va in GroupKFold(n_splits=7).split(idx, groups=idx):
        Xtr = np.vstack([feats(data[i])[target(data[i]["t"], data[i]["tc"]) >= 0] for i in tr])
        ytr = np.concatenate([target(data[i]["t"], data[i]["tc"])[target(data[i]["t"], data[i]["tc"]) >= 0] for i in tr])
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, class_weight="balanced", max_iter=3000)).fit(Xtr, ytr)
        for i in va:
            p = clf.predict_proba(feats(data[i]))[:, 1]
            y = target(data[i]["t"], data[i]["tc"])
            fy.append(y[y >= 0]); fp.append(p[y >= 0])
            vs[i] = np.sort(p)[-2:].mean()
            if data[i]["tc"] is not None:
                loc.append(abs(data[i]["t"][int(p.argmax())] - data[i]["tc"]) <= 3)
    vy = np.array([d["tc"] is not None for d in data])
    print(f"\nLR поверх ответов: frame-AUC={roc_auc_score(np.concatenate(fy), np.concatenate(fp)):.2f}  "
          f"video-AUC={roc_auc_score(vy, vs):.2f}  loc@3s={np.mean(loc):.2f}")
    # порог под recall=1
    thr = np.sort(vs[vy])[0]
    print(f"порог для recall=1.0 по видео: {thr:.2f}; ложных срабатываний при нём: {(vs[~vy] >= thr).sum()} из {(~vy).sum()}")
