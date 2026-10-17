"""Разметка без дубликатов: одинаковые файлы (X-4/X-47, X-5/X-48) -> одно видео со списком таймкодов."""
import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# папка с видео датасета организаторов: переменная окружения XSCAN_VIDEOS или ~/Downloads/open/videos
VIDEOS = Path(os.environ.get("XSCAN_VIDEOS", Path.home() / "Downloads/open/videos"))


def unique_videos(videos_dir: Path = VIDEOS):
    rows = list(csv.DictReader((ROOT / "data/labels.csv").open(encoding="utf-8")))
    by_size, out = {}, {}
    for r in rows:
        key = (videos_dir / r["file"]).stat().st_size
        base = by_size.setdefault(key, r["video_id"])
        v = out.setdefault(base, {"id": base, "file": r["file"], "tcs": [], "dups": []})
        if base != r["video_id"]:
            v["dups"].append(r["video_id"])
        if r["timecode_sec"]:
            v["tcs"].append(float(r["timecode_sec"]))
    return list(out.values())


def target(times, tcs, before=1.0, after=3.0, margin=3.0):
    """1 = момент нарушения, 0 = обычный кадр, -1 = игнор (после первого нарушения, состояние может длиться)."""
    import numpy as np
    y = np.zeros(len(times), int)
    if tcs:
        y[times >= min(tcs) - margin] = -1
        for tc in tcs:
            y[(times >= tc - before) & (times <= tc + after)] = 1
    return y


if __name__ == "__main__":
    vs = unique_videos()
    print(len(vs), "уникальных видео;", sum(bool(v["tcs"]) for v in vs), "с нарушением;",
          [(v["id"], v["dups"], v["tcs"]) for v in vs if v["dups"]])
