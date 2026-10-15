"""Campus Customs desk API (FastAPI).

Every database read and write goes through the campus-customs MCP server,
the same one the agents use. This API holds its own MCP client for the
human-only tools (record_payment, reset_database) that agents never get.

Money rules:
- Agents can only *request* payments/purchases (BossPlan.approvals_needed).
  Requests are queued in output/approvals.json.
- Only POST /approvals/{id}/approve, called for a named person, records a
  payment. The MCP server checks the amount against the database and refuses
  anything that would take the balance below zero.

Run:
    uvicorn main:app --app-dir backend --reload
    (docs at http://127.0.0.1:8000/docs)
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

import approvals
from agents import MCP_SERVER_PATH, ROOT, new_run_id, run_shop, ticket_task
from audit import AUDIT_PATH, log_step
from models import (
    AGENT_NAMES,
    PAYMENT_KIND_FOR,
    ApproveRequest,
    DelegationRecord,
    RejectRequest,
    ResolveRequest,
    RunTicketRequest,
)

# Names that can never count as the human approver.
NON_HUMAN_NAMES = {*AGENT_NAMES, "customer service", "agent", "ai", "bot", "system", "assistant", "gpt-6-luna"}

mcp_client: Client | None = None
agent_run_lock = asyncio.Lock()  # one agent run at a time keeps the shared cash picture consistent


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_client
    transport = PythonStdioTransport(MCP_SERVER_PATH, python_cmd=sys.executable, cwd=str(ROOT))
    async with Client(transport) as client:
        mcp_client = client
        yield
    mcp_client = None


app = FastAPI(title="Campus Customs Desk API", version="1.0", lifespan=lifespan)
# The React dashboard (frontend/, Vite dev server) calls this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Background agent runs started from the dashboard, by run_id (in memory; lost on restart,
# but every step is also in output/audit_trail.json).
runs: dict[str, dict[str, Any]] = {}
_background_tasks: set[asyncio.Task] = set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def mcp(tool: str, args: dict[str, Any] | None = None) -> Any:
    """Call an MCP tool and turn its {'error': ...} replies into HTTP errors."""
    result = await mcp_client.call_tool(tool, args or {}, raise_on_error=False)
    if result.is_error:
        raise HTTPException(502, f"MCP tool {tool} failed: {result.content}")
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]  # list-returning tools are wrapped by FastMCP
    if isinstance(data, dict) and "error" in data:
        message = data["error"]
        raise HTTPException(404 if "not found" in message.lower() else 400, message)
    return data


def api_run_id() -> str:
    return "api-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def require_human(name: str) -> str:
    name = name.strip()
    if name.lower() in NON_HUMAN_NAMES:
        raise HTTPException(403, f"'{name}' is an agent or system name. Only a person can approve or reject.")
    return name


async def append_ticket_note(ticket_id: int | None, note: str) -> None:
    """Add a note to a ticket without changing its status (written for real, not a dry run)."""
    if ticket_id is None:
        return
    ticket = await mcp("get_ticket", {"ticket_id": ticket_id})
    await mcp("update_ticket", {"ticket_id": ticket_id, "status": ticket["status"], "note": note, "dry_run": False})


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


@app.get("/tickets")
async def get_tickets():
    """All tickets with their current status."""
    tickets = await mcp("list_tickets")
    desk = await mcp("get_desk")
    return {
        "desk_date": desk["date_today"],
        "count": len(tickets),
        "tickets": [
            {k: t[k] for k in ("id", "type", "requester", "subject", "status", "notes", "created_at")} for t in tickets
        ],
    }


@app.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: int):
    """One ticket with every record it links to (stock, pricing, invoice, lease, cash)."""
    return await mcp("get_ticket_context", {"ticket_id": ticket_id})


@app.post("/tickets/{ticket_id}/run")
async def run_ticket(ticket_id: int, body: RunTicketRequest | None = None):
    """Run the agent team (starting with the Boss) on one ticket.

    Default is a dry run: the Boss's status update is previewed, not written.
    Any payments/purchases the agents want are queued for human approval.
    Nothing here can record a payment.
    """
    body = body or RunTicketRequest()
    await mcp("get_ticket", {"ticket_id": ticket_id})  # 404 if it doesn't exist
    if agent_run_lock.locked():
        raise HTTPException(409, "An agent run is already in progress. Try again when it finishes.")
    async with agent_run_lock:
        try:
            run_id, plan, trace, usage = await run_shop(ticket_task(ticket_id), "boss", dry_run=not body.apply)
        except Exception as exc:
            raise HTTPException(500, f"Agent run failed: {type(exc).__name__}: {exc}") from exc

    queued = approvals.add_requests(run_id, not body.apply, plan.approvals_needed)
    for a in queued:
        log_step(run_id, "boss", "approval_created", chain=["boss"], args=a.model_dump(), result="waiting for a human")
    return {
        "run_id": run_id,
        "ticket_id": ticket_id,
        "dry_run": not body.apply,
        "plan": plan.model_dump(),
        "delegations": [{"from": r.from_agent, "to": r.to_agent, "depth": r.depth, "task": r.task} for r in trace],
        "approvals_queued": [a.model_dump() for a in queued],
        "usage": {"requests": usage.requests, "tool_calls": usage.tool_calls, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
    }


@app.post("/tickets/{ticket_id}/runs", status_code=202)
async def start_run(ticket_id: int, body: RunTicketRequest | None = None):
    """Start the agent team on one ticket in the background and return its run_id right away.

    Follow it with GET /runs/{run_id} (status, delegations, per-agent summaries)
    and GET /activity?run_id=... (each step as it happens).
    """
    body = body or RunTicketRequest()
    await mcp("get_ticket", {"ticket_id": ticket_id})
    if agent_run_lock.locked():
        raise HTTPException(409, "An agent run is already in progress. Try again when it finishes.")
    await agent_run_lock.acquire()  # held until the background run ends

    run_id = new_run_id()
    trace: list[DelegationRecord] = []
    runs[run_id] = {
        "run_id": run_id,
        "ticket_id": ticket_id,
        "status": "running",
        "dry_run": not body.apply,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finished_at": None,
        "trace": trace,
        "plan": None,
        "usage": None,
        "approvals_queued": [],
        "error": None,
    }

    async def work() -> None:
        state = runs[run_id]
        try:
            _, plan, _, usage = await run_shop(ticket_task(ticket_id), "boss", dry_run=not body.apply, run_id=run_id, trace=trace)
            queued = approvals.add_requests(run_id, not body.apply, plan.approvals_needed)
            for a in queued:
                log_step(run_id, "boss", "approval_created", chain=["boss"], args=a.model_dump(), result="waiting for a human")
            state.update(
                status="completed",
                plan=plan.model_dump(),
                usage={"requests": usage.requests, "tool_calls": usage.tool_calls, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
                approvals_queued=[a.model_dump() for a in queued],
            )
        except Exception as exc:
            state.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            state["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            agent_run_lock.release()

    task = asyncio.create_task(work())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"run_id": run_id, "ticket_id": ticket_id, "status": "running", "dry_run": not body.apply}


def _read_audit(run_id: str | None = None) -> list[dict]:
    entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8")) if AUDIT_PATH.exists() else []
    return [e for e in entries if run_id is None or e["run_id"] == run_id]


def _agent_summaries(run_id: str, trace: list[DelegationRecord], plan: dict | None) -> list[dict]:
    """What each agent did in a run: tasks received, answers, tools used, who it asked."""
    entries = _read_audit(run_id)
    summaries = []
    for name in AGENT_NAMES:
        mine = [e for e in entries if e["agent"] == name]
        if not mine:
            continue
        starts = sum(e["event"] == "run_start" for e in mine)
        ends = sum(e["event"] in ("run_end", "error") for e in mine)
        tool_counts: dict[str, int] = {}
        for e in mine:
            if e["event"] == "tool_call":
                tool_counts[e["tool"]] = tool_counts.get(e["tool"], 0) + 1
        tasks = []
        for r in trace:
            if r.to_agent != name:
                continue
            report = None
            if r.result:
                try:
                    report = json.loads(r.result)
                except json.JSONDecodeError:
                    report = {"answer": r.result}
            tasks.append({"from": r.from_agent, "task": r.task, "depth": r.depth, "report": report, "error": r.error})
        summaries.append({
            "agent": name,
            "status": "working" if starts > ends else "done",
            "model_responses": sum(e["event"] == "model_response" for e in mine),
            "tools": [{"tool": t, "count": c} for t, c in tool_counts.items()],
            "asked": [{"to": r.to_agent, "task": r.task} for r in trace if r.from_agent == name],
            "tasks": tasks,
            "plan": plan if name == "boss" else None,
        })
    return summaries


@app.get("/runs")
async def list_runs(ticket_id: int | None = None):
    """Runs started from the dashboard since the server started, newest first."""
    items = [r for r in runs.values() if ticket_id is None or r["ticket_id"] == ticket_id]
    items.sort(key=lambda r: r["started_at"], reverse=True)
    return {"runs": [{k: r[k] for k in ("run_id", "ticket_id", "status", "dry_run", "started_at", "finished_at", "error")} for r in items]}


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Live status of a background run: delegations so far, each agent's summary, and the final plan."""
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found (runs are kept in memory until the server restarts).")
    trace: list[DelegationRecord] = run["trace"]
    return {
        **{k: v for k, v in run.items() if k != "trace"},
        "delegations": [{"from": r.from_agent, "to": r.to_agent, "depth": r.depth, "task": r.task, "done": r.result is not None or r.error is not None} for r in trace],
        "agents": _agent_summaries(run_id, trace, run["plan"]),
    }


@app.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int, body: ResolveRequest):
    """A person marks a ticket resolved (status 'closed'). Refused while it still has pending approvals."""
    person = require_human(body.resolved_by)
    ticket = await mcp("get_ticket", {"ticket_id": ticket_id})
    pending = [a for a in approvals.list_approvals("pending") if a.ticket_id == ticket_id]
    if pending:
        raise HTTPException(409, f"Ticket {ticket_id} still has {len(pending)} pending approval(s). Approve or reject them first.")
    if ticket["status"] == "closed":
        return {"ticket": ticket, "message": "Already resolved."}
    note = f"Resolved by {person}" + (f": {body.note}" if body.note else ".")
    result = await mcp("update_ticket", {"ticket_id": ticket_id, "status": "closed", "note": note, "dry_run": False})
    log_step(api_run_id(), "human", "ticket_resolved", chain=["human"], args={"ticket_id": ticket_id, "by": person}, result=note)
    return {"ticket": result["ticket"]}


# ---------------------------------------------------------------------------
# Agent activity (from the audit trail)
# ---------------------------------------------------------------------------


@app.get("/activity")
async def get_activity(
    limit: int = Query(50, ge=1, le=500),
    run_id: str | None = None,
    agent: str | None = None,
):
    """Recent agent steps, newest first: messages, tools used, delegations and approvals."""
    entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8")) if AUDIT_PATH.exists() else []
    if run_id:
        entries = [e for e in entries if e["run_id"] == run_id]
    if agent:
        entries = [e for e in entries if e["agent"] == agent]
    recent = entries[-limit:][::-1]

    def parse(text: Any) -> dict:
        """Logged results are JSON text, possibly cut off at the audit size cap."""
        if not isinstance(text, str):
            return text if isinstance(text, dict) else {}
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {"answer": text}

    def view(e: dict) -> dict:
        item = {k: e[k] for k in ("timestamp", "run_id", "agent", "event", "depth")}
        if e["event"] == "model_response":
            result = parse(e["result"])
            item["message"] = result.get("text")
            item["tools_requested"] = [c.get("tool") for c in result.get("tool_calls", [])]
        elif e["event"] in ("tool_call", "tool_blocked"):
            item["tool"] = e["tool"]
            item["args"] = e["args"]
            item["result"] = (e["result"] or "")[:300] if isinstance(e["result"], str) else e["result"]
        elif e["event"] in ("delegation", "delegation_refused"):
            item["to"] = (e["tool"] or "").removeprefix("ask_")
            item["message"] = e["args"]
        elif e["event"] == "run_end":
            output = parse(e["result"])
            item["message"] = output.get("answer") or output.get("summary")
            item["usage"] = e.get("usage")
        else:
            item["message"] = e["result"] if isinstance(e["result"], str) else e["args"]
        return item

    runs = list(dict.fromkeys(e["run_id"] for e in reversed(entries)))[:10]
    return {"count": len(recent), "recent_run_ids": runs, "activity": [view(e) for e in recent]}


# ---------------------------------------------------------------------------
# Human approvals (the only path that moves money)
# ---------------------------------------------------------------------------


@app.get("/approvals")
async def get_approvals(status: str | None = Query(None, pattern="^(pending|approved|rejected|failed|voided)$")):
    """Requests from agents, e.g. ?status=pending for what's waiting on a person."""
    return {"approvals": [a.model_dump() for a in approvals.list_approvals(status)]}


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: ApproveRequest):
    """A person approves a request. For payments/purchases this records the payment through MCP.

    The MCP server re-checks the amount against the invoice/lease and refuses
    anything that would make the cash balance negative.
    """
    person = require_human(body.approved_by)
    approval = approvals.get_approval(approval_id)
    if approval is None:
        raise HTTPException(404, f"Approval {approval_id} not found.")
    if approval.status != "pending":
        raise HTTPException(409, f"Approval {approval_id} is already {approval.status}.")

    run_id = api_run_id()
    payment_kind = PAYMENT_KIND_FOR.get(approval.kind)
    if payment_kind is None:
        # price_override / other: no money moves; record the decision on the ticket.
        decided = approvals.decide(approval_id, status="approved", decided_by=person, decision_note=body.note,
                                   amount=body.amount or approval.amount)
        await append_ticket_note(approval.ticket_id, f"Human approval #{approval_id} ({approval.kind}) by {person}"
                                 + (f" at ${decided.amount:,.2f}" if decided.amount else "") + (f": {body.note}" if body.note else "."))
        log_step(run_id, "human", "human_approved", chain=["human"], args={"approval_id": approval_id, "by": person}, result=decided.model_dump())
        return {"approval": decided.model_dump(), "payment": None}

    if approval.ref_id is None:
        raise HTTPException(400, f"Approval {approval_id} has no invoice/lease/vendor id, so no payment can be recorded.")
    # Invoice and rent amounts come from the agent's request and are re-checked by MCP; a person may set the purchase amount.
    amount = body.amount if (body.amount and approval.kind == "purchase") else approval.amount
    if amount is None:
        raise HTTPException(400, "No amount on this request. Provide one in the body.")
    try:
        result = await mcp("record_payment", {"kind": payment_kind, "ref_id": approval.ref_id, "amount": amount, "approved_by": person})
    except HTTPException as exc:
        failed = approvals.decide(approval_id, status="failed", decided_by=person, error=exc.detail)
        log_step(run_id, "human", "approval_failed", chain=["human"], args={"approval_id": approval_id, "by": person, "amount": amount}, result=exc.detail)
        raise HTTPException(exc.status_code, {"message": exc.detail, "approval": failed.model_dump()}) from exc

    decided = approvals.decide(approval_id, status="approved", decided_by=person, decision_note=body.note,
                               amount=amount, payment=result["payment"])
    await append_ticket_note(approval.ticket_id, f"Human approval #{approval_id} by {person}: paid ${amount:,.2f} "
                             f"({payment_kind} {approval.ref_id}); checking now ${result['new_balance']:,.2f}.")
    log_step(run_id, "human", "human_approved", chain=["human"], args={"approval_id": approval_id, "by": person}, result=result)
    return {"approval": decided.model_dump(), "payment": result["payment"], "checking_balance": result["new_balance"]}


@app.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: RejectRequest):
    """A person rejects a request. Nothing is paid."""
    person = require_human(body.rejected_by)
    approval = approvals.get_approval(approval_id)
    if approval is None:
        raise HTTPException(404, f"Approval {approval_id} not found.")
    if approval.status != "pending":
        raise HTTPException(409, f"Approval {approval_id} is already {approval.status}.")
    decided = approvals.decide(approval_id, status="rejected", decided_by=person, decision_note=body.reason)
    await append_ticket_note(approval.ticket_id, f"Human rejected request #{approval_id} ({approval.kind}) - {person}: {body.reason}")
    log_step(api_run_id(), "human", "human_rejected", chain=["human"], args={"approval_id": approval_id, "by": person}, result=body.reason)
    return {"approval": decided.model_dump()}


# ---------------------------------------------------------------------------
# Cash and reset
# ---------------------------------------------------------------------------


@app.get("/cash")
async def get_cash():
    """Current checking balance (from the database), plus what's owed against it."""
    position = await mcp("get_cash_position")
    checking = next((a for a in position["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account in the database.")
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "desk_date": position["desk_date"],
        "open_invoices_total": position["open_invoices_total"],
        "rent_total": position["rent_total"],
        "after_all_obligations": position["cash_after_all_obligations"],
    }


@app.post("/reset")
async def reset():
    """Restore campus_customs_new.db to the original values. The original file is never changed.

    Pending approvals are voided (kept on record). The audit trail is kept.
    """
    if agent_run_lock.locked():
        raise HTTPException(409, "An agent run is in progress. Reset after it finishes.")
    result = await mcp("reset_database")
    voided = approvals.void_pending("Database was reset to original values.")
    log_step(api_run_id(), "human", "database_reset", chain=["human"], result={**result, "approvals_voided": voided})
    return {**result, "approvals_voided": voided}


@app.get("/")
async def root():
    return {"service": "Campus Customs Desk API", "docs": "/docs"}
