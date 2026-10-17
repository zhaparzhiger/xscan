"""Очередь задач анализа: in-process пул потоков + состояние на диске (переживает рестарт)."""
import json
import logging
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import botapi, config
from app.pipeline.analyze import analyze_video

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=config.WORKERS)
_lock = threading.Lock()


def _job_path(job_id: str) -> Path:
    return config.JOBS_DIR / f"{job_id}.json"


def _save(job: dict) -> None:
    tmp = _job_path(job["job_id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_job_path(job["job_id"]))


def get_job(job_id: str) -> dict | None:
    if not all(c.isalnum() for c in job_id):
        return None
    p = _job_path(job_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _run(job_id: str, video_path: Path) -> None:
    try:
        result = analyze_video(video_path)
        job = {"job_id": job_id, "status": "done", **result}
    except Exception as e:  # noqa: BLE001 — любая ошибка = failed, сервис живёт дальше
        log.error("job %s failed: %s", job_id, traceback.format_exc())
        job = {"job_id": job_id, "status": "failed", "verdict": None, "violations": [], "error": str(e)}
    with _lock:
        _save(job)


def submit(video_path: Path) -> str:
    job_id = video_path.stem
    with _lock:
        _save({"job_id": job_id, "status": "processing", "verdict": None, "violations": []})
    botapi.create_task(job_id, video_path)  # видео сразу доступно внешним агентам
    _executor.submit(_run, job_id, video_path)
    return job_id


def save_meta(job_id: str, file_name: str) -> None:
    """Имя исходного файла и время загрузки — рядом с задачей, отдельно от ответа по схеме ТЗ."""
    meta = {"file": file_name, "created": time.time()}
    (config.JOBS_DIR / f"{job_id}.meta").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def list_jobs(limit: int = 200) -> list[dict]:
    """Краткая сводка по всем проверкам на сервере (для истории в интерфейсе), новые сверху."""
    out = []
    for p in config.JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if "status" not in job:
            continue
        m = p.with_suffix(".meta")
        meta = json.loads(m.read_text(encoding="utf-8")) if m.exists() else {}
        out.append({
            "job_id": job["job_id"], "status": job["status"], "verdict": job.get("verdict"),
            "file": meta.get("file") or f"{job['job_id']}.mov",
            "created": meta.get("created") or p.stat().st_mtime,
            "duration_sec": job.get("duration_sec"), "processing_sec": job.get("processing_sec"),
            "types": [v.get("type_id") for v in job.get("violations", [])],
        })
    out.sort(key=lambda j: j["created"], reverse=True)
    return out[:limit]


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def recover_unfinished() -> None:
    """После рестарта перезапускаем задачи, которые остались в processing."""
    for p in config.JOBS_DIR.glob("*.json"):
        job = json.loads(p.read_text(encoding="utf-8"))
        if job.get("status") != "processing":
            continue
        videos = list(config.UPLOAD_DIR.glob(f"{job['job_id']}.*"))
        if videos:
            _executor.submit(_run, job["job_id"], videos[0])
        else:
            job.update(status="failed", error="video lost after restart")
            _save(job)
