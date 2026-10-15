"""Campus Customs MCP server.

The only way the agents reach the database. Exposes ticket-handling tools over
the working database data/campus_customs_new.db. The original
data/campus_customs.db is never touched.

Human-only tools: record_payment and reset_database are called only by the
FastAPI backend (backend/main.py) after a person acts. They are never given to
any agent. There is no tool that changes prices, changes inventory or contacts
anyone outside the shop; messages are drafts for a human to send.
"""

import calendar
import sqlite3
from datetime import date
from pathlib import Path

from fastmcp import FastMCP

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "campus_customs_new.db"
ORIGINAL_DB_PATH = DATA_DIR / "campus_customs.db"  # read-only source for reset_database

# Workflow states an agent may move a ticket into.
ALLOWED_STATUSES = {"open", "in_progress", "escalated", "closed"}

# Names that are agents or automation, never a human approver.
NON_HUMAN_APPROVERS = {
    "boss", "inventory", "accounting", "facilities", "customer_service", "customer service",
    "agent", "ai", "bot", "system", "assistant", "gpt-6-luna",
}
PAYMENT_KINDS = {"invoice", "lease", "purchase"}

mcp = FastMCP("campus-customs")


def _connect(read_only: bool = True) -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    mode = "ro" if read_only else "rw"
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode={mode}", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _row(cur: sqlite3.Cursor) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


def _rows(cur: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _desk_date(con: sqlite3.Connection) -> str | None:
    desk = _row(con.execute("SELECT date_today FROM desk LIMIT 1"))
    return desk["date_today"] if desk else None


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


# ---------------------------------------------------------------------------
# Desk and tickets
# ---------------------------------------------------------------------------


@mcp.tool
def get_desk() -> dict:
    """Today's shop date (desk.date_today) and desk notes. Use this date, never the system clock."""
    with _connect() as con:
        return _row(con.execute("SELECT date_today, notes FROM desk LIMIT 1")) or {"error": "desk table is empty"}


@mcp.tool
def list_open_tickets() -> dict:
    """List all tickets with status 'open', oldest first, plus the desk date.

    Use this first to see the work queue. Use desk_date (not the system clock)
    to judge what is due or overdue.
    """
    with _connect() as con:
        tickets = _rows(con.execute("SELECT * FROM tickets WHERE status = 'open' ORDER BY created_at"))
        return {"desk_date": _desk_date(con), "count": len(tickets), "tickets": tickets}


@mcp.tool
def list_tickets() -> list[dict]:
    """Every ticket (any status), by id."""
    with _connect() as con:
        return _rows(con.execute("SELECT * FROM tickets ORDER BY id"))


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """One ticket by id (all fields)."""
    with _connect() as con:
        ticket = _row(con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)))
    return ticket or {"error": f"Ticket {ticket_id} not found."}


@mcp.tool
def get_ticket_context(ticket_id: int) -> dict:
    """Return a ticket with every database record it connects to.

    Includes, when relevant: inventory for the requested SKU/size and all sizes
    of that SKU, pricing, the linked invoice and its vendor, the linked lease,
    cash account balances, existing payments for the linked invoice/lease, and
    the desk date. Missing links are reported in 'warnings' rather than guessed.
    """
    with _connect() as con:
        ticket = _row(con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)))
        if ticket is None:
            return {"error": f"Ticket {ticket_id} not found."}

        desk = _row(con.execute("SELECT date_today, notes FROM desk LIMIT 1"))
        context: dict = {
            "ticket": ticket,
            "desk_date": desk["date_today"] if desk else None,
            "cash_accounts": _rows(con.execute("SELECT * FROM cash_accounts")),
        }
        warnings: list[str] = []

        if ticket["sku"]:
            sku, size = ticket["sku"], ticket["size"]
            all_sizes = _rows(con.execute("SELECT * FROM inventory WHERE sku = ? ORDER BY rowid", (sku,)))
            requested = next((r for r in all_sizes if r["size"] == size), None)
            context["inventory_requested_size"] = requested
            context["inventory_all_sizes"] = all_sizes
            context["pricing"] = _row(con.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)))
            if not all_sizes:
                warnings.append(f"SKU {sku} not found in inventory.")
            elif requested is None:
                warnings.append(f"Size {size} not found in inventory for SKU {sku}.")
            elif ticket["qty"] is not None and requested["qty"] < ticket["qty"]:
                warnings.append(
                    f"Insufficient stock: requested {ticket['qty']}, "
                    f"available {requested['qty']} ({sku} {size})."
                )
            if context["pricing"] is None:
                warnings.append(f"No pricing row for SKU {sku}.")

        if ticket["invoice_id"] is not None:
            invoice = _row(con.execute("SELECT * FROM invoices WHERE id = ?", (ticket["invoice_id"],)))
            context["invoice"] = invoice
            if invoice is None:
                warnings.append(f"Invoice {ticket['invoice_id']} not found.")
            else:
                context["vendor"] = _row(con.execute("SELECT * FROM vendors WHERE id = ?", (invoice["vendor_id"],)))
                if context["vendor"] is None:
                    warnings.append(f"Vendor {invoice['vendor_id']} not found.")
                if desk and invoice["status"] == "open" and invoice["due_date"] < desk["date_today"]:
                    warnings.append(
                        f"Invoice {invoice['id']} is overdue "
                        f"(due {invoice['due_date']}, today {desk['date_today']})."
                    )
                context["invoice_payments"] = _rows(
                    con.execute("SELECT * FROM payments WHERE kind = 'invoice' AND ref_id = ?", (invoice["id"],))
                )

        if ticket["lease_id"] is not None:
            lease = _row(con.execute("SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)))
            context["lease"] = lease
            if lease is None:
                warnings.append(f"Lease {ticket['lease_id']} not found.")
            else:
                if lease["landlord"] != ticket["requester"]:
                    warnings.append(
                        f"Requester '{ticket['requester']}' does not match lease landlord '{lease['landlord']}'."
                    )
                context["lease_payments"] = _rows(
                    con.execute("SELECT * FROM payments WHERE kind = 'lease' AND ref_id = ?", (lease["id"],))
                )

        context["warnings"] = warnings
    return context


@mcp.tool
def update_ticket(ticket_id: int, status: str, note: str, dry_run: bool = False) -> dict:
    """Change a ticket's status and append a note explaining the decision.

    status must be one of: open, in_progress, escalated, closed.
    The note is appended to the existing notes (existing text is kept).
    With dry_run=true nothing is written and the would-be result is returned.
    This tool does not move money or change inventory.
    """
    if status not in ALLOWED_STATUSES:
        return {"error": f"Invalid status '{status}'. Allowed: {sorted(ALLOWED_STATUSES)}"}
    if not note.strip():
        return {"error": "A note explaining the update is required."}

    with _connect(read_only=dry_run) as con:
        ticket = _row(con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)))
        if ticket is None:
            return {"error": f"Ticket {ticket_id} not found."}
        stamp = _desk_date(con) or "unknown date"
        new_notes = f"{ticket['notes'] or ''}\n[{stamp}] {note.strip()}".strip()
        if dry_run:
            return {"dry_run": True, "previous_status": ticket["status"], "ticket": {**ticket, "status": status, "notes": new_notes}}
        con.execute("UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, new_notes, ticket_id))
        updated = _row(con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)))
    return {"dry_run": False, "previous_status": ticket["status"], "ticket": updated}


# ---------------------------------------------------------------------------
# Inventory and vendors
# ---------------------------------------------------------------------------


@mcp.tool
def check_stock(sku: str, size: str, requested_qty: int | None = None) -> dict:
    """Stock for one SKU and size compared with requested_qty, plus every other size of the SKU."""
    with _connect() as con:
        rows = _rows(con.execute("SELECT * FROM inventory WHERE sku = ? ORDER BY rowid", (sku,)))
    item = next((r for r in rows if r["size"] == size), None)
    available = item["qty"] if item else 0
    return {
        "sku": sku,
        "size": size,
        "found": item is not None,
        "item": item,
        "requested_qty": requested_qty,
        "available_qty": available,
        "enough_stock": item is not None and requested_qty is not None and available >= requested_qty,
        "shortfall": max((requested_qty or 0) - available, 0),
        "other_sizes": [r for r in rows if r["size"] != size],
    }


@mcp.tool
def list_inventory(sku: str | None = None) -> list[dict]:
    """All inventory rows, or only the rows for one SKU."""
    with _connect() as con:
        if sku:
            return _rows(con.execute("SELECT * FROM inventory WHERE sku = ? ORDER BY rowid", (sku,)))
        return _rows(con.execute("SELECT * FROM inventory ORDER BY rowid"))


@mcp.tool
def list_vendors() -> list[dict]:
    """All vendors with their specialty and restock lead time in days (lead_days)."""
    with _connect() as con:
        return _rows(con.execute("SELECT * FROM vendors ORDER BY id"))


# ---------------------------------------------------------------------------
# Pricing, invoices, payments, cash
# ---------------------------------------------------------------------------


@mcp.tool
def get_pricing(sku: str) -> dict:
    """List price and unit cost for one SKU."""
    with _connect() as con:
        row = _row(con.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)))
    return row or {"error": f"No pricing row for SKU {sku}."}


@mcp.tool
def check_invoice(invoice_id: int) -> dict:
    """An invoice with its vendor, payments already recorded, and whether it is overdue (by desk date)."""
    with _connect() as con:
        invoice = _row(con.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)))
        if invoice is None:
            return {"found": False, "error": f"Invoice {invoice_id} not found."}
        vendor = _row(con.execute("SELECT * FROM vendors WHERE id = ?", (invoice["vendor_id"],)))
        payments = _rows(con.execute("SELECT * FROM payments WHERE kind = 'invoice' AND ref_id = ?", (invoice_id,)))
        today = _desk_date(con)
    late = _days_between(invoice["due_date"], today)
    is_open = invoice["status"] == "open"
    return {
        "found": True,
        "desk_date": today,
        "invoice": invoice,
        "vendor": vendor,
        "payments": payments,
        "amount_paid": sum(p["amount"] for p in payments),
        "overdue": is_open and late > 0,
        "days_overdue": max(late, 0) if is_open else 0,
    }


@mcp.tool
def list_invoices(status: str | None = None) -> list[dict]:
    """All invoices, or only those with the given status (e.g. 'open'), by due date."""
    with _connect() as con:
        if status:
            return _rows(con.execute("SELECT * FROM invoices WHERE status = ? ORDER BY due_date", (status,)))
        return _rows(con.execute("SELECT * FROM invoices ORDER BY due_date"))


@mcp.tool
def list_payments() -> list[dict]:
    """Every payment already recorded."""
    with _connect() as con:
        return _rows(con.execute("SELECT * FROM payments ORDER BY paid_at"))


@mcp.tool
def get_cash_position() -> dict:
    """Cash balances compared with all open invoices and the next rent on every lease."""
    with _connect() as con:
        accounts = _rows(con.execute("SELECT * FROM cash_accounts"))
        invoices = _rows(con.execute("SELECT * FROM invoices WHERE status = 'open' ORDER BY due_date"))
        leases = _rows(con.execute("SELECT * FROM leases ORDER BY id"))
        today = _desk_date(con)
    total_cash = sum(a["balance"] for a in accounts)
    inv_total = sum(i["amount"] for i in invoices)
    rent_total = sum(l["monthly_rent"] for l in leases)
    return {
        "desk_date": today,
        "accounts": accounts,
        "total_cash": total_cash,
        "open_invoices": invoices,
        "open_invoices_total": inv_total,
        "leases": leases,
        "rent_total": rent_total,
        "cash_after_all_obligations": total_cash - inv_total - rent_total,
    }


# ---------------------------------------------------------------------------
# Leases
# ---------------------------------------------------------------------------


@mcp.tool
def list_leases() -> list[dict]:
    """All leases with landlord, monthly rent and next due date."""
    with _connect() as con:
        return _rows(con.execute("SELECT * FROM leases ORDER BY id"))


@mcp.tool
def check_lease(lease_id: int) -> dict:
    """One lease with rent payments already recorded and days until rent is due (by desk date)."""
    with _connect() as con:
        lease = _row(con.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)))
        if lease is None:
            return {"found": False, "error": f"Lease {lease_id} not found."}
        payments = _rows(con.execute("SELECT * FROM payments WHERE kind = 'lease' AND ref_id = ?", (lease_id,)))
        today = _desk_date(con)
    return {
        "found": True,
        "desk_date": today,
        "lease": lease,
        "payments": payments,
        "days_until_due": _days_between(today, lease["next_due"]),
    }


# ---------------------------------------------------------------------------
# Human-only (called by the FastAPI backend, never by agents)
# ---------------------------------------------------------------------------


def _add_month(d: str) -> str:
    day = date.fromisoformat(d)
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])).isoformat()


@mcp.tool
def record_payment(kind: str, ref_id: int, amount: float, approved_by: str, account: str = "checking") -> dict:
    """HUMAN-ONLY. Record a payment a person has approved and take it out of cash.

    kind: 'invoice' (ref_id = invoices.id), 'lease' (ref_id = leases.id) or
    'purchase' (ref_id = vendors.id). Refused if approved_by is not a person,
    the amount doesn't match the record, the bill is already paid, or the
    account balance would go below zero. Everything happens in one transaction.
    """
    approver = approved_by.strip()
    if not approver or approver.lower() in NON_HUMAN_APPROVERS:
        return {"error": f"approved_by must be a human's name, not '{approved_by}'."}
    if kind not in PAYMENT_KINDS:
        return {"error": f"Invalid kind '{kind}'. Allowed: {sorted(PAYMENT_KINDS)}"}
    amount = round(float(amount), 2)
    if amount <= 0:
        return {"error": "Amount must be greater than zero."}

    con = _connect(read_only=False)
    try:
        con.execute("BEGIN IMMEDIATE")  # lock so balance check and debit can't interleave
        cash = _row(con.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)))
        if cash is None:
            raise ValueError(f"Cash account '{account}' not found.")
        today = _desk_date(con)

        if kind == "invoice":
            invoice = _row(con.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)))
            if invoice is None:
                raise ValueError(f"Invoice {ref_id} not found.")
            if invoice["status"] != "open":
                raise ValueError(f"Invoice {ref_id} is '{invoice['status']}', not open.")
            paid = con.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE kind = 'invoice' AND ref_id = ?", (ref_id,)).fetchone()[0]
            remaining = round(invoice["amount"] - paid, 2)
            if amount > remaining:
                raise ValueError(f"Amount ${amount:,.2f} is more than the ${remaining:,.2f} still owed on invoice {ref_id}.")
        elif kind == "lease":
            lease = _row(con.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)))
            if lease is None:
                raise ValueError(f"Lease {ref_id} not found.")
            if amount != round(lease["monthly_rent"], 2):
                raise ValueError(f"Rent for lease {ref_id} is ${lease['monthly_rent']:,.2f}, not ${amount:,.2f}.")
        else:
            if _row(con.execute("SELECT id FROM vendors WHERE id = ?", (ref_id,))) is None:
                raise ValueError(f"Vendor {ref_id} not found.")

        new_balance = round(cash["balance"] - amount, 2)
        if new_balance < 0:
            raise ValueError(
                f"Refused: paying ${amount:,.2f} would take {account} from ${cash['balance']:,.2f} to ${new_balance:,.2f}. Balance can't go negative."
            )

        cur = con.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, amount, account, today, approver),
        )
        con.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))
        if kind == "invoice" and amount == remaining:
            con.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
        if kind == "lease":
            con.execute("UPDATE leases SET next_due = ? WHERE id = ?", (_add_month(lease["next_due"]), ref_id))
        con.commit()
        payment = _row(con.execute("SELECT * FROM payments WHERE id = ?", (cur.lastrowid,)))
        return {"ok": True, "payment": payment, "account": account, "previous_balance": cash["balance"], "new_balance": new_balance}
    except ValueError as exc:
        con.rollback()
        return {"error": str(exc)}
    finally:
        con.close()


@mcp.tool
def reset_database() -> dict:
    """HUMAN-ONLY. Restore campus_customs_new.db to the original campus_customs.db values.

    The original is opened read-only and copied with SQLite's backup API, so it is never changed.
    """
    if not ORIGINAL_DB_PATH.exists():
        return {"error": f"Original database not found: {ORIGINAL_DB_PATH}"}
    src = sqlite3.connect(f"file:{ORIGINAL_DB_PATH.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(DB_PATH)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    with _connect() as con:
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("tickets", "payments", "invoices", "leases")}
        balance = _row(con.execute("SELECT * FROM cash_accounts WHERE name = 'checking'"))
    return {"ok": True, "restored_from": ORIGINAL_DB_PATH.name, "row_counts": counts, "checking": balance}


if __name__ == "__main__":
    mcp.run(show_banner=False)
