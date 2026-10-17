"""Стадия 1: вероятность "здесь нарушение" для каждого момента видео.

- Есть models/detector.joblib (ml/train.py) -> обученный классификатор поверх CLIP-признаков окна.
- Нет модели -> zero-shot CLIP по фразам из violations.yaml (слабый baseline, только для отладки).
"""
import logging
from functools import lru_cache

import joblib
import numpy as np

from app import config
from app.pipeline import features
from app.rules import registry

log = logging.getLogger(__name__)

DETECTOR_PATH = config.MODELS_DIR / "detector.joblib"
TYPES_PATH = config.MODELS_DIR / "types.joblib"

NORMAL_PROMPTS = [
    "a cashier sitting at the desk working on a laptop",
    "a cashier serving a client across the desk",
    "an office cash room with a cashier at work",
]


@lru_cache(maxsize=1)
def _detector() -> dict | None:
    if DETECTOR_PATH.exists():
        log.info("loading %s", DETECTOR_PATH)
        return joblib.load(DETECTOR_PATH)
    return None


@lru_cache(maxsize=1)
def _type_model() -> dict | None:
    return joblib.load(TYPES_PATH) if TYPES_PATH.exists() else None


def model_status() -> dict:
    det = _detector()
    return {
        "ml_deps": features.available(),
        "detector": "trained" if det else "zero-shot fallback",
        "type_classifier": "trained" if _type_model() else "zero-shot fallback",
        "threshold": threshold(),
    }


def threshold() -> float:
    if config.DETECTOR_THRESHOLD:
        return float(config.DETECTOR_THRESHOLD)
    det = _detector()
    return float(det["threshold"]) if det else 0.6


def half_window() -> float:
    det = _detector()
    return float(det.get("half_window_sec", 1.0)) if det else 1.0


def score(emb: np.ndarray, times: np.ndarray) -> np.ndarray:
    det = _detector()
    if det is not None:
        feats = features.window_features(emb, times, det.get("half_window_sec", 1.0))
        return det["clf"].predict_proba(feats)[:, 1]
    return _zero_shot_score(emb)


def _zero_shot_score(emb: np.ndarray) -> np.ndarray:
    prompts = [p for t in registry.type_ids() for p in registry.violation(t).get("clip_prompts", [])]
    text = features.embed_texts(NORMAL_PROMPTS + prompts)
    logits = 100.0 * emb @ text.T
    probs = np.exp(logits - logits.max(1, keepdims=True))
    probs /= probs.sum(1, keepdims=True)
    return probs[:, len(NORMAL_PROMPTS):].sum(1)


def classify(window_emb: np.ndarray, window_feat: np.ndarray) -> tuple[str, float]:
    """Стадия 2: тип нарушения для найденного события."""
    tm = _type_model()
    if tm is not None:
        proba = tm["clf"].predict_proba(window_feat[None])[0]
        i = int(proba.argmax())
        # Неуверенно -> универсальный тип (в тесте бывают незнакомые нарушения)
        if proba[i] < tm.get("min_confidence", 0.4):
            return registry.GENERIC, float(proba[i])
        return str(tm["clf"].classes_[i]), float(proba[i])

    ids, prompts = [], []
    for t in registry.type_ids():
        for p in registry.violation(t).get("clip_prompts", []):
            ids.append(t)
            prompts.append(p)
    if not prompts:
        return registry.GENERIC, 0.0
    sims = window_emb.mean(0) @ features.embed_texts(prompts).T
    i = int(sims.argmax())
    return ids[i], float(sims[i])
