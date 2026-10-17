"""open_labels.xlsx -> data/labels.csv

Нормализует имена (в датасете смешаны латинская X и кириллическая Х) и таймкоды ("1минута 8 секунда" -> 68).
Колонку type заполняем руками после просмотра роликов (id из app/rules/violations.yaml).

    python ml/prepare_labels.py --xlsx ~/Downloads/open/open_labels.xlsx --videos ~/Downloads/open/videos
"""
import argparse
import csv
import html
import re
import zipfile
from pathlib import Path


def norm_id(name: str) -> str:
    return name.strip().replace("Х", "X").replace("х", "x").upper()


def parse_tc(text: str) -> float | None:
    if not text or not text.strip():
        return None
    m = re.search(r"(\d+)\s*мин", text)
    s = re.search(r"(\d+(?:[.,]\d+)?)\s*сек", text)
    if not m and not s:
        return float(text.replace(",", "."))
    return (int(m.group(1)) * 60 if m else 0) + (float(s.group(1).replace(",", ".")) if s else 0)


def read_xlsx(path: Path) -> list[list[str]]:
    """Минимальный парсер первого листа xlsx без openpyxl."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        xml = z.read("xl/sharedStrings.xml").decode()
        shared = [html.unescape(re.sub(r"<[^>]+>", "", s)) for s in re.findall(r"<si>(.*?)</si>", xml, re.S)]
    xml = z.read("xl/worksheets/sheet1.xml").decode()
    rows = []
    for row in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
        cells = {}
        for attrs, body in re.findall(r"<c ([^>]*?)(?:/>|>(.*?)</c>)", row, re.S):
            col = re.search(r'r="([A-Z]+)', attrs).group(1)
            v = re.search(r"<v>(.*?)</v>", body or "")
            val = v.group(1) if v else html.unescape(re.sub(r"<[^>]+>", "", body or ""))
            if 't="s"' in attrs:
                val = shared[int(val)]
            cells[col] = val
        rows.append([cells.get(c, "") for c in "ABC"])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", type=Path, required=True)
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/labels.csv"))
    args = ap.parse_args()

    files = {norm_id(p.stem): p.name for p in args.videos.iterdir() if p.suffix.lower() in {".mov", ".mp4"}}
    old_types = {}
    if args.out.exists():  # не теряем уже проставленные руками типы
        with args.out.open(encoding="utf-8") as f:
            old_types = {r["video_id"]: r.get("type", "") for r in csv.DictReader(f)}

    rows = []
    for name, tc, label in read_xlsx(args.xlsx)[1:]:
        vid = norm_id(name)
        if vid not in files:
            print(f"WARN: нет файла для {name}")
            continue
        is_v = "без" not in label.lower()
        rows.append({
            "video_id": vid, "file": files[vid], "label": "violation" if is_v else "no_violation",
            "timecode_sec": parse_tc(tc) if is_v else "", "type": old_types.get(vid, ""),
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["video_id", "file", "label", "timecode_sec", "type"])
        w.writeheader()
        w.writerows(rows)
    n_v = sum(r["label"] == "violation" for r in rows)
    print(f"{len(rows)} видео ({n_v} с нарушением, {len(rows) - n_v} без) -> {args.out}")


if __name__ == "__main__":
    main()
