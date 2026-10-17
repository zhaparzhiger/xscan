"""XScan Bot API: внешние агенты-процессы забирают задачи (видео), присылают находки и закрывают задачу.

Методы (docs/xscan-slide-botapi-methods.png), все по заголовку X-API-Key:
    GET    /agents                          список агентов
    POST   /agents                          создать агента
    PUT    /agents/{uuid}                   включить/выключить/изменить
    DELETE /agents/{uuid}                   удалить
    GET    /bot-api/ping                    проверка связи
    PUT    /bot-api/tasks-get               выдать агенту следующую задачу (204 — задач нет)
    GET    /bot-api/tasks/{task_uuid}/video скачать видео задачи
    POST   /bot-api/task-result/{agent_uuid} находка: таймкод, кадр, уверенность
    POST   /bot-api/task-done/{task_uuid}   агент закончил задачу

Задача создаётся на каждое загруженное видео (app/jobs.py). Каждый включённый агент обрабатывает её один раз.
Находки агентов — подсказки проверяющему: в ответ API жюри (/api/v1/jobs) они не попадают, видны в интерфейсе.
Состояние — JSON в data/bot/ (переживает рестарт).
"""
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import config

BOT_DIR = config.DATA_DIR / "bot"
BOT_DIR.mkdir(parents=True, exist_ok=True)
AGENTS_FILE = BOT_DIR / "agents.json"
TASKS_FILE = BOT_DIR / "tasks.json"
VERSION = "0.1.0"
# агент взял задачу и пропал -> через столько секунд задача снова доступна ему
LEASE_SEC = 600

_lock = threading.Lock()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


# ---------- модели ----------

AgentKind = Literal["safe", "money", "cashier", "outsiders", "other"]


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: AgentKind = "other"
    description: str = ""
    enabled: bool = True


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: AgentKind | None = None
    description: str | None = None
    enabled: bool | None = None


class AgentResolved(AgentIn):
    uuid: str
    created_at: float
    last_seen_at: float | None = None
    tasks_done: int = 0
    findings: int = 0


class TasksGetIn(BaseModel):
    agent_uuid: str


class TaskOut(BaseModel):
    task_uuid: str
    job_id: str
    video_url: str
    duration_hint_sec: float | None = None
    created_at: float


class FindingIn(BaseModel):
    task_uuid: str
    timecode_sec: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    label: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=500)
    frame_base64: str | None = Field(default=None, description="JPEG кадра-доказательства, base64")


class TaskDoneIn(BaseModel):
    agent_uuid: str


class BotApiPingResult(BaseModel):
    ok: bool
    version: str
    server_time: float
    agents_enabled: int
    tasks_pending: int


# ---------- хранилище ----------

def _agents() -> dict:
    return _read(AGENTS_FILE)


def _tasks() -> dict:
    return _read(TASKS_FILE)


def create_task(job_id: str, video_path: Path) -> str:
    """Вызывается из app/jobs.py при загрузке видео."""
    task_uuid = uuid.uuid4().hex
    with _lock:
        tasks = _tasks()
        tasks[task_uuid] = {"task_uuid": task_uuid, "job_id": job_id, "video": video_path.name,
                            "created_at": time.time(), "taken": {}, "done_by": [], "findings": []}
        _write(TASKS_FILE, tasks)
    return task_uuid


def findings_for_job(job_id: str) -> list[dict]:
    """Находки всех агентов по видео (для интерфейса), без кадров — кадры отдельно по запросу."""
    agents = _agents()
    out = []
    for t in _tasks().values():
        if t["job_id"] != job_id:
            continue
        for f in t["findings"]:
            a = agents.get(f["agent_uuid"], {})
            out.append({**{k: v for k, v in f.items() if k != "frame_base64"},
                        "agent_name": a.get("name", "удалённый агент"), "agent_kind": a.get("kind"),
                        "has_frame": bool(f.get("frame_base64"))})
    return sorted(out, key=lambda f: f["timecode_sec"])


def _pending_for(agent_uuid: str, tasks: dict, now: float) -> list[dict]:
    return [t for t in tasks.values()
            if agent_uuid not in t["done_by"] and now - t["taken"].get(agent_uuid, 0) > LEASE_SEC]


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    from app.main import require_api_key  # один ключ на весь сервис
    require_api_key(x_api_key)


def _agent_or_404(agents: dict, agent_uuid: str) -> dict:
    a = agents.get(agent_uuid)
    if a is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return a


def _task_or_404(tasks: dict, task_uuid: str) -> dict:
    t = tasks.get(task_uuid)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    return t


router = APIRouter(dependencies=[Depends(_require_api_key)])


# ---------- Agents Management ----------

@router.get("/agents", response_model=list[AgentResolved], tags=["agents"])
def list_agents():
    return sorted(_agents().values(), key=lambda a: a["created_at"])


@router.post("/agents", response_model=AgentResolved, status_code=201, tags=["agents"])
def create_agent(body: AgentIn):
    a = {**body.model_dump(), "uuid": uuid.uuid4().hex, "created_at": time.time(),
         "last_seen_at": None, "tasks_done": 0, "findings": 0}
    with _lock:
        agents = _agents()
        agents[a["uuid"]] = a
        _write(AGENTS_FILE, agents)
    return a


@router.put("/agents/{agent_uuid}", response_model=AgentResolved, tags=["agents"])
def update_agent(agent_uuid: str, body: AgentUpdate):
    with _lock:
        agents = _agents()
        a = _agent_or_404(agents, agent_uuid)
        a.update(body.model_dump(exclude_none=True))
        _write(AGENTS_FILE, agents)
    return a


@router.delete("/agents/{agent_uuid}", status_code=204, tags=["agents"])
def delete_agent(agent_uuid: str):
    with _lock:
        agents = _agents()
        _agent_or_404(agents, agent_uuid)
        del agents[agent_uuid]
        _write(AGENTS_FILE, agents)
    return Response(status_code=204)


# ---------- Bot API ----------

@router.get("/bot-api/ping", response_model=BotApiPingResult, tags=["bot-api"])
def ping():
    agents = [a for a in _agents().values() if a["enabled"]]
    tasks = _tasks()
    now = time.time()
    pending = {t["task_uuid"] for a in agents for t in _pending_for(a["uuid"], tasks, now)}
    return {"ok": True, "version": VERSION, "server_time": now,
            "agents_enabled": len(agents), "tasks_pending": len(pending)}


@router.put("/bot-api/tasks-get", response_model=TaskOut, responses={204: {"description": "задач нет"}},
            tags=["bot-api"])
def tasks_get(body: TasksGetIn):
    now = time.time()
    with _lock:
        agents = _agents()
        a = _agent_or_404(agents, body.agent_uuid)
        if not a["enabled"]:
            raise HTTPException(status_code=403, detail="agent disabled")
        a["last_seen_at"] = now
        _write(AGENTS_FILE, agents)
        tasks = _tasks()
        pending = sorted(_pending_for(a["uuid"], tasks, now), key=lambda t: t["created_at"])
        if not pending:
            return Response(status_code=204)
        t = pending[0]
        t["taken"][a["uuid"]] = now
        _write(TASKS_FILE, tasks)
    return {"task_uuid": t["task_uuid"], "job_id": t["job_id"], "created_at": t["created_at"],
            "video_url": f"/bot-api/tasks/{t['task_uuid']}/video"}


@router.get("/bot-api/tasks/{task_uuid}/video", tags=["bot-api"])
def task_video(task_uuid: str):
    t = _task_or_404(_tasks(), task_uuid)
    path = config.UPLOAD_DIR / t["video"]
    if not path.exists():
        raise HTTPException(status_code=410, detail="video no longer stored")
    return FileResponse(path, filename=t["video"])


@router.post("/bot-api/task-result/{agent_uuid}", status_code=201, tags=["bot-api"])
def task_result(agent_uuid: str, body: FindingIn):
    with _lock:
        agents = _agents()
        a = _agent_or_404(agents, agent_uuid)
        tasks = _tasks()
        t = _task_or_404(tasks, body.task_uuid)
        finding = {"finding_uuid": uuid.uuid4().hex, "agent_uuid": agent_uuid, "created_at": time.time(),
                   **body.model_dump(exclude={"task_uuid"})}
        t["findings"].append(finding)
        a["findings"] = a.get("findings", 0) + 1
        a["last_seen_at"] = finding["created_at"]
        _write(TASKS_FILE, tasks)
        _write(AGENTS_FILE, agents)
    return {"finding_uuid": finding["finding_uuid"]}


@router.post("/bot-api/task-done/{task_uuid}", tags=["bot-api"])
def task_done(task_uuid: str, body: TaskDoneIn):
    with _lock:
        agents = _agents()
        a = _agent_or_404(agents, body.agent_uuid)
        tasks = _tasks()
        t = _task_or_404(tasks, task_uuid)
        if body.agent_uuid not in t["done_by"]:
            t["done_by"].append(body.agent_uuid)
            a["tasks_done"] = a.get("tasks_done", 0) + 1
        t["taken"].pop(body.agent_uuid, None)
        a["last_seen_at"] = time.time()
        _write(TASKS_FILE, tasks)
        _write(AGENTS_FILE, agents)
    enabled = {u for u, x in agents.items() if x["enabled"]}
    return {"task_uuid": task_uuid, "done_by": len(t["done_by"]),
            "all_enabled_agents_done": enabled <= set(t["done_by"])}
