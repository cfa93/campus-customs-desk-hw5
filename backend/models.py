"""Data types shared by the Campus Customs multi-agent backend.

Database rows come from the MCP server (mcp_server/server.py) as JSON, so the
backend only defines what agents return, how delegations are tracked, and
what the audit trail records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

TicketStatus = Literal["open", "in_progress", "escalated", "closed"]


# ---------------------------------------------------------------------------
# Agent outputs
# ---------------------------------------------------------------------------


class Fact(BaseModel):
    """One fact the agent relied on, with the table it came from."""

    statement: str = Field(description="The fact, with exact numbers from a tool result.")
    source_table: str = Field(description="Database table the fact came from, e.g. 'inventory'.")


class AgentReport(BaseModel):
    """What a specialist agent (inventory, accounting, facilities, customer_service) returns."""

    agent: AgentName
    answer: str = Field(description="Direct answer to the task that was delegated.")
    facts: list[Fact] = Field(default_factory=list, description="Facts used, each traceable to a table.")
    recommended_actions: list[str] = Field(default_factory=list)
    needs_human_approval: bool = Field(
        default=False, description="True if any recommended action moves money or changes a price."
    )
    approval_reason: str | None = None
    customer_message: str | None = Field(
        default=None, description="Draft message to the requester, if one is needed (customer_service)."
    )


class ApprovalRequest(BaseModel):
    """An action only a human can approve (payments, purchases, discounts)."""

    kind: Literal["invoice_payment", "rent_payment", "purchase", "price_override", "other"]
    ticket_id: int | None = None
    ref_id: int | None = Field(
        default=None, description="invoices.id (invoice_payment), leases.id (rent_payment) or vendors.id (purchase)."
    )
    amount: float | None = None
    reason: str


class TicketDecision(BaseModel):
    ticket_id: int
    owner: AgentName = Field(description="Agent responsible for this ticket.")
    new_status: TicketStatus
    decision: str = Field(description="What will happen with this ticket and why.")
    customer_message: str | None = None


class BossPlan(BaseModel):
    """What the Boss agent returns after coordinating the team."""

    summary: str
    decisions: list[TicketDecision] = Field(default_factory=list)
    approvals_needed: list[ApprovalRequest] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Delegation tracking and audit trail
# ---------------------------------------------------------------------------


class DelegationRecord(BaseModel):
    from_agent: AgentName
    to_agent: AgentName
    task: str
    depth: int
    result: str | None = None
    error: str | None = None


AuditEvent = Literal[
    "run_start",  # an agent loop begins (top-level run or delegated task)
    "model_response",  # the model answered: tool calls requested and/or text
    "tool_call",  # an MCP tool was called (args + result)
    "tool_blocked",  # a tool call was refused by a safety check
    "delegation",  # one agent handed a task to another
    "delegation_refused",  # a delegation hit a loop limit
    "run_end",  # an agent loop finished with its output
    "error",  # the loop failed (e.g. token limit reached)
    "approval_created",  # an agent's approval request was queued for a human
    "human_approved",  # a person approved a request (payment recorded if it moves money)
    "human_rejected",  # a person rejected a request
    "approval_failed",  # a person approved but the MCP server refused (e.g. balance would go negative)
    "database_reset",  # campus_customs_new.db restored from the original
    "ticket_resolved",  # a person marked a ticket resolved (status closed)
]


class AuditEntry(BaseModel):
    """One step in output/audit_trail.json."""

    timestamp: str = Field(description="Real UTC time the step happened.")
    run_id: str = Field(description="Shared by every step of one top-level run.")
    agent: str
    event: AuditEvent
    depth: int = 0
    chain: list[str] = Field(default_factory=list)
    tool: str | None = None
    args: Any = None
    result: Any = None
    dry_run: bool | None = None
    usage: dict | None = None


# ---------------------------------------------------------------------------
# Human approval queue and API bodies
# ---------------------------------------------------------------------------

ApprovalStatus = Literal["pending", "approved", "rejected", "failed", "voided"]

# Which approval kinds move money, and the payments.kind they are recorded as.
PAYMENT_KIND_FOR: dict[str, str] = {"invoice_payment": "invoice", "rent_payment": "lease", "purchase": "purchase"}


class Approval(BaseModel):
    """An agent's request waiting for (or decided by) a person."""

    id: int
    created_at: str
    run_id: str
    dry_run_request: bool = Field(description="True if the agent run that asked for it was a dry run.")
    ticket_id: int | None = None
    kind: str
    ref_id: int | None = None
    amount: float | None = None
    reason: str
    status: ApprovalStatus = "pending"
    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None
    payment: dict | None = None
    error: str | None = None


class RunTicketRequest(BaseModel):
    apply: bool = Field(default=False, description="Write the Boss's ticket status update. Default is a dry run.")


class ApproveRequest(BaseModel):
    approved_by: str = Field(min_length=2, description="Name of the person approving. Agents can't approve.")
    amount: float | None = Field(default=None, gt=0, description="Override the amount (purchases / price overrides only).")
    note: str | None = None


class ResolveRequest(BaseModel):
    resolved_by: str = Field(min_length=2, description="Name of the person marking the ticket resolved.")
    note: str | None = None


class RejectRequest(BaseModel):
    rejected_by: str = Field(min_length=2)
    reason: str = Field(min_length=2)


@dataclass
class ShopDeps:
    """Run context shared across all agents in one top-level run.

    depth and chain describe the current position in the delegation tree.
    trace is the same list object for every agent in the run, so its length is
    the total number of delegations made so far.
    """

    run_id: str = ""
    dry_run: bool = True
    depth: int = 0
    chain: list[AgentName] = field(default_factory=list)
    trace: list[DelegationRecord] = field(default_factory=list)

    @property
    def agent(self) -> AgentName:
        return self.chain[-1]
