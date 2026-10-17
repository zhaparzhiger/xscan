"""Оркестратор: видео -> кадры -> CLIP -> вероятность нарушения -> события -> тип -> доказательства."""
import logging
import time
from pathlib import Path

from app import config
from app.pipeline import detector, features, video
from app.pipeline.events import find_events
from app.rules import registry

log = logging.getLogger(__name__)


def analyze_video(path: Path) -> dict:
    if config.ANALYZER == "gemini":
        return _analyze_gemini(path)
    t0 = time.time()
    info = video.probe(path)
    # Длинное видео -> реже выборка, чтобы уложиться в бюджет 5 минут
    fps = config.SAMPLE_FPS if info.duration_sec <= 180 else max(1.0, config.SAMPLE_FPS * 180 / info.duration_sec)
    times, frames = video.sample_frames(path, fps)
    if len(frames) == 0:
        raise ValueError("в видео нет кадров")
    log.info("%s: %.1fs, %d frames sampled in %.1fs", path.name, info.duration_sec, len(frames), time.time() - t0)

    if not features.available():
        raise RuntimeError("ML-зависимости не установлены: pip install -r requirements-ml.txt")
    emb = features.embed_frames(frames)
    scores = detector.score(emb, times)
    feats = features.window_features(emb, times, detector.half_window())
    events = find_events(times, scores, detector.threshold())
    log.info("%s: scored in %.1fs, max=%.2f, events=%d", path.name, time.time() - t0, scores.max(), len(events))

    violations = []
    for ev in events:
        type_id, type_conf = detector.classify(emb[ev.lo_idx:ev.hi_idx + 1], feats[ev.peak_idx])
        rule = registry.violation(type_id)
        tc = video.fmt_tc(ev.peak_time)
        violations.append({
            "type": rule["title"],
            "timecode_sec": round(ev.peak_time, 2),
            "description": registry.describe(type_id, tc),
            "evidence_frames": _evidence(path, ev, info.duration_sec),
            # --- поля только для UI (в API не уходят) ---
            "type_id": type_id,
            "confidence": round(ev.score, 3),
            "type_confidence": round(type_conf, 3),
            "interval_sec": [round(ev.start, 2), round(ev.end, 2)],
            "rule": registry.rule_reference(type_id),
        })

    return {
        "verdict": "violation" if violations else "no_violation",
        "violations": violations,
        "duration_sec": round(info.duration_sec, 2),
        "processing_sec": round(time.time() - t0, 1),
        "score_timeline": [[round(float(t), 2), round(float(s), 3)] for t, s in zip(times, scores)],
    }


def _analyze_gemini(path: Path) -> dict:
    from app.pipeline import gemini

    t0 = time.time()
    info = video.probe(path)
    ans = gemini.ask(path, info.duration_sec)
    found = gemini.violations(ans, info.duration_sec)
    log.info("%s: gemini %s за %.1fs, %d КБ, нарушений %d", path.name, ans["_model"], ans["_sec"],
             ans["_bytes"] // 1024, len(found))

    violations = []
    for v in found:
        tc = video.fmt_tc(v["timecode_sec"])
        ref = registry.rule_reference(v["type_id"])
        basis = ref["document"] + (f", {ref['clause']}" if ref["clause"] else "")
        violations.append({
            "type": registry.violation(v["type_id"])["title"],
            "timecode_sec": v["timecode_sec"],
            "description": f"{tc}: {v['what_is_seen']} Основание: {basis}. Требуется проверка человеком.",
            "evidence_frames": _evidence_at(path, v["timecode_sec"], info.duration_sec),
            # --- поля только для UI ---
            "type_id": v["type_id"],
            "confidence": v["confidence"],
            "rule": ref,
        })
    return {
        "verdict": "violation" if violations else "no_violation",
        "violations": violations,
        "duration_sec": round(info.duration_sec, 2),
        "processing_sec": round(time.time() - t0, 1),
        "analyzer": f"gemini/{ans['_model']}",
        "scene_summary": ans.get("scene_summary", ""),
    }


def _evidence_at(path: Path, tc: float, duration: float) -> list[dict]:
    """Кадр в момент нарушения и через 2 с (видно, что состояние сохраняется)."""
    ts = sorted({round(min(max(t, 0.0), max(duration - 0.05, 0.0)), 2) for t in (tc, tc + 2.0)})
    shots = video.frames_at(path, ts)
    return [{"timestamp_sec": t, "image_base64": video.to_jpeg_b64(video.annotate(f, video.fmt_tc(t)))}
            for t, f in shots.items()]


def _evidence(path: Path, ev, duration: float) -> list[dict]:
    """1–3 кадра: пик события и, если участок длинный, его начало и конец."""
    ts = [ev.peak_time]
    if ev.end - ev.start >= 1.0:
        ts = [ev.start, ev.peak_time, ev.end]
    ts = sorted({round(min(max(t, 0.0), max(duration - 0.05, 0.0)), 2) for t in ts})
    shots = video.frames_at(path, ts)
    return [
        # cv2.putText не умеет кириллицу — на кадре только таймкод
        {"timestamp_sec": t, "image_base64": video.to_jpeg_b64(video.annotate(f, video.fmt_tc(t)))}
        for t, f in shots.items()
    ]
