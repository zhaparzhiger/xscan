"""Признаки кадров: эмбеддинги CLIP (open_clip, MIT). Модель грузится один раз и работает на CPU.

Веса скачиваются при первом запуске (scripts/download_models.py), дальше интернет не нужен.
"""
import logging
import threading

import cv2
import numpy as np

from app import config

log = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None
_device = "cpu"


def available() -> bool:
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _load():
    global _model, _device
    with _lock:
        if _model is None:
            import open_clip
            import torch

            # CUDA, если есть NVIDIA (ноут для обучения); иначе CPU — результат тот же, только медленнее
            _device = "cuda" if torch.cuda.is_available() else "cpu"
            model, _, preprocess = open_clip.create_model_and_transforms(
                config.CLIP_MODEL, pretrained=config.CLIP_PRETRAINED, cache_dir=str(config.MODELS_DIR / "clip")
            )
            model.eval().to(_device)
            tokenizer = open_clip.get_tokenizer(config.CLIP_MODEL)
            _model = (model, preprocess, tokenizer)
            log.info("CLIP %s/%s loaded on %s", config.CLIP_MODEL, config.CLIP_PRETRAINED, _device)
    return _model


def embed_frames(frames: list[np.ndarray], batch_size: int = 32) -> np.ndarray:
    """BGR-кадры -> L2-нормированные эмбеддинги [N, D]."""
    import torch
    from PIL import Image

    model, preprocess, _ = _load()
    out = []
    with torch.inference_mode():
        for i in range(0, len(frames), batch_size):
            batch = torch.stack(
                [preprocess(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))) for f in frames[i:i + batch_size]]
            )
            emb = model.encode_image(batch.to(_device))
            out.append(torch.nn.functional.normalize(emb, dim=-1).float().cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, 512), dtype=np.float32)


def embed_texts(texts: list[str]) -> np.ndarray:
    import torch

    model, _, tokenizer = _load()
    with torch.inference_mode():
        emb = model.encode_text(tokenizer(texts).to(_device))
        return torch.nn.functional.normalize(emb, dim=-1).float().cpu().numpy()


def window_features(emb: np.ndarray, times: np.ndarray, half_window_sec: float = 1.0) -> np.ndarray:
    """Признак момента t = [эмбеддинг t, среднее по окну ±w, разница с началом окна (движение)].

    Должна совпадать в train (ml/train.py) и в inference.
    """
    n = len(emb)
    feats = np.zeros((n, emb.shape[1] * 3), dtype=np.float32)
    for i, t in enumerate(times):
        lo = np.searchsorted(times, t - half_window_sec)
        hi = np.searchsorted(times, t + half_window_sec, side="right")
        win = emb[lo:hi]
        feats[i] = np.concatenate([emb[i], win.mean(0), emb[i] - emb[lo]])
    return feats
