# Campus Customs MCP Server

An MCP server built with [FastMCP](https://gofastmcp.com). It is the only way the Campus Customs agents reach the shop's database. It gives them tools to:
- **Read the queue:** see open tickets.
- **Look up records:** stock, pricing, vendors, invoices, payments, cash and leases.
- **Record decisions:** update a ticket's status.

The five PydanticAI agents in `backend/agents.py` start this server over stdio and call its tools. The backend has no database code of its own. Claude Code connects to it too, through `.mcp.json`.

## Database

- **Uses:** `data/campus_customs_new.db` (SQLite), the working copy.
- **Never touches:** `data/campus_customs.db`, the original, which must stay unchanged.
- **Path:** resolved relative to this folder, so the server works from any directory.
- **Read-only by default:** every tool except `update_ticket` opens the database read-only.
- **No invented values:** every value comes straight from the database. Missing records come back as `{"error": ...}` or `found: false`, never guessed.

Tables: `desk`, `inventory`, `pricing`, `vendors`, `invoices`, `leases`, `cash_accounts`, `payments`, `tickets`. See `output/harness.md` for fields.

## Tools (18)

There are 15 agent tools plus 3 tools for the desk API: `list_tickets` and the human-only `record_payment` and `reset_database`.

### Desk and tickets
| Tool | What it returns |
|---|---|
| `get_desk()` | Today's shop date (`desk.date_today`) and desk notes. Agents use this date, never the system clock. |
| `list_tickets()` | Every ticket, any status, by id. Used by the API's `GET /tickets`. |
| `list_open_tickets()` | All `open` tickets, oldest first, plus `desk_date`. |
| `get_ticket(ticket_id)` | One ticket, all fields. |
| `get_ticket_context(ticket_id)` | One ticket plus everything it links to. See the list below this table. |
| `update_ticket(ticket_id, status, note, dry_run=False)` | **The only write.** Sets status (`open`, `in_progress`, `escalated`, `closed`) and adds a note stamped with the desk date. `dry_run=true` previews without writing. |

What `get_ticket_context` includes:
- **SKU tickets:** inventory for the requested size, inventory for all sizes, and pricing.
- **Linked invoice:** the invoice, its vendor and its payments.
- **Linked lease:** the lease and its payments.
- **Always:** cash balances, the desk date, and `warnings` such as stock shortfalls, overdue invoices or a requester who isn't the landlord.

### Inventory and vendors
| Tool | What it returns |
|---|---|
| `check_stock(sku, size, requested_qty)` | Stock for one size: `available_qty`, `enough_stock`, `shortfall`, the location, and every other size of the SKU. |
| `list_inventory(sku=None)` | All inventory rows, or the rows for one SKU. |
| `list_vendors()` | Vendors with specialty and `lead_days`. |

### Pricing, invoices, payments, cash
| Tool | What it returns |
|---|---|
| `get_pricing(sku)` | `list_price` and `unit_cost`. |
| `check_invoice(invoice_id)` | The invoice, its vendor, recorded payments, `amount_paid`, `overdue` and `days_overdue`, all counted from the desk date. |
| `list_invoices(status=None)` | All invoices, or those with one status, by due date. |
| `list_payments()` | Every recorded payment. |
| `get_cash_position()` | Cash balances against all open invoices and every lease's rent, plus `cash_after_all_obligations`. |

### Leases
| Tool | What it returns |
|---|---|
| `list_leases()` | Every lease: landlord, monthly rent, next due date. |
| `check_lease(lease_id)` | One lease, its recorded rent payments, and `days_until_due` from the desk date. |

### Human-only (called by `backend/main.py` after a person acts, never by an agent)
| Tool | What it does |
|---|---|
| `record_payment(kind, ref_id, amount, approved_by, account="checking")` | Records an approved payment and takes it out of cash, in one locked transaction. See the checks below. |
| `reset_database()` | Restores `campus_customs_new.db` from the original `campus_customs.db`. The original is opened read-only and copied with SQLite's backup API. |

`kind` is `invoice` (ref_id = invoice id), `lease` (lease id) or `purchase` (vendor id).

Checks `record_payment` makes before recording anything:
- **Approver:** refused if `approved_by` is empty or an agent/system name (`boss`, `accounting`, `agent`, `ai`, ...).
- **Invoice amount:** must not be more than what's still owed, and the invoice must be `open`. Paying the full balance marks it `paid`.
- **Rent amount:** must equal `monthly_rent`. Paying it moves `next_due` forward one month.
- **Purchase:** the vendor must exist.
- **Balance:** refused if the account would go below $0.

The payment row is stamped with the desk date.

## What the server deliberately cannot do

- **Let agents record payments:** `record_payment` exists only for the desk API. The backend blocks it for every agent, both in their tool lists and in `_guarded_call`. Payments always need a named person.
- **Change prices or inventory:** discounts need human approval, and stock changes happen on the shop floor.
- **Contact anyone:** there are no email, phone or messaging tools. Agents only draft messages.

## How the backend uses it

- **Filtered tools:** each agent gets a filtered view with only its role's tools. See the Agents table in `output/harness.md`.
- **Separate API client:** the desk API (`backend/main.py`) keeps its own MCP client for ticket lists, cash, approvals and reset.
- **The `_guarded_call` hook:** every call passes through `_guarded_call` in `backend/agents.py`, which does three things:
  - **Role check:** blocks tools outside the agent's role.
  - **Dry-run control:** forces `dry_run` on `update_ticket` to the run's setting. The model can't override it.
  - **Audit:** logs the call, its args and its result to `output/audit_trail.json`.

## Setup

```bash
pip install -r mcp_server/requirements.txt
python mcp_server/server.py        # stdio; normally started by the backend or Claude Code
```
