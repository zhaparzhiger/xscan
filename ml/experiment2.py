"""Сравнение наборов признаков: SigLIP2 (весь кадр / тайлы), CLIP, позы.

Метрики по кросс-валидации с разбиением по видео:
- frame-AUC: отличает ли модель момент нарушения (окно tc-1..tc+3) от обычных кадров (честнее video-AUC: нет зависимости от длины ролика);
- video-AUC: max сглаженной вероятности по ролику против метки ролика;
- loc: доля роликов с нарушением, где пик попал в ±3 с от таймкода.

    python -m ml.experiment2
"""
import csv
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.pipeline.events import smooth  # noqa: E402
from ml import pose_features as pf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def win(mat, times, half=1.0):
    out = np.zeros((len(times), mat.shape[1] * 2), np.float32)
    for i, t in enumerate(times):
        seg = mat[(times >= t - half) & (times <= t + half)]
        out[i] = np.concatenate([seg.mean(0), seg.max(0) - seg.min(0)])
    return out


def load():
    data = []
    for r in csv.DictReader((ROOT / "data/labels.csv").open(encoding="utf-8")):
        i = r["video_id"]
        sp, cp, pp = ROOT / f"data/siglip/{i}.npz", ROOT / f"data/features/{i}.npz", ROOT / f"data/pose/{i}.joblib"
        if not (sp.exists() and cp.exists() and pp.exists()):
            continue
        s, c, pose = np.load(sp), np.load(cp), joblib.load(pp)
        n = min(len(s["orig"]), len(c["orig"]), len(pose["times"]))
        times = s["times"][:n]
        sig = s["orig"][:n].astype(np.float32)  # (T,5,D)
        d = {"id": i, "times": times, "tc": float(r["timecode_sec"]) if r["timecode_sec"] else None,
             "sig_full": win(sig[:, 0], times), "sig_tiles": win(sig[:, 1:].mean(1), times),
             "sig_all": win(sig.reshape(n, -1), times),
             "clip": win(c["orig"][:n].astype(np.float32), times),
             "pose": win(pf.video_matrix(pose)[:n], times)}
        data.append(d)
    return data


def target(times, tc, before=1.0, after=3.0, margin=3.0):
    y = np.zeros(len(times), int)
    if tc is not None:
        y[times >= tc - margin] = -1
        y[(times >= tc - before) & (times <= tc + after)] = 1
    return y


def run(data, keys, C=0.02, npc=48):
    idx = np.arange(len(data))
    frame_y, frame_p, vid_s, loc = [], [], np.zeros(len(data)), []
    for tr, va in GroupKFold(n_splits=7).split(idx, groups=idx):
        def X(i):
            return np.hstack([data[i][k] for k in keys])
        Xtr = np.concatenate([X(i)[target(data[i]["times"], data[i]["tc"]) >= 0] for i in tr])
        ytr = np.concatenate([target(data[i]["times"], data[i]["tc"])[target(data[i]["times"], data[i]["tc"]) >= 0] for i in tr])
        clf = make_pipeline(StandardScaler(), PCA(min(npc, Xtr.shape[1]), random_state=0),
                            LogisticRegression(C=C, class_weight="balanced", max_iter=3000)).fit(Xtr, ytr)
        for i in va:
            p = smooth(clf.predict_proba(X(i))[:, 1])
            y = target(data[i]["times"], data[i]["tc"])
            frame_y.append(y[y >= 0])
            frame_p.append(p[y >= 0])
            vid_s[i] = np.sort(p)[-5:].mean()
            if data[i]["tc"] is not None:
                loc.append(abs(data[i]["times"][int(p.argmax())] - data[i]["tc"]) <= 3)
    vy = np.array([d["tc"] is not None for d in data])
    return (roc_auc_score(np.concatenate(frame_y), np.concatenate(frame_p)), roc_auc_score(vy, vid_s), float(np.mean(loc)))


if __name__ == "__main__":
    data = load()
    print("видео:", len(data), flush=True)
    for name, keys in {"pose": ["pose"], "clip": ["clip"], "sig_full": ["sig_full"], "sig_tiles": ["sig_tiles"],
                       "sig_all": ["sig_all"], "sig_full+pose": ["sig_full", "pose"],
                       "sig_all+pose": ["sig_all", "pose"]}.items():
        fa, va, lc = run(data, keys)
        print(f"{name:14s} frame-AUC={fa:.2f}  video-AUC={va:.2f}  loc@3s={lc:.2f}", flush=True)
