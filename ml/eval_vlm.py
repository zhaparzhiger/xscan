"""Замер VLM-анализатора на открытом датасете: 40 уникальных видео (дубликаты X-4/X-47, X-5/X-48 склеены).

Обучения нет (zero-shot), поэтому кросс-валидация не нужна. Но подсказки в промпте (SCENE_NOTES) составлены
по этим же роликам — цифры оптимистичнее, чем будут на закрытом тесте.

    python ml/eval_vlm.py                            # модель из VLM_MODEL
    python ml/eval_vlm.py --model <id> --workers 4
Ответы кэшируются в data/vlm/<model>/<id>.json (повторный запуск не тратит запросы; --fresh — заново).
"""
import argparse
import base64
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402,F401  (.env)
from app.pipeline import vlm, video  # noqa: E402
from ml.labels2 import VIDEOS, unique_videos  # noqa: E402


def run_one(v, model, cache: Path, fresh: bool):
    dst = cache / f"{v['id']}.json"
    if dst.exists() and not fresh:
        old = json.loads(dst.read_text(encoding="utf-8"))
        if "_error" not in old:  # ошибки не кэшируем — при повторе запрашиваем заново
            return v, old
    path = VIDEOS / v["file"]
    dur = video.probe(path).duration_sec
    try:
        ans = vlm.ask(path, dur, model)
    except Exception as e:  # noqa: BLE001
        ans = {"_error": str(e)}
    ans["_duration"] = dur
    dst.write_text(json.dumps(ans, ensure_ascii=False, indent=1), encoding="utf-8")
    return v, ans


def _still(path: Path, t: float) -> str:
    """Кадр ролика в момент t как base64 jpeg — для страницы «Замер» в интерфейсе."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(t, 0) * 1000)
    ok, f = cap.read()
    cap.release()
    if not ok:
        return ""
    h = 220
    f = cv2.resize(f, (int(f.shape[1] * h / f.shape[0]), h))
    return base64.b64encode(cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 70])[1]).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=vlm.MODEL)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--tol", type=float, default=3.0)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--only", nargs="*", help="id роликов, например X-28 X-29")
    ap.add_argument("--tag", default="", help="метка варианта (промпт/разрешение) — отдельный кэш")
    a = ap.parse_args()

    vids = unique_videos()
    if a.only:
        vids = [v for v in vids if v["id"] in a.only]
    cache = config.DATA_DIR / "vlm" / (a.model + (f"-think-{vlm.THINKING}" if vlm.THINKING else "")
                                          + (f"-{a.tag}" if a.tag else ""))
    cache.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(lambda v: run_one(v, a.model, cache, a.fresh), vids))

    tp = fn = fp = tn = err = loc = 0
    secs = []
    rows = []
    for v, ans in sorted(results, key=lambda r: int(r[0]["id"].split("-")[1])):
        if "_error" in ans:
            err += 1
            print(f"{v['id']:6} ОШИБКА {ans['_error'][:150]}")
            continue
        found = vlm.violations(ans, ans["_duration"])
        pred, truth = bool(found), bool(v["tcs"])
        secs.append(ans.get("_sec", 0))
        hit = ""
        if truth and pred:
            tp += 1
            d = min(abs(f["timecode_sec"] - tc) for f in found for tc in v["tcs"])
            loc += d <= a.tol
            hit = f"Δ={d:.1f}s"
        elif truth:
            fn += 1
        elif pred:
            fp += 1
        else:
            tn += 1
        found_rows = [{"type_id": f["type_id"], "timecode_sec": round(f["timecode_sec"], 1),
                       "confidence": round(f["confidence"], 2)} for f in found]
        t_show = found[0]["timecode_sec"] if found else (v["tcs"][0] if v["tcs"] else ans["_duration"] / 2)
        rows.append({"id": v["id"], "truth": truth, "truth_tcs": v["tcs"], "pred": pred, "found": found_rows,
                     "sec": ans.get("_sec", 0), "duration": round(ans["_duration"], 1),
                     "delta": (None if not (truth and pred) else round(d, 1)),
                     "still": _still(VIDEOS / v["file"], t_show), "still_t": round(t_show, 1)})
        mark = "OK " if pred == truth else "ERR"
        got = ", ".join(f"{f['type_id']}@{f['timecode_sec']:.0f}({f['confidence']:.2f})" for f in found) or "—"
        print(f"{v['id']:6} {mark} истина={'нар@' + ','.join(f'{t:.0f}' for t in v['tcs']) if truth else 'норма':12} "
              f"ответ={got} {hit} [{ans.get('_sec', 0)}с]")

    n = tp + fn + fp + tn
    report = {"model": a.model, "tag": a.tag, "tol": a.tol, "n": n,
              "tp": tp, "fn": fn, "fp": fp, "tn": tn, "loc": loc,
              "avg_sec": round(sum(secs) / max(len(secs), 1), 1), "max_sec": round(max(secs, default=0), 1),
              "made": time.strftime("%d.%m.%Y %H:%M"), "rows": rows}
    out = config.DATA_DIR / "eval_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    print(f"отчёт для интерфейса: {out}")
    print(f"\nмодель {a.model}: видео {n} (+{err} ошибок), {time.time() - t0:.0f} с всего")
    print(f"recall {tp}/{tp + fn} = {tp / max(tp + fn, 1):.2f}   ложные тревоги {fp}/{fp + tn} = {fp / max(fp + tn, 1):.2f}   "
          f"точность вердикта {(tp + tn) / max(n, 1):.2f}")
    print(f"таймкод в ±{a.tol:.0f} с: {loc}/{tp}   время на видео: среднее {sum(secs) / max(len(secs), 1):.1f} с, "
          f"макс {max(secs, default=0):.1f} с")
    tin = sum(ans.get("_usage", {}).get("promptTokenCount", 0) for _, ans in results)
    tout = sum(ans.get("_usage", {}).get("candidatesTokenCount", 0) + ans.get("_usage", {}).get("thoughtsTokenCount", 0)
               for _, ans in results)
    print(f"токены: вход {tin:,}, выход (с рассуждениями) {tout:,}; на видео в среднем {tin // max(n, 1):,} / {tout // max(n, 1):,}"
          " — умножить на цену модели с ai.google.dev/pricing")


if __name__ == "__main__":
    main()
