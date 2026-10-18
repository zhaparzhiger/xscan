"""Какие модели VLM доступны и какие подходят для анализа видео.

Берёт доступ из .env (GOOGLE_APPLICATION_CREDENTIALS — Vertex AI, иначе VLM_API_KEY), пробует каждую
модель-кандидат на коротком ролике датасета и печатает: доступна ли, время ответа, вердикт.

    python scripts/vlm_models.py                      # кандидаты из VLM_CANDIDATES на X-28
    python scripts/vlm_models.py --video X-29 --models <id1> <id2>
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402,F401  (.env)
from app.pipeline import vlm, video  # noqa: E402

CANDIDATES = [m.strip() for m in os.getenv("VLM_CANDIDATES", "").split(",") if m.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="X-28")
    ap.add_argument("--models", nargs="*", default=CANDIDATES)
    a = ap.parse_args()
    videos = Path(__import__("os").environ.get("XSCAN_VIDEOS", "data/open/videos"))
    path = next(videos.glob(f"*-{a.video.split('-')[-1]}.mov"))
    dur = video.probe(path).duration_sec
    print(f"доступ: {vlm.backend()}, ролик {path.name} ({dur:.0f} с)\n")
    for m in a.models:
        t0 = time.time()
        try:
            vlm.FALLBACK_MODELS.clear()  # без подмены модели — проверяем именно эту
            ans = vlm.ask(path, dur, m)
            found = vlm.violations(ans, dur)
            got = ", ".join(f"{f['type_id']}@{f['timecode_sec']:.0f}" for f in found) or "нарушений нет"
            u = ans.get("_usage", {})
            print(f"OK   {m:24} {time.time() - t0:5.1f} с  токены {u.get('promptTokenCount', 0)}/"
                  f"{u.get('candidatesTokenCount', 0) + u.get('thoughtsTokenCount', 0)}  -> {got}")
        except Exception as e:  # noqa: BLE001
            print(f"--   {m:24} недоступна: {str(e)[:160]}")


if __name__ == "__main__":
    main()
