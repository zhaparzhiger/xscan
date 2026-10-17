"""Схема ответа API — строго по разделу 10 ТЗ."""
from typing import Literal

from pydantic import BaseModel


class EvidenceFrame(BaseModel):
    timestamp_sec: float
    image_base64: str  # JPEG


class Violation(BaseModel):
    type: str
    timecode_sec: float
    description: str
    evidence_frames: list[EvidenceFrame]


class JobResult(BaseModel):
    job_id: str
    status: Literal["processing", "done", "failed"]
    verdict: Literal["violation", "no_violation"] | None = None
    violations: list[Violation] = []
    error: str | None = None


class AnalyzeResponse(BaseModel):
    job_id: str
    status: Literal["processing"] = "processing"
