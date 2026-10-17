"""Быстрые эксперименты: какие признаки вообще разделяют нарушение и норму.

Метрика уровня видео: AUC по max-вероятности ролика; плюс точность таймкода.
    python ml/experiment.py
"""
import csv
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.pipeline.features import window_features as clip_window  # noqa: E402
from ml import pose_features as pf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load():
    rows = list(csv.DictReader((ROOT / "data/labels.csv").open(encoding="utf-8")))
    data = []
    for r in rows:
        pp, fp = ROOT / "data/pose" / f"{r['video_id']}.joblib", ROOT / "data/features" / f"{r['video_id']}.npz"
        if not pp.exists():
            continue
        pose = joblib.load(pp)
        d = {**r, "tc": float(r["timecode_sec"]) if r["timecode_sec"] else None, "times": pose["times"],
             "pose": pf.window_features(pf.video_matrix(pose), pose["times"], 1.0)}
        if fp.exists():
            z = np.load(fp)
            n = min(len(z["orig"]), len(d["times"]))
            d["clip"] = clip_window(z["orig"][:n], z["times"][:n], 1.0)
            d["times"] = d["times"][:n]
            d["pose"] = d["pose"][:n]
        data.append(d)
    return data


def targets(times, tc, before=1.0, after=3.0, margin=3.0):
    y = np.zeros(len(times), int)
    if tc is None:
        return y
    y[times >= tc - margin] = -1
    y[(times >= tc - before) & (times <= tc + after)] = 1
    return y


def make(kind):
    if kind == "lr":
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000))
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, class_weight="balanced")


def run(data, feat_key, kind):
    idx = np.arange(len(data))
    score = np.zeros(len(data))
    err = []
    for tr, va in GroupKFold(n_splits=7).split(idx, groups=idx):
        X = np.concatenate([np.hstack([data[i][k] for k in feat_key])[targets(data[i]["times"], data[i]["tc"]) >= 0] for i in tr])
        Y = np.concatenate([targets(data[i]["times"], data[i]["tc"])[targets(data[i]["times"], data[i]["tc"]) >= 0] for i in tr])
        clf = make(kind).fit(X, Y)
        for i in va:
            p = clf.predict_proba(np.hstack([data[i][k] for k in feat_key]))[:, 1]
            score[i] = p.max()
            if data[i]["tc"] is not None:
                err.append(abs(data[i]["times"][int(p.argmax())] - data[i]["tc"]))
    y = np.array([d["tc"] is not None for d in data])
    return roc_auc_score(y, score), (np.mean(np.array(err) <= 3) if err else 0.0), float(np.median(err)) if err else 0.0


if __name__ == "__main__":
    data = load()
    print("видео:", len(data), "с clip:", sum("clip" in d for d in data))
    sets = {"pose": ["pose"]}
    if all("clip" in d for d in data):
        sets.update({"clip": ["clip"], "pose+clip": ["pose", "clip"]})
    for name, keys in sets.items():
        for kind in ("lr", "gb"):
            auc, loc, med = run(data, keys, kind)
            print(f"{name:10s} {kind}: video-AUC={auc:.2f}  loc@3s={loc:.2f}  медиана ошибки={med:.1f}с")
