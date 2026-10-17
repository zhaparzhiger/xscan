"""Разведка: что именно видит локальный VLM (Qwen2.5-VL) на размеченных моментах.

Для каждого видео с нарушением берём кадры вокруг таймкода (t-4 ... t+4, раз в секунду) и просим описать
действия людей. Результат -> data/vlm_probe.json, по нему вручную группируем типы нарушений.

    python ml/vlm_probe.py --videos ~/Downloads/open/videos [--limit 8]
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

PROMPT = (
    "These are consecutive frames (one per second) from a fixed top-down camera in a bank cash room. "
    "The cashier sits at the desk; other people (clients, cash collectors) may enter. A safe is the grey cabinet. "
    "Describe step by step what each person does: handling banknotes, opening or closing the safe, "
    "leaving cash on the desk, people entering or leaving, leaving the workplace. "
    "Then answer: is there a possible cash-handling security violation, and what exactly is it? "
    "Be factual, mention only what is visible."
)


def load_vlm(path: Path):
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        path, torch_dtype=torch.float16, device_map="cuda", attn_implementation="sdpa")
    proc = AutoProcessor.from_pretrained(path, min_pixels=200 * 28 * 28, max_pixels=360 * 28 * 28)
    return model, proc


def grab(video_path: Path, times: list[float]) -> list[Image.Image]:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    out = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t * fps)))
        ok, f = cap.read()
        if ok:
            out.append(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    cap.release()
    return out


@torch.inference_mode()
def ask(model, proc, images: list[Image.Image], prompt: str, max_new: int = 380) -> str:
    content = [{"type": "image", "image": im} for im in images] + [{"type": "text", "text": prompt}]
    text = proc.apply_chat_template([{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[text], images=images, return_tensors="pt").to("cuda")
    out = model.generate(**inputs, max_new_tokens=max_new, do_sample=False)
    return proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--model", type=Path, default=config.MODELS_DIR / "qwen25vl3b")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--span", type=float, default=4.0)
    args = ap.parse_args()
    rows = [r for r in csv.DictReader(Path("data/labels.csv").open(encoding="utf-8")) if r["label"] == "violation"][:args.limit]
    model, proc = load_vlm(args.model)
    res = {}
    for r in rows:
        tc = float(r["timecode_sec"])
        ts = [max(0.0, tc + d) for d in range(-int(args.span), int(args.span) + 1, 2)]
        imgs = grab(args.videos / r["file"], ts)
        t0 = time.time()
        ans = ask(model, proc, imgs, PROMPT)
        res[r["video_id"]] = {"tc": tc, "frames_at": ts, "answer": ans}
        print(f"\n=== {r['video_id']} tc={tc} ({time.time() - t0:.0f} с)\n{ans}", flush=True)
        Path("data/vlm_probe.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
