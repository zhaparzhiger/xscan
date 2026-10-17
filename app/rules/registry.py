"""Справочник нарушений и нормативных источников (app/rules/violations.yaml)."""
from functools import lru_cache

import yaml

from app import config

GENERIC = "generic"


@lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(config.RULES_FILE.read_text(encoding="utf-8"))


def violation(type_id: str) -> dict:
    kb = load()
    return kb["violations"].get(type_id) or kb["violations"][GENERIC]


def type_ids() -> list[str]:
    return list(load()["violations"].keys())


def rule_reference(type_id: str) -> dict:
    v = violation(type_id)
    doc = load()["documents"][v["document"]]
    return {
        "document": doc["title"],
        "clause": v.get("clause") if doc.get("verified") else None,
        "url": doc.get("url"),
        "verified": bool(doc.get("verified")),
    }


def describe(type_id: str, timecode: str) -> str:
    """Текст для поля description: что видно + почему + основание. Без утверждений, которых нет на видео."""
    v = violation(type_id)
    ref = rule_reference(type_id)
    basis = ref["document"] + (f", {ref['clause']}" if ref["clause"] else "")
    return (
        f"{timecode}: на видео {v['observed']}. "
        f"Это может указывать на нарушение: {v['why']}. "
        f"Основание: {basis}. Требуется проверка человеком."
    )
