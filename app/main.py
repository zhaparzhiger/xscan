"""FastAPI: публичный API для жюри (по ключу) + веб-интерфейс для пользователя."""
import logging
import secrets
import shutil

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from app import auth, botapi, config, jobs
from app.schemas import AnalyzeResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="ForteBank XScan", version="0.1.0")

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
    job_id = jobs.submit(dst)
    jobs.save_meta(job_id, name)
    return job_id


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


# ---------- Веб-интерфейс: вход по логину/паролю, расширенные поля ----------

class LoginIn(BaseModel):
    login: str
    password: str


@app.post("/ui/login")
def ui_login(body: LoginIn, request: Request, response: Response):
    token = auth.login(request, body.login.strip(), body.password)
    response.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_TTL, httponly=True,
                        samesite="lax", secure=auth.is_https(request))
    return {"user": body.login.strip()}


@app.post("/ui/logout")
def ui_logout(response: Response):
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@app.get("/ui/config")
def ui_config():
    """Публичные настройки экрана входа: тестовая учётка (если включена в .env)."""
    return {"demo": auth.demo_credentials()}


@app.get("/ui/me")
def ui_me(user: str = Depends(auth.require_session)):
    return {"user": user}


@app.post("/ui/analyze", dependencies=[Depends(auth.require_session)])
def ui_analyze(file: UploadFile = File(...)):
    return {"job_id": _store_upload(file), "status": "processing"}


@app.get("/ui/jobs", dependencies=[Depends(auth.require_session)])
def ui_jobs():
    return {"jobs": jobs.list_jobs()}


@app.get("/ui/jobs/{job_id}/video", dependencies=[Depends(auth.require_session)])
def ui_job_video(job_id: str):
    """Исходное видео проверки — чтобы открыть старый отчёт из истории вместе с плеером."""
    if not job_id.isalnum():
        raise HTTPException(404, "not found")
    files = list(config.UPLOAD_DIR.glob(f"{job_id}.*"))
    if not files:
        raise HTTPException(404, "видео удалено")
    return FileResponse(files[0], media_type="video/quicktime")


@app.get("/ui/jobs/{job_id}", dependencies=[Depends(auth.require_session)])
def ui_job(job_id: str):
    return {**_job_or_404(job_id), "agent_findings": botapi.findings_for_job(job_id)}


@app.get("/ui/eval", dependencies=[Depends(auth.require_session)])
def ui_eval():
    """Последний замер на открытом датасете (его пишет ml/eval_gemini.py) — для страницы «Замер»."""
    f = config.DATA_DIR / "eval_report.json"
    if not f.exists():
        raise HTTPException(404, "замер ещё не запускали: python ml/eval_gemini.py")
    return Response(f.read_text(encoding="utf-8"), media_type="application/json")


# ---------- Bot API для агентов-процессов (app/botapi.py) ----------
app.include_router(botapi.router)


@app.get("/health")
def health():
    if config.ANALYZER == "gemini":
        from app.pipeline import gemini
        return {"status": "ok", "analyzer": "gemini", "backend": gemini.backend(), "model": gemini.MODEL}
    from app.pipeline.detector import model_status
    return {"status": "ok", "analyzer": "local", **model_status()}


@app.on_event("startup")
def _startup() -> None:
    jobs.recover_unfinished()


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
# CRM-интерфейс: /design/ (вход по логину, см. app/auth.py)
if (config.ROOT / "design").is_dir():
    app.mount("/design", StaticFiles(directory=config.ROOT / "design", html=True), name="design")


@app.get("/")
def index():
    return RedirectResponse("/design/")
