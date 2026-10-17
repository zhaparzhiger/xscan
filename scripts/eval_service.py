"""Прогон всего пайплайна сервиса (как в проде) по датасету и сравнение с labels.csv.

    .venv/bin/python scripts/eval_service.py --videos ~/Downloads/open/videos
Внимание: модель обучена на этих же видео — честная оценка только в выводе ml/train.py (кросс-валидация).
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.pipeline.analyze import analyze_video  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--videos", type=Path, required=True)
ap.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
a = ap.parse_args()
with a.labels.open(encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
ok = 0
for r in rows:
    res = analyze_video(a.videos / r["file"])
    pred = [(v["timecode_sec"], v["type_id"]) for v in res["violations"]]
    hit = (res["verdict"] == r["label"])
    ok += hit
    print(f"{'OK ' if hit else 'ERR'} {r['video_id']:6} true={r['label']:12} tc={r['timecode_sec'] or '-':>5}  "
          f"pred={pred}  {res['processing_sec']}s")
print(f"\naccuracy {ok}/{len(rows)}")
