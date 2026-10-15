"""Append-only audit trail of every agent step, stored in output/audit_trail.json.

The file is a JSON list. Each new entry is appended and existing records are
always kept. If the file can't be parsed it is moved aside, never overwritten.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import AuditEntry

AUDIT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
MAX_FIELD_CHARS = 2000  # cap on logged args/results so the file stays readable

_lock = threading.Lock()


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= MAX_FIELD_CHARS else text[:MAX_FIELD_CHARS] + "...[truncated]"


def _load() -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    try:
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # Keep unreadable records instead of overwriting them.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    AUDIT_PATH.rename(AUDIT_PATH.with_name(f"audit_trail.unreadable-{stamp}.json"))
    return []


def log_step(
    run_id: str,
    agent: str,
    event: str,
    *,
    depth: int = 0,
    chain: list[str] | None = None,
    tool: str | None = None,
    args: Any = None,
    result: Any = None,
    dry_run: bool | None = None,
    usage: dict | None = None,
) -> None:
    entry = AuditEntry(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        run_id=run_id,
        agent=agent,
        event=event,
        depth=depth,
        chain=chain or [agent],
        tool=tool,
        args=None if args is None else _clip(args),
        result=None if result is None else _clip(result),
        dry_run=dry_run,
        usage=usage,
    )
    with _lock:
        records = _load()
        records.append(entry.model_dump())
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, AUDIT_PATH)
