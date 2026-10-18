"""Анализ видео мультимодальной моделью (VLM) по API (режим ANALYZER=vlm).

Видео локально ужимается (512 px, 5 кадров/с, без звука — звук по ТЗ не анализируем) и уходит одним запросом.
Модель возвращает строгий JSON: вердикт, типы из app/rules/violations.yaml, таймкоды, что видно.
Нормативы и кадры-доказательства подставляет сервис сам (из проверенной базы и из исходного видео),
модель ссылки на законы не генерирует.
"""
import base64
import json
import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2

from app.rules import registry

log = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta"
MODEL = os.getenv("VLM_MODEL", "")  # идентификатор модели — только в настройках (.env / панель хостинга)
# запасные модели: квота считается отдельно на каждую модель, при 429/503 берём следующую
FALLBACK_MODELS = [m.strip() for m in os.getenv(
    "VLM_FALLBACK_MODELS", "").split(",") if m.strip()]
VIDEO_FPS = float(os.getenv("VLM_VIDEO_FPS", "2"))  # сколько кадров/с смотрит модель (влияет на точность таймкода)
MIN_CONFIDENCE = float(os.getenv("VLM_MIN_CONFIDENCE", "0"))
TIMEOUT = float(os.getenv("VLM_TIMEOUT_SEC", "150"))  # один запрос
BUDGET_SEC = float(os.getenv("VLM_BUDGET_SEC", "240"))  # все попытки по одному видео (лимит жюри — 300 с)
# уровень «размышлений» модели: low — быстрее, high — дольше; пусто — по умолчанию модели
THINKING = os.getenv("VLM_THINKING", "").strip().lower()
# ширина ужатого видео и детализация кадров у модели (high — видно экран/дверцу сейфа, токенов больше)
VIDEO_WIDTH = int(os.getenv("VLM_VIDEO_WIDTH", "512"))
MEDIA_RESOLUTION = os.getenv("VLM_MEDIA_RESOLUTION", "").strip().upper()  # LOW / MEDIUM / HIGH

# Что выяснено по датасету (HANDOFF.md): нормальные и нарушающие ролики почти одинаковы, отличие в деталях.
SCENE_NOTES = """Камера снимает кассовый кабинет банка сверху (ракурсов несколько). В кадре стол кассира с ноутбуком,
счётная машинка, сейф/металлический шкаф, дверь. Ролики постановочные: в нормальных и нарушающих роликах происходят ПОХОЖИЕ
действия, нарушение отличается деталями. Сначала пойми, что происходит в целом, потом ищи отклонение от штатного порядка.

ЧТО НОРМА (само по себе не нарушение):
- клиент или посетитель заходит в кабинет через дверь, садится напротив кассира и его обслуживают: передаёт или получает деньги,
  документы, карту. Обслуживание клиента — штатная работа кассы, вход клиента НЕ нарушение;
- кассир принимает деньги у клиента и при нём пересчитывает их на счётной машинке или вручную;
- кассир отходит или уходит, заблокировав ноутбук (экран тёмный) и убрав деньги;
- человек проходит за стеклянной дверью в коридоре.

ЧТО НАРУШЕНИЕ (ищи именно это):
- работа с деньгами клиента не по порядку (cash_handling): деньги клиента пересчитывают или убирают уже ПОСЛЕ того, как клиент ушёл,
  или когда клиент на это не смотрит; деньги передаются мимо стола/машинки, остаются лежать открыто, клиент берёт деньги со стола сам;
- кассир во время работы с клиентом или с наличными держит в руках телефон, ест, пьёт; личные вещи на рабочем месте (personal_items);
- кассир уходит от стола или из кабинета и оставляет без присмотра наличные, ценности или РАЗБЛОКИРОВАННЫЙ ноутбук
  (экран светлый, открыта таблица/программа) — cashier_left_workplace;
- сейф/шкаф с ценностями оставлен открытым: дверца открыта или приоткрыта, ключ в замке, а кассир отошёл или занят другим;
- посторонний (unauthorized_person) — ТОЛЬКО если человек, не являющийся кассиром, заходит за стол кассира, к сейфу или к ценностям,
  берёт деньги или документы со стороны кассира, остаётся в кабинете без кассира или входит, пока кассира нет. Клиент на стуле напротив — не посторонний;
- дверь кассы (door_open) — кассир работает с наличными, а дверь кабинета распахнута настежь и так остаётся. Дверь, через которую
  клиент зашёл и закрыл за собой, — не нарушение;
- нарушения порядка передачи ценностей инкассатору (сумка/мешок).

Таймкод — момент, когда нарушение НАЧИНАЕТСЯ (деньги пересчитывают без клиента, сейф остался открытым, кассир отошёл),
а не момент, когда кто-то вошёл в кабинет."""


def _types_text() -> str:
    kb = registry.load()["violations"]
    return "\n".join(f"- {tid}: {v['title']} — {v['observed']}" for tid, v in kb.items())


def _prompt(duration: float) -> str:
    return f"""Ты проверяешь соблюдение кассовой дисциплины по видео с камеры наблюдения. Длительность видео {duration:.1f} с.
{SCENE_NOTES}

Допустимые типы нарушений (type_id):
{_types_text()}

Правила ответа:
- Оценивай только то, что видно. Звука нет. Не опознавай людей, не описывай их внешность сверх необходимого (роль: кассир, посетитель, инкассатор).
- Не утверждай нарушение, если для этого нужны невидимые данные (документы, проводки).
- Пропуск нарушения хуже ложной тревоги: если признаки нарушения видны, но ты не уверен — укажи его с низкой confidence.
- timecode_sec — секунды от начала видео (0..{duration:.1f}), с точностью до 1 с.
- what_is_seen — 1–2 предложения по-русски: что конкретно видно в этот момент.
- Если нарушений нет — verdict "no_violation" и пустой список."""


def _schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "scene_summary": {"type": "STRING"},
            "verdict": {"type": "STRING", "enum": ["violation", "no_violation"]},
            "violations": {"type": "ARRAY", "items": {
                "type": "OBJECT",
                "properties": {
                    "type_id": {"type": "STRING", "enum": registry.type_ids()},
                    "timecode_sec": {"type": "NUMBER"},
                    "confidence": {"type": "NUMBER"},
                    "what_is_seen": {"type": "STRING"},
                },
                "required": ["type_id", "timecode_sec", "confidence", "what_is_seen"],
            }},
        },
        "required": ["scene_summary", "verdict", "violations"],
    }


def compress(src: Path, dst: Path, width: int | None = None, fps: float = 5.0) -> None:
    """Уменьшает видео для отправки: ширина VLM_VIDEO_WIDTH (512), ~5 кадров/с, без звука. Время ролика сохраняется."""
    width = width or VIDEO_WIDTH
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise ValueError("не удалось открыть видео")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / fps))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    size = (width, int(round(h * width / w / 2)) * 2) if w > width else (w, h)
    out = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), src_fps / step, size)
    i = 0
    while cap.grab():
        if i % step == 0:
            _, f = cap.retrieve()
            out.write(cv2.resize(f, size, interpolation=cv2.INTER_AREA) if f.shape[1] != size[0] else f)
        i += 1
    cap.release()
    out.release()


# Vertex AI через сервисный аккаунт (платные квоты проекта): GOOGLE_APPLICATION_CREDENTIALS=путь к JSON.
# Иначе — по ключу VLM_API_KEY (у бесплатного проекта 20 запросов в сутки на модель).
SA_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
VERTEX_LOCATION = os.getenv("VLM_VERTEX_LOCATION", "global")
_creds = None
_auth_lock = threading.Lock()


def _vertex_auth() -> tuple[str, str]:
    """(project_id, bearer-токен) из сервисного аккаунта; токен обновляется, когда истёк."""
    global _creds
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    with _auth_lock:  # несколько обработчиков параллельно: без блокировки первые запросы уходят без токена (401)
        if _creds is None:
            _creds = service_account.Credentials.from_service_account_file(
                SA_FILE, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not _creds.valid:
            _creds.refresh(Request())
        return _creds.project_id, _creds.token


def _endpoint(model: str) -> tuple[str, dict]:
    if SA_FILE:
        project, token = _vertex_auth()
        host = "aiplatform.googleapis.com" if VERTEX_LOCATION == "global" else f"{VERTEX_LOCATION}-aiplatform.googleapis.com"
        url = (f"https://{host}/v1/projects/{project}/locations/{VERTEX_LOCATION}"
               f"/publishers/google/models/{model}:generateContent")
        return url, {"Authorization": f"Bearer {token}"}
    key = os.getenv("VLM_API_KEY")
    if not key:
        raise RuntimeError("не задан ни GOOGLE_APPLICATION_CREDENTIALS, ни VLM_API_KEY в .env")
    return f"{API}/models/{model}:generateContent", {"x-goog-api-key": key}


def backend() -> str:
    return f"vertex/{VERTEX_LOCATION}" if SA_FILE else "api-key"


def _post(model: str, body: dict, timeout: float = TIMEOUT) -> dict:
    url, auth = _endpoint(model)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={**auth, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _generate(body: dict, models: list[str]) -> tuple[dict, str]:
    """Запрос с повтором при перегрузке (503) и переходом на следующую модель при исчерпании квоты (429).

    Общий бюджет BUDGET_SEC на все попытки: жюри ждёт не больше 5 минут, лучше честная ошибка, чем «необработано».
    """
    errors = []
    deadline = time.time() + BUDGET_SEC
    for model in models:
        for attempt in range(2):
            left = deadline - time.time()
            if left < 15:
                raise RuntimeError("VLM: истёк бюджет времени на видео; " + "; ".join(errors))
            try:
                return _post(model, body, timeout=min(TIMEOUT, left)), model
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")
                errors.append(f"{model}: HTTP {e.code}")
                if e.code == 429 or e.code == 404:  # квота модели исчерпана / модель недоступна -> следующая
                    log.warning("vlm %s: HTTP %s, пробую следующую модель", model, e.code)
                    break
                if e.code not in (500, 502, 503, 504):
                    raise RuntimeError(f"VLM {model}: HTTP {e.code}: {msg[:300]}") from None
                time.sleep(4 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError) as e:
                errors.append(f"{model}: {e}")
                time.sleep(3)
    raise RuntimeError("VLM недоступна: " + "; ".join(errors))


def ask(video_path: Path, duration: float, model: str | None = None) -> dict:
    """Возвращает разобранный JSON ответа модели + служебные поля (_model, _sec, _bytes)."""
    model = model or MODEL
    if not model:
        raise RuntimeError("не задана модель: VLM_MODEL в .env")
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        small = Path(d) / "video.mp4"
        compress(video_path, small)
        data = small.read_bytes()
    body = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "video/mp4", "data": base64.b64encode(data).decode()},
             "video_metadata": {"fps": VIDEO_FPS}},
            {"text": _prompt(duration)},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": _schema()},
    }
    if THINKING:
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": THINKING}
    if MEDIA_RESOLUTION:
        body["generationConfig"]["mediaResolution"] = f"MEDIA_RESOLUTION_{MEDIA_RESOLUTION}"
    resp, model = _generate(body, [model] + [m for m in FALLBACK_MODELS if m != model])
    try:
        text = "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])
        out = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"VLM вернула неожиданный ответ: {str(resp)[:300]}") from e
    out["_model"], out["_sec"], out["_bytes"] = model, round(time.time() - t0, 1), len(data)
    out["_usage"] = resp.get("usageMetadata", {})
    return out


def violations(ans: dict, duration: float) -> list[dict]:
    """Нормализует ответ: таймкоды в пределах видео, порог уверенности, без дублей (тот же тип ближе 3 с)."""
    out = []
    for v in sorted(ans.get("violations", []), key=lambda v: -float(v.get("confidence", 0))):
        tc = min(max(float(v["timecode_sec"]), 0.0), max(duration - 0.05, 0.0))
        conf = min(max(float(v.get("confidence", 0)), 0.0), 1.0)
        if conf < MIN_CONFIDENCE:
            continue
        if any(o["type_id"] == v["type_id"] and abs(o["timecode_sec"] - tc) < 3 for o in out):
            continue
        out.append({"type_id": v["type_id"], "timecode_sec": round(tc, 2), "confidence": round(conf, 3),
                    "what_is_seen": str(v.get("what_is_seen", "")).strip()})
    return sorted(out, key=lambda o: o["timecode_sec"])
