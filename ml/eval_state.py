"""Что дают признаки состояния объектов (data/state): AUC по признакам и модель с кросс-валидацией по видео.

    python -m ml.eval_state
"""
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.labels2 import ROOT, target, unique_videos  # noqa: E402
from ml.state_features import FEATS  # noqa: E402

NAMES = FEATS + ["scr_on_away", "safe_on_away", "paper_on_away", "alone_far", "n_changes"]


def load():
    data = []
    for v in unique_videos():
        z = np.load(ROOT / f"data/state/{v['id']}.npz")
        X, t = z["X"], z["times"]
        away = 1 - X[:, FEATS.index("p_desk")]
        ex = np.stack([X[:, FEATS.index("scr_white")] * away, X[:, FEATS.index("safe_diff")] * away,
                       X[:, FEATS.index("desk_paper")] * away, away * (X[:, FEATS.index("p_room")] <= 1),
                       np.r_[0, np.abs(np.diff(X[:, FEATS.index("p_room")]))]], 1)
        data.append({**v, "t": t, "X": np.hstack([X, ex]).astype(np.float32)})
    return data


def smooth(X, k=3):
    pad = np.pad(X, ((k // 2, k // 2), (0, 0)), mode="edge")
    return np.stack([pad[i:i + len(X)].mean(0) for i in range(len(X))])


def feats(d, half=2):
    """признаки кадра: сглаженное значение, максимум, изменение к соседям."""
    X = smooth(d["X"])
    n = len(X)
    out = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        seg = X[lo:hi]
        out.append(np.concatenate([X[i], seg.max(0), seg.min(0), X[min(n - 1, i + half)] - X[max(0, i - half)]]))
    return np.array(out, np.float32)


if __name__ == "__main__":
    data = load()
    print("видео:", len(data), "с нарушением:", sum(bool(d["tcs"]) for d in data), "кадров:", sum(len(d["t"]) for d in data))
    Y = np.concatenate([target(d["t"], d["tcs"]) for d in data])
    XA = np.vstack([d["X"] for d in data])
    m = Y >= 0
    print(f"положительных кадров: {int((Y == 1).sum())}, обычных: {int((Y == 0).sum())}\n\nAUC по признакам (кадр нарушения против обычных):")
    for j, nme in enumerate(NAMES):
        a = roc_auc_score(Y[m], XA[m, j])
        if abs(a - .5) >= .06:
            print(f"  {nme:14s} AUC={a:.2f}")

    idx = np.arange(len(data))
    for name, mk in [("LR", lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.05, class_weight="balanced", max_iter=4000))),
                     ("GB", lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=120, class_weight="balanced"))]:
        fy, fp, vs, loc = [], [], np.zeros(len(data)), []
        for tr, va in GroupKFold(n_splits=8).split(idx, groups=idx):
            Xtr = np.vstack([feats(data[i])[target(data[i]["t"], data[i]["tcs"]) >= 0] for i in tr])
            ytr = np.concatenate([target(data[i]["t"], data[i]["tcs"])[target(data[i]["t"], data[i]["tcs"]) >= 0] for i in tr])
            clf = mk().fit(Xtr, ytr)
            for i in va:
                p = clf.predict_proba(feats(data[i]))[:, 1]
                y = target(data[i]["t"], data[i]["tcs"])
                fy.append(y[y >= 0]); fp.append(p[y >= 0])
                vs[i] = np.sort(p)[-3:].mean()
                if data[i]["tcs"]:
                    loc.append(any(abs(data[i]["t"][int(p.argmax())] - tc) <= 3 for tc in data[i]["tcs"]))
        vy = np.array([bool(d["tcs"]) for d in data])
        print(f"\n{name}: frame-AUC={roc_auc_score(np.concatenate(fy), np.concatenate(fp)):.2f}  video-AUC={roc_auc_score(vy, vs):.2f}  loc@3s={np.mean(loc):.2f}")
