"""FastAPI: публичный API для жюри (по ключу) + веб-интерфейс для пользователя."""
import logging
import secrets
import shutil

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config, jobs
from app.schemas import AnalyzeResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="ForteBank Cashier AI", version="0.1.0")

ALLOWED_EXT = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
API_FIELDS = ("type", "timecode_sec", "description", "evidence_frames")


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or not secrets.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


def _store_upload(file: UploadFile) -> str:
    name = file.filename or "video.mov"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ".mov"
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=415, detail=f"unsupported file type {ext}, expected .mov")
    job_id = jobs.new_job_id()
    dst = config.UPLOAD_DIR / f"{job_id}{ext}"
    with dst.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    if dst.stat().st_size > config.MAX_UPLOAD_MB * 1024 * 1024:
        dst.unlink()
        raise HTTPException(status_code=413, detail="file too large")
    return jobs.submit(dst)


def _job_or_404(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _public(job: dict) -> dict:
    """Ответ строго по схеме ТЗ (лишние поля для UI отрезаем)."""
    out = {
        "job_id": job["job_id"],
        "status": job["status"],
        "verdict": job.get("verdict"),
        "violations": [{k: v[k] for k in API_FIELDS} for v in job.get("violations", [])],
    }
    if job["status"] == "failed":
        out["error"] = job.get("error")
    return out


# ---------- API для жюри (раздел 10 ТЗ) ----------

@app.post("/api/v1/analyze", response_model=AnalyzeResponse, dependencies=[Depends(require_api_key)])
def api_analyze(file: UploadFile = File(...)):
    return {"job_id": _store_upload(file), "status": "processing"}


@app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def api_job(job_id: str):
    return _public(_job_or_404(job_id))


# ---------- Эндпоинты для веб-интерфейса (без ключа, с расширенными полями) ----------

@app.post("/ui/analyze")
def ui_analyze(file: UploadFile = File(...)):
    return {"job_id": _store_upload(file), "status": "processing"}


@app.get("/ui/jobs/{job_id}")
def ui_job(job_id: str):
    return _job_or_404(job_id)


@app.get("/health")
def health():
    from app.pipeline.detector import model_status
    return {"status": "ok", **model_status()}


@app.on_event("startup")
def _startup() -> None:
    jobs.recover_unfinished()


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")
