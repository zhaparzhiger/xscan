"""Qwen3-VL (4-bit) отвечает на короткие вопросы да/нет по кадрам: основа агентов сцены.

Ответ берётся по логитам первого токена (Yes/No), без генерации текста: десятки миллисекунд на вопрос.
Модель не получает подсказок про «нарушение» — только нейтральные вопросы о том, что видно.

    python ml/vlm_qa.py --videos ~/Downloads/open/videos --ids X-17 X-13 X-26
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

MODEL_DIR = config.MODELS_DIR / "qwen3vl4b"

QUESTIONS = {
    "cashier_present": "Is there a person sitting or standing at the cashier desk (behind the desk)?",
    "safe_open": "Is the door of the grey metal safe cabinet open?",
    "cash_on_desk": "Are there banknotes or a cash bag lying on the desk?",
    "extra_person": "Are there two or more people in the room?",
    "person_standing_far": "Is the person who works at the desk away from the desk, walking in the room or near the door?",
}


def load(device="cuda"):
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig

    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type="nf4")
    model = AutoModelForImageTextToText.from_pretrained(MODEL_DIR, quantization_config=q, device_map=device)
    proc = AutoProcessor.from_pretrained(MODEL_DIR, min_pixels=160 * 28 * 28, max_pixels=320 * 28 * 28)
    return model.eval(), proc


@torch.inference_mode()
def yes_prob(model, proc, image: Image.Image, question: str) -> float:
    msgs = [{"role": "user", "content": [{"type": "image", "image": image},
                                          {"type": "text", "text": question + " Answer with Yes or No only."}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = proc(text=[text], images=[image], return_tensors="pt").to(model.device)
    logits = model(**inputs).logits[0, -1].float()
    tok = proc.tokenizer
    yes = [tok.encode(w, add_special_tokens=False)[0] for w in ("Yes", "yes")]
    no = [tok.encode(w, add_special_tokens=False)[0] for w in ("No", "no")]
    py = torch.logsumexp(logits[yes], 0)
    pn = torch.logsumexp(logits[no], 0)
    return float(torch.sigmoid(py - pn))


def frame_at(path: Path, t: float) -> Image.Image:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
    ok, f = cap.read()
    cap.release()
    return Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--ids", nargs="+", default=["X-17"])
    ap.add_argument("--times", nargs="+", type=float, default=[2, 6, 10])
    ap.add_argument("--all", action="store_true", help="все видео, кадр каждые --step секунд -> data/vlm_qa/<id>.json")
    ap.add_argument("--step", type=float, default=2.0)
    args = ap.parse_args()
    import csv
    files = {r["video_id"]: r["file"] for r in csv.DictReader(Path("data/labels.csv").open(encoding="utf-8"))}
    t0 = time.time()
    model, proc = load()
    print(f"загрузка: {time.time() - t0:.0f} с, VRAM {torch.cuda.memory_allocated() / 2**30:.1f} ГБ", flush=True)
    if args.all:
        import json
        out = Path("data/vlm_qa"); out.mkdir(parents=True, exist_ok=True)
        for vid, fn in files.items():
            dst = out / f"{vid}.json"
            if dst.exists():
                continue
            cap = cv2.VideoCapture(str(args.videos / fn)); dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30); cap.release()
            rows, t1 = [], time.time()
            for t in np.arange(0.5, dur - 0.3, args.step):
                img = frame_at(args.videos / fn, float(t))
                rows.append({"t": float(t), **{k: yes_prob(model, proc, img, q) for k, q in QUESTIONS.items()}})
            dst.write_text(json.dumps(rows), encoding="utf-8")
            print(f"{vid}: {len(rows)} кадров, {time.time() - t1:.0f} с", flush=True)
        return
    for vid in args.ids:
        for t in args.times:
            img = frame_at(args.videos / files[vid], t)
            t1 = time.time()
            res = {k: yes_prob(model, proc, img, q) for k, q in QUESTIONS.items()}
            dt = time.time() - t1
            print(f"{vid} t={t:>4.0f}s ({dt:.1f} с на {len(QUESTIONS)} вопросов) " +
                  " ".join(f"{k}={v:.2f}" for k, v in res.items()), flush=True)


if __name__ == "__main__":
    main()
