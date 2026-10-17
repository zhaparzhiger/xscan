"""Обучение детектора (стадия 1) и классификатора типов (стадия 2) поверх кэшированных CLIP-признаков.

Разметка кадров для детектора (по таймкоду tc из labels.csv):
  положительные: tc - pos_before ... tc + pos_after
  игнор:         всё остальное после tc - neg_margin в роликах с нарушением (состояние нарушения может длиться)
  отрицательные: кадры до tc - neg_margin + все кадры роликов без нарушений

Валидация — GroupKFold по видео (ролик целиком либо в train, либо в val), порог подбирается
по требованию заказчика: пропуск недопустим -> максимальный recall, затем минимум ложных срабатываний.

    python ml/train.py
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.pipeline.events import find_events  # noqa: E402
from app.pipeline.features import window_features  # noqa: E402


def load(labels: Path, feat_dir: Path):
    with labels.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (feat_dir / f"{r['video_id']}.npz").exists()]
    data = []
    for r in rows:
        z = np.load(feat_dir / f"{r['video_id']}.npz")
        views = {k: z[k] for k in z.files if k != "times"}
        tc = float(r["timecode_sec"]) if r["timecode_sec"] else None
        data.append({**r, "times": z["times"], "views": views, "tc": tc})
    return data


def frame_targets(times, tc, a):
    """1 = нарушение, 0 = норма, -1 = игнор."""
    y = np.zeros(len(times), dtype=int)
    if tc is None:
        return y
    y[times >= tc - a.neg_margin] = -1
    y[(times >= tc - a.pos_before) & (times <= tc + a.pos_after)] = 1
    return y


def build(data, a, use_aug=True):
    X, Y = [], []
    for d in data:
        y = frame_targets(d["times"], d["tc"], a)
        for name, emb in d["views"].items():
            if name != "orig" and not use_aug:
                continue
            f = window_features(emb, d["times"], a.half_window)
            X.append(f[y >= 0])
            Y.append(y[y >= 0])
    return np.concatenate(X), np.concatenate(Y)


def make_clf(C):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, class_weight="balanced", max_iter=2000))


def evaluate(data, probs, thr, tol):
    tp = fn = fp = tn = 0
    loc_hits, errs = 0, []
    for d, p in zip(data, probs):
        ev = find_events(d["times"], p, thr)
        if d["tc"] is not None:
            if ev:
                tp += 1
                best = min(ev, key=lambda e: abs(e.peak_time - d["tc"]))
                errs.append(best.peak_time - d["tc"])
                loc_hits += abs(best.peak_time - d["tc"]) <= tol
            else:
                fn += 1
        else:
            fp += bool(ev)
            tn += not ev
    return {"thr": thr, "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "recall": tp / max(tp + fn, 1), "fpr": fp / max(fp + tn, 1),
            "acc": (tp + tn) / max(len(data), 1), "loc_hits": loc_hits,
            "mae": float(np.mean(np.abs(errs))) if errs else None,
            "bias": float(np.mean(errs)) if errs else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    ap.add_argument("--features", type=Path, default=Path("data/features"))
    ap.add_argument("--videos", type=Path, default=Path(os.environ.get("XSCAN_VIDEOS", Path.home() / "Downloads/open/videos")))
    ap.add_argument("--half-window", type=float, default=1.0)
    ap.add_argument("--pos-before", type=float, default=1.0)
    ap.add_argument("--pos-after", type=float, default=3.0)
    ap.add_argument("--neg-margin", type=float, default=3.0)
    ap.add_argument("--C", type=float, default=0.05)
    ap.add_argument("--folds", type=int, default=7)
    ap.add_argument("--target-recall", type=float, default=1.0)
    ap.add_argument("--tol", type=float, default=3.0, help="допуск по таймкоду для отчёта, сек")
    a = ap.parse_args()

    data = load(a.labels, a.features)
    if not data:
        sys.exit("нет признаков: сначала ml/extract_features.py")
    print(f"видео: {len(data)}, с нарушением: {sum(d['tc'] is not None for d in data)}")

    # ---- кросс-валидация по видео ----
    # дубликаты (X-4 == X-47, X-5 == X-48) — одна группа, иначе утечка между фолдами;
    # одинаковый размер файла == один и тот же ролик (как в ml/labels2.py)
    keys = {}
    groups = np.array([keys.setdefault((a.videos / d["file"]).stat().st_size, len(keys)) for d in data])
    print(f"уникальных видео: {len(keys)}")
    oof = [None] * len(data)
    for tr, va in GroupKFold(n_splits=min(a.folds, len(keys))).split(groups, groups=groups):
        X, Y = build([data[i] for i in tr], a)
        clf = make_clf(a.C).fit(X, Y)
        for i in va:
            f = window_features(data[i]["views"]["orig"], data[i]["times"], a.half_window)
            oof[i] = clf.predict_proba(f)[:, 1]

    grid = [evaluate(data, oof, t, a.tol) for t in np.round(np.arange(0.30, 0.99, 0.02), 2)]
    print("\n thr  recall  fpr   acc   loc@±%.0fs  mae   bias" % a.tol)
    for r in grid:
        print(f"{r['thr']:.2f}  {r['recall']:.2f}   {r['fpr']:.2f}  {r['acc']:.2f}  {r['loc_hits']:>3}       "
              f"{r['mae'] if r['mae'] is not None else float('nan'):.2f}  "
              f"{r['bias'] if r['bias'] is not None else float('nan'):+.2f}")
    ok = [r for r in grid if r["recall"] >= a.target_recall]
    best = max(ok, key=lambda r: (-r["fp"], r["thr"])) if ok else max(grid, key=lambda r: r["recall"] - 0.5 * r["fpr"])
    print(f"\nвыбран порог {best['thr']}: recall={best['recall']:.2f} fpr={best['fpr']:.2f} acc={best['acc']:.2f}")

    # ---- финальная модель на всех данных ----
    X, Y = build(data, a)
    det = {"clf": make_clf(a.C).fit(X, Y), "threshold": best["thr"], "half_window_sec": a.half_window,
           "clip": f"{config.CLIP_MODEL}/{config.CLIP_PRETRAINED}", "cv": best}
    joblib.dump(det, config.MODELS_DIR / "detector.joblib")
    print("-> models/detector.joblib")

    # ---- классификатор типов (если в labels.csv проставлены type) ----
    typed = [d for d in data if d["tc"] is not None and d.get("type")]
    if len({d["type"] for d in typed}) >= 2:
        Xt, Yt = [], []
        for d in typed:
            for emb in d["views"].values():
                f = window_features(emb, d["times"], a.half_window)
                m = (d["times"] >= d["tc"] - a.pos_before) & (d["times"] <= d["tc"] + a.pos_after)
                Xt.append(f[m])
                Yt += [d["type"]] * int(m.sum())
        tclf = make_clf(1.0).fit(np.concatenate(Xt), Yt)
        joblib.dump({"clf": tclf, "min_confidence": 0.4}, config.MODELS_DIR / "types.joblib")
        print(f"-> models/types.joblib, типы: {sorted(set(Yt))}")
    else:
        print("типы не размечены (колонка type в labels.csv) — используется zero-shot по violations.yaml")


if __name__ == "__main__":
    main()
