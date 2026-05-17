"""Audit log persistente (JSON Lines) para trazabilidad de pipeline runs."""
from __future__ import annotations

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import settings


def _audit_path() -> Path:
    settings.ensure_dirs()
    audit_dir = settings.logs_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return audit_dir / f"audit_{today}.jsonl"


def audit_log(event: str, payload: dict[str, Any] | None = None) -> Path:
    """Append-only JSONL audit record. Returns the file path."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user": os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "host": platform.node(),
        "app_version": settings.app_version,
        "payload": payload or {},
    }
    path = _audit_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
