"""Qwen3-VL находит рамки объектов (экран ноутбука, сейф, стол) на кадре каждого видео -> data/boxes.json.

Рамки нужны, чтобы дальше смотреть на мелкие состояния (экран включён/заблокирован, дверца сейфа,
вещи на столе) по вырезкам, а не по всему кадру. Координаты модели — 0..1000 по осям.

    python -m ml.ground --videos ~/Downloads/open/videos
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import cv2
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.vlm_qa import load  # noqa: E402

OBJECTS = {
    "laptop_screen": "the screen of the open laptop on the desk",
    "safe": "the grey metal safe cabinet",
    "desk": "the wooden office desk",
}


@torch.inference_mode()
def find(model, proc, image: Image.Image, what: str):
    q = f'Locate {what} in the image. Output its bounding box as JSON: {{"bbox_2d": [x1, y1, x2, y2]}}. If it is not visible output {{"bbox_2d": null}}.'
    msgs = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": q}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[text], images=[image], return_tensors="pt").to(model.device)
    out = model.generate(**inputs, max_new_tokens=60, do_sample=False)
    ans = proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
    br = re.search(r"\[([^\]]*)\]", ans)
    m = re.findall(r"-?\d+(?:\.\d+)?", br.group(1)) if br else []
    return [float(x) for x in m[:4]] if len(m) >= 4 else None, ans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--t", type=float, default=1.5)
    args = ap.parse_args()
    model, proc = load()
    res, seen = {}, {}
    for r in csv.DictReader(Path("data/labels.csv").open(encoding="utf-8")):
        path = args.videos / r["file"]
        key = path.stat().st_size
        if key in seen:               # дубликаты файлов (X-4/X-47, X-5/X-48)
            res[r["video_id"]] = res[seen[key]]
            continue
        seen[key] = r["video_id"]
        cap = cv2.VideoCapture(str(path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(args.t * (cap.get(cv2.CAP_PROP_FPS) or 30)))
        ok, f = cap.read(); cap.release()
        img = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        res[r["video_id"]] = {"size": [img.width, img.height]}
        for k, what in OBJECTS.items():
            box, raw = find(model, proc, img, what)
            res[r["video_id"]][k] = box
            res[r["video_id"]][k + "_raw"] = raw
        print(r["video_id"], {k: res[r["video_id"]][k] for k in OBJECTS}, flush=True)
        Path("data/boxes.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
