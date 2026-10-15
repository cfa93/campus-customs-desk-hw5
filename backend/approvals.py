"""Queue of actions waiting for a human, stored in output/approvals.json.

Agents can only add requests here (via their BossPlan). Only the FastAPI
routes, acting for a person, can mark a request approved or rejected.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from models import Approval, ApprovalRequest

APPROVALS_PATH = Path(__file__).resolve().parent.parent / "output" / "approvals.json"
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> list[Approval]:
    if not APPROVALS_PATH.exists():
        return []
    return [Approval(**a) for a in json.loads(APPROVALS_PATH.read_text(encoding="utf-8") or "[]")]


def _save(items: list[Approval]) -> None:
    APPROVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = APPROVALS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps([a.model_dump() for a in items], indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, APPROVALS_PATH)


def list_approvals(status: str | None = None) -> list[Approval]:
    with _lock:
        items = _load()
    return [a for a in items if status is None or a.status == status]


def get_approval(approval_id: int) -> Approval | None:
    return next((a for a in list_approvals() if a.id == approval_id), None)


def add_requests(run_id: str, dry_run: bool, requests: list[ApprovalRequest]) -> list[Approval]:
    """Queue an agent run's approval requests. A request already pending for the same thing isn't duplicated."""
    created: list[Approval] = []
    with _lock:
        items = _load()
        for req in requests:
            duplicate = any(
                a.status == "pending" and a.kind == req.kind and a.ref_id == req.ref_id and a.ticket_id == req.ticket_id
                for a in items
            )
            if duplicate:
                continue
            approval = Approval(
                id=max((a.id for a in items), default=0) + 1,
                created_at=_now(),
                run_id=run_id,
                dry_run_request=dry_run,
                ticket_id=req.ticket_id,
                kind=req.kind,
                ref_id=req.ref_id,
                amount=req.amount,
                reason=req.reason,
            )
            items.append(approval)
            created.append(approval)
        _save(items)
    return created


def decide(approval_id: int, **changes) -> Approval:
    """Record a person's decision on a pending request."""
    with _lock:
        items = _load()
        for i, a in enumerate(items):
            if a.id == approval_id:
                items[i] = a.model_copy(update={**changes, "decided_at": _now()})
                _save(items)
                return items[i]
    raise KeyError(approval_id)


def void_pending(reason: str) -> int:
    """Mark every pending request voided (used after a database reset). Records are kept."""
    with _lock:
        items = _load()
        count = 0
        for i, a in enumerate(items):
            if a.status == "pending":
                items[i] = a.model_copy(update={"status": "voided", "decision_note": reason, "decided_at": _now()})
                count += 1
        _save(items)
    return count
