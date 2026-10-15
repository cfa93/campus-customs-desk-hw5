# Campus Customs Agent Harness

This is the reference for the Campus Customs desk system: 5 AI agents that handle shop tickets, a MCP server that is their only path to the database, a FastAPI backend, and a React dashboard where a person approves anything that moves money.

- **Working database:** `data/campus_customs_new.db`. Never modify `data/campus_customs.db`.
- **Database access:** agents reach the database only through the MCP server.
- **Model:** all agents use `gpt-6-luna` through Portkey.

**Contents:**
1. Database Tables
2. Architecture
3. Agents
4. MCP Tools
5. Safety Rules
6. Desk API (backend routes)
7. Dashboard (frontend)
8. Audit Trail
9. Final Results (Problem 9)
10. Output Files

## Database Tables

### desk
**Fields:** `date_today` (TEXT, not null), `notes` (TEXT)

**Why it matters:** This is the agent's source for the current date (2026-08-31). Agents must use it, not the system clock, to judge due dates, overdue items, and deadlines.

### inventory
**Fields:** `sku` (TEXT, not null), `name` (TEXT, not null), `size` (TEXT, not null), `qty` (INTEGER, not null), `location` (TEXT, not null). Primary key: (`sku`, `size`)

**Why it matters:** Agents check stock here before promising or filling an order. Stock is tracked per size, so a SKU can be in stock in one size and out of stock in another (e.g. CC-TEE-WHITE S = 0).

### pricing
**Fields:** `sku` (TEXT, primary key), `unit_cost` (REAL, not null), `list_price` (REAL, not null)

**Why it matters:** This gives the normal selling price and the cost floor. Agents need it to quote orders and to judge whether a discount request still covers cost.

### vendors
**Fields:** `id` (INTEGER, primary key), `name` (TEXT, not null), `specialty` (TEXT, not null), `lead_days` (INTEGER, not null)

**Why it matters:** This shows who supplies what and how long restocks take. Agents use `lead_days` to estimate when out-of-stock items can be fulfilled, and use the table to check who sent an invoice.

### invoices
**Fields:** `id` (INTEGER, primary key), `vendor_id` (INTEGER, not null, FK → `vendors.id`), `amount` (REAL, not null), `due_date` (TEXT, not null), `status` (TEXT, not null), `description` (TEXT)

**Why it matters:** These are bills the shop owes. Agents compare `due_date` with `desk.date_today` to spot overdue bills and must link each invoice to a real vendor before any payment.

### leases
**Fields:** `id` (INTEGER, primary key), `space_name` (TEXT, not null), `landlord` (TEXT, not null), `monthly_rent` (REAL, not null), `next_due` (TEXT, not null), `notes` (TEXT)

**Why it matters:** This is the source of truth for rent. Agents check rent notices against the real landlord, amount, and due date here, and don't trust the notice's own text.

### cash_accounts
**Fields:** `name` (TEXT, primary key), `balance` (REAL, not null), `date` (TEXT, not null)

**Why it matters:** This shows how much money is available. Agents must confirm a payment fits within the balance and plan which obligations to pay first when cash is tight.

### payments
**Fields:** `id` (INTEGER, primary key), `kind` (TEXT, not null), `ref_id` (INTEGER), `amount` (REAL, not null), `account` (TEXT, not null), `paid_at` (TEXT, not null), `approved_by` (TEXT, not null)

**Why it matters:** This is the record of money going out. Agents can read it (to check that a bill isn't already paid) but can never write to it.
- **How rows get here:** a row is added only by the human-only MCP tool `record_payment`, after a named person approves in the dashboard.
- **`approved_by`:** required on every row.
- **`ref_id`:** not enforced by a foreign key, so `record_payment` checks that it points to a real invoice, lease or vendor itself.

### tickets
**Fields:** `id` (INTEGER, primary key), `type` (TEXT, not null), `requester` (TEXT, not null), `subject` (TEXT, not null), `sku` (TEXT), `size` (TEXT), `qty` (INTEGER), `lease_id` (INTEGER, FK → `leases.id`), `invoice_id` (INTEGER, FK → `invoices.id`), `status` (TEXT, not null), `notes` (TEXT), `created_at` (TEXT, not null)

**Why it matters:** This is the agent's work queue. Each ticket's `type` decides how it is handled, and its `sku`/`size`, `lease_id`, or `invoice_id` show which other tables to check before acting.

## Architecture

```
 Person ──► Desk API (backend/main.py, FastAPI)
              │  run agents          │  approve / reject / cash / reset
              ▼                      │
 Boss ──┬── Inventory                │   (every agent can ask_<agent> every other agent)
        ├── Accounting               │
        ├── Facilities               │
        └── Customer Service         │
              │ agent tools only     │ API-only tools (record_payment, reset_database)
              ▼                      ▼
     MCP server "campus-customs" (mcp_server/server.py, stdio)
              │
              ▼
     data/campus_customs_new.db
```

- **Desk API:** `backend/main.py`, see Desk API below. It is the only entry point for people.
- **Agents:** 5 PydanticAI agents in `backend/agents.py`. All use `gpt-6-luna` through Portkey (OpenAI Responses API).
- **Prompts:** `backend/prompts/`. Each agent gets `shop_rules.md` plus its own role prompt.
- **Data access:** only through MCP. The backend has no SQLite code. It starts the MCP server and gives each agent a filtered view with only its role's tools.
- **Audit:** every step is appended to `output/audit_trail.json` (see Audit Trail below).

## Agents

| Agent | Role | MCP tools | Tables it reads (via MCP) | Writes |
|---|---|---|---|---|
| **Boss** | Owns the ticket queue, coordinates, sets ticket status, lists approvals needed | `get_desk`, `list_open_tickets`, `get_ticket`, `get_ticket_context`, `get_cash_position`, `update_ticket` | `desk`, `tickets`, `inventory`, `pricing`, `invoices`, `vendors`, `leases`, `cash_accounts`, `payments` | `tickets` (status + notes) |
| **Inventory** | Stock by SKU/size, shortfalls, restock vendor and lead time | `get_desk`, `list_open_tickets`, `get_ticket`, `check_stock`, `list_inventory`, `list_vendors` | `desk`, `tickets`, `inventory`, `vendors` | nothing |
| **Accounting** | Invoices, payments, cash position, pricing and margins | `get_desk`, `list_open_tickets`, `get_ticket`, `check_invoice`, `list_invoices`, `list_payments`, `get_cash_position`, `get_pricing`, `list_vendors` | `desk`, `tickets`, `invoices`, `vendors`, `payments`, `cash_accounts`, `leases`, `pricing` | nothing |
| **Facilities** | Leases and rent; verifies rent notices against the lease | `get_desk`, `list_open_tickets`, `get_ticket`, `check_lease`, `list_leases`, `list_payments` | `desk`, `tickets`, `leases`, `payments` | nothing |
| **Customer Service** | Drafts replies to requesters from verified facts | `get_desk`, `list_open_tickets`, `get_ticket`, `check_stock`, `get_pricing` | `desk`, `tickets`, `inventory`, `pricing` | nothing |

**Delegation tools.** Every agent also has `ask_<agent>` for each of the other four, so the team is fully connected.
- **What happens on a call:** each delegation starts a new loop for the target agent, which keeps calling tools until it returns a structured answer.
- **Return types:** specialists return an `AgentReport`. The Boss returns a `BossPlan`.

### Which agents handle which ticket

Only the agents a ticket needs are involved. This routing is written into `backend/prompts/boss.md` and explained in `output/desk_tickets.html`.

| Ticket | Type | Calls first | Delegation flow | Not involved |
|---|---|---|---|---|
| 101 | customer_order | Inventory | Boss → Inventory → Accounting (invoice 501), then Boss → Customer Service | Facilities |
| 102 | rent_notice | Facilities | Boss → Facilities. The Boss checks cash itself. | Accounting, Inventory, Customer Service |
| 103 | price_override | Accounting | Boss → Accounting → Inventory (8 of 20 M), then Boss → Customer Service | Facilities |

**Confirmed in the final Problem 9 run:** all 3 tickets followed this routing exactly.
- **First agent:** the Boss called the planned agent first every time.
- **Delegations:** the counts matched the plan (3, 1 and 3).
- **Left out:** the agents listed as "Not involved" were never called.

Details, and the small differences in which tools were used, are in the Actual sections of `output/desk_tickets.html`.

## MCP Tools

Server: `mcp_server/server.py` (FastMCP, name `campus-customs`), connected to `data/campus_customs_new.db`. It has 18 tools.
- **Agent tools (15):** listed below. Only `update_ticket` writes.
- **API tools (3):** `list_tickets` is read-only. `record_payment` and `reset_database` are human-only. No agent can ever see or call these.

| API tool | Reads | Writes | Used by |
|---|---|---|---|
| `list_tickets()` | `tickets` | – | Desk API `GET /tickets` |
| `record_payment(kind, ref_id, amount, approved_by)` | `cash_accounts`, `invoices`, `leases`, `vendors`, `payments`, `desk` | `payments`, `cash_accounts`, `invoices.status`, `leases.next_due` | Desk API `POST /approvals/{id}/approve`, **human only** |
| `reset_database()` | original `campus_customs.db` (read-only) | all tables of `campus_customs_new.db` | Desk API `POST /reset`, **human only** |

Agent tools:

| Tool | Reads | Writes | Used by | Tickets it helps |
|---|---|---|---|---|
| `get_desk()` | `desk` | – | all | 101, 102, 103 (today's date for due/overdue math) |
| `list_open_tickets()` | `tickets`, `desk` | – | all | 101, 102, 103 (the work queue) |
| `get_ticket(ticket_id)` | `tickets` | – | all | 101, 102, 103 |
| `get_ticket_context(ticket_id)` | `tickets`, `desk`, `cash_accounts`, `inventory`, `pricing`, `invoices`, `vendors`, `leases`, `payments` | – | Boss | 101, 102, 103 (everything a ticket links to) |
| `update_ticket(ticket_id, status, note, dry_run)` | `tickets`, `desk` | `tickets` | Boss | 101, 102, 103 (record the decision) |
| `check_stock(sku, size, requested_qty)` | `inventory` | – | Inventory, Customer Service | 101 (S = 0), 103 (M = 8 of 20) |
| `list_inventory(sku)` | `inventory` | – | Inventory | 101, 103 |
| `list_vendors()` | `vendors` | – | Inventory, Accounting | 101 (Bulldog Print Co, 5 lead days) |
| `get_pricing(sku)` | `pricing` | – | Accounting, Customer Service | 101 ($28 tee), 103 ($58 list / $22 cost) |
| `check_invoice(invoice_id)` | `invoices`, `vendors`, `payments`, `desk` | – | Accounting | 101 (invoice 501, $840, 3 days overdue) |
| `list_invoices(status)` | `invoices` | – | Accounting | 101, 102 (all open bills compete for cash) |
| `list_payments()` | `payments` | – | Accounting, Facilities | 101, 102 (confirm nothing is already paid) |
| `get_cash_position()` | `cash_accounts`, `invoices`, `leases`, `desk` | – | Boss, Accounting | 101, 102 ($3,400 − $840 − $2,400 = $160) |
| `list_leases()` | `leases` | – | Facilities | 102 |
| `check_lease(lease_id)` | `leases`, `payments`, `desk` | – | Facilities | 102 (lease 1, $2,400, due in 2 days) |

### Why the original 3 tools are needed for each ticket

#### list_open_tickets()
| Ticket | Why this tool is needed |
|---|---|
| 101 | It surfaces Tauhid Zaman's open tee order so the agent knows a customer is waiting on an out-of-stock item. |
| 102 | It surfaces the rent notice with its `created_at` and the desk date so the agent can see the rent deadline is close. |
| 103 | It surfaces the Yale AI Club discount request so the agent knows a pricing decision is pending. |

#### get_ticket_context(ticket_id)
| Ticket | Why this tool is needed |
|---|---|
| 101 | It shows CC-TEE-WHITE size S has 0 in stock and links invoice 501 ($840 from Bulldog Print Co, due 2026-08-28) so the agent sees the order depends on an overdue reprint bill. |
| 102 | It pulls lease 1 ($2,400 due 2026-09-02, landlord Elm City Properties) and the $3,400 checking balance so the agent can verify the emailed notice against real records before anything is paid. |
| 103 | It shows only 8 size-M hoodies in stock against 20 requested, plus the $58 list price and $22 unit cost, so the agent knows the stock gap and the cost floor before answering the discount request. |

#### update_ticket(ticket_id, status, note, dry_run)
| Ticket | Why this tool is needed |
|---|---|
| 101 | It lets the agent record that the order is waiting on the reprint (or escalate the overdue invoice) without moving money. |
| 102 | It lets the agent record that the rent notice was checked against lease 1 and escalate payment for human approval, since every payment needs `approved_by`. |
| 103 | It lets the agent record the stock shortfall and its discount recommendation and escalate the price override for a human decision. |

## Safety Rules

These are enforced in code, not just written in the prompts (`backend/prompts/shop_rules.md`, section 9).

### 1. Payments require human approval
- **No payment tool for agents:** the only tool that writes to `payments` is `record_payment`. It is human-only:
  - **Never handed out:** it's in `HUMAN_ONLY_TOOLS` and never given to any agent. A startup check fails if one ever gets it.
  - **Blocked if tried:** `_guarded_call` blocks it if an agent attempts it.
  - **Rejects agent approvers:** it refuses an `approved_by` that is an agent or system name.
- **Path to a payment:** agent request → `output/approvals.json` (pending) → a named person calls `POST /approvals/{id}/approve` → `record_payment`.
  - **Agent names rejected:** the API rejects agent names like `boss` or `accounting` as approvers (403).
  - **Single use:** an approval can't be used twice.
- **Cash can't go negative:** `record_payment` checks the balance inside a locked transaction and refuses any payment that would go below $0.
  - **Tested:** after paying $840 and $2,400, a $264 purchase was refused with "$160 → −$104".
  - **Amounts re-checked:** rent must equal `monthly_rent`, and an invoice payment can't be more than what's owed.
- **Recommend only:** agents can only recommend payments. The Boss lists them in `BossPlan.approvals_needed` with the kind, invoice or lease id, exact amount and reason. Tickets that need a payment are set to `escalated`, not `closed`.
- **Same for discounts:** any price below `list_price` needs human approval, and agents never recommend below `unit_cost`.
- **Seen in practice (Problem 9):** the agents asked for 3 approvals ($840 invoice, $2,400 rent, a price override). They were asked about first, then decided by King: 2 paid, 1 rejected. No agent moved money, and the balance never went below $0.

### 2. No contacting real customers, vendors or landlords
- **No outbound tools:** there is no email, phone, SMS or web tool anywhere in the system.
- **Drafts only:** Customer Service writes `customer_message` drafts for a human to review and send. Prompts forbid saying a message was sent.

### 3. Token and loop limits
| Limit | Value | Where |
|---|---|---|
| Model requests per run | 60 | `USAGE_LIMITS.request_limit` |
| Tool calls per run | 100 | `USAGE_LIMITS.tool_calls_limit` |
| Total tokens per run | 250,000 | `USAGE_LIMITS.total_tokens_limit` |
| Max tokens per model response | 8,000 | `MODEL_SETTINGS.max_tokens` |
| Delegation depth | 3 | `MAX_DEPTH` |
| Delegations per run | 15 | `MAX_DELEGATIONS` |

- **One shared budget:** a single usage counter is shared by every agent in a run, including delegated agents, so the limits cover the whole team.
- **Delegation refusals:** a delegation past the limits is refused and logged as `delegation_refused`. The agent finishes with the facts it has.
- **Over budget:** going over the request, tool or token limits stops the run, and the run is logged as `error`.

### 4. Role and write restrictions
- **Role tools only:** each agent sees only its role's MCP tools. A call to any other tool is blocked in `_guarded_call` and logged as `tool_blocked`.
- **Boss-only writes:** only the Boss has `update_ticket`. The run, not the model, decides `dry_run`, which defaults to true.
  - **To write for real:** use **Save status decision** in the dashboard, `{"apply": true}` in the API, or `--apply` on the command line.
- **Protected original:** `data/campus_customs.db` is never written. Only `reset_database` opens it, read-only, to copy it over `campus_customs_new.db`.

## Desk API (backend routes)

`backend/main.py` (FastAPI). Start it from the `backend` folder:

```powershell
cd backend
python -m uvicorn main:app --reload --port 8000
```

- **Plain `uvicorn` now works:** new VS Code terminals open in `backend` (`.vscode/settings.json`) and include Python's Scripts folder on PATH, so `uvicorn main:app --reload --port 8000` works as typed. `python -m uvicorn ...` works anywhere, as a fallback.
- **Run from `backend`:** `main.py` lives there. From `hw5`, use `--app-dir backend` instead of `cd backend`.
- **Use `main:app`, not just `main`:** Uvicorn needs `<file>:<app object>` and fails with "Import string must be in format `<module>:<attribute>`" otherwise.
- **Base URL:** **http://127.0.0.1:8000**. **http://localhost:8000** is the same server, and it's what the dashboard uses.
- **Database access:** every database read and write goes through MCP.

| Method | URL | What it does |
|---|---|---|
| GET | http://127.0.0.1:8000/ | Health check: service name and a link to the docs. |
| GET | http://127.0.0.1:8000/docs | Interactive Swagger page to try every route in the browser. |
| GET | http://127.0.0.1:8000/tickets | All tickets (101, 102, 103) with their current status, notes and the desk date. |
| GET | http://127.0.0.1:8000/tickets/{ticket_id} | One ticket with every record it links to: stock, pricing, invoice, vendor, lease, cash, warnings. |
| POST | http://127.0.0.1:8000/tickets/{ticket_id}/run | Runs the agent team on one ticket. Body `{"apply": false}` (default) is a dry run, and `true` writes the status. Returns the plan, delegations, usage and queued approvals. |
| GET | http://127.0.0.1:8000/activity?limit=50&run_id=&agent= | Recent agent steps from the audit trail, newest first: messages, tools used, delegations, approvals. |
| GET | http://127.0.0.1:8000/approvals?status=pending | Payment, purchase and price requests from agents, filterable by status (pending, approved, rejected, failed, voided). |
| POST | http://127.0.0.1:8000/approvals/{approval_id}/approve | A named person approves. Body `{"approved_by": "King"}`. Records the payment through MCP, refused for agent names, wrong amounts or a negative balance. |
| POST | http://127.0.0.1:8000/approvals/{approval_id}/reject | A named person rejects. Body `{"rejected_by": "King", "reason": "..."}`. Nothing is paid, and a note is added to the ticket. |
| GET | http://127.0.0.1:8000/cash | Current checking balance from the database, plus open invoices, rent and what's left after both. |
| POST | http://127.0.0.1:8000/reset | Restores `campus_customs_new.db` to the original values. Pending approvals are voided, and the audit trail is kept. |
| POST | http://127.0.0.1:8000/tickets/{ticket_id}/runs | Starts the agents on a ticket **in the background** and returns a `run_id` immediately. Used by the dashboard for live progress. |
| GET | http://127.0.0.1:8000/runs | Runs started since the server started, newest first, with status. |
| GET | http://127.0.0.1:8000/runs/{run_id} | Live run state: status, delegations so far, a summary per agent (tasks, answers, facts, tools, who it asked), and the final plan. |
| POST | http://127.0.0.1:8000/tickets/{ticket_id}/resolve | A named person marks a ticket resolved (status `closed`). Refused (409) while it has pending approvals. |

## Dashboard (frontend)

`frontend/`: React + Vite + TypeScript, styled black and pink.
- **Start:** from `frontend`, run `npm install` once, then `npm run dev`.
- **Open:** **http://localhost:5173**.
- **Deep links:** `?ticket=102` opens a ticket directly, and `&tab=summary` opens its Agent summaries tab. The screenshots used these.
- **Backend calls:** the browser calls the backend directly at **http://localhost:8000**. The address is set by `VITE_API_URL` in `frontend/.env`.
- **CORS:** the backend allows requests only from `http://localhost:5173` and `http://127.0.0.1:5173`.

| Area | What it shows / does | Backend routes |
|---|---|---|
| Header | Checking balance (re-fetched every 8 s and right after each approval, highlighted when it changes) · "Approving as" name · Reset data | `GET /cash`, `POST /reset` |
| Tickets list | All 3 tickets with status, "Agents working…" and "awaiting approval" flags | `GET /tickets`, `GET /approvals` |
| Ticket panel | Request text, key database facts and warnings, **Run agents** (with a "Save status decision" toggle), **Mark resolved** | `GET /tickets/{id}`, `POST /tickets/{id}/runs`, `POST /tickets/{id}/resolve` |
| Live activity tab | "Who's working" handoff flow, plus a step-by-step feed of each agent's tool lookups, handoffs and messages, polled every 1.2 s | `GET /runs/{run_id}`, `GET /activity?run_id=` |
| Agent summaries tab | One card per agent that took part: headline, tools used, who it asked, tasks with answers, facts (with source tables), recommendations, draft messages. The Boss card shows the decision, approvals requested and risks. | `GET /runs/{run_id}` |
| Human approvals | Pending payment, purchase and price requests with **Approve & pay** / **Reject** (needs a reason), plus recent decisions and any refusals (e.g. a negative balance) | `GET /approvals`, `POST /approvals/{id}/approve`, `/reject` |

Safety in the UI mirrors the backend:
- **Approver name:** the approve, reject and resolve buttons need a name. The backend still refuses agent names.
- **Resolve:** stays disabled while a ticket has pending approvals.
- **Money:** every payment is checked again by the MCP server, including the never-negative balance rule.

**Checked on 2026-10-15** with the server started from `backend/` on port 8000:
- **Read routes:** every GET returned 200. `/tickets/999` returned 404.
- **Guard:** approving as `boss` returned 403.
- **Agent run:** `POST /tickets/103/run` (dry run) returned 200 with the Boss's plan.

## Audit Trail

`output/audit_trail.json` is a JSON list that only grows. New runs are appended and earlier records are always kept.
- **One run id per run:** every step of a top-level run shares its `run_id`.
- **Unreadable files:** if the file can't be parsed, it's renamed to `audit_trail.unreadable-<time>.json` instead of being overwritten.

| Event | Logged when |
|---|---|
| `run_start` | An agent loop begins: the top-level run or a delegated task |
| `model_response` | The model replied, with the tools it asked for and any text |
| `tool_call` | An MCP tool ran, with args and result |
| `tool_blocked` | A tool call was refused by the role check |
| `delegation` / `delegation_refused` | An agent asked another agent, or hit a loop limit |
| `run_end` | An agent finished, with its structured output and token usage |
| `error` | A loop failed, e.g. a usage limit was exceeded |
| `approval_created` | An agent's payment, purchase or price request was queued for a person |
| `human_approved` / `human_rejected` | A named person decided a request (agent: `human`) |
| `approval_failed` | A person approved, but the MCP server refused, e.g. negative balance or wrong amount |
| `database_reset` | `POST /reset` restored the working database |
| `ticket_resolved` | A named person marked a ticket resolved from the dashboard |

Each entry has: `timestamp` (real UTC), `run_id`, `agent`, `event`, `depth`, `chain`, `tool`, `args`, `result`, `dry_run`, `usage`.

## Final Results (Problem 9)

The working database was reset to the original data. Then tickets 101 → 102 → 103 were run through the dashboard with **Save status decision** on, and every payment was put to King before approving. All values below come from the run records, the audit trail and the database (through MCP).

| | Value |
|---|---|
| Starting checking balance (after reset) | **$3,400** |
| Paid out (2 human-approved payments) | **−$3,240** |
| Ending checking balance (`cash_accounts.checking`) | **$160** |
| Tickets resolved | **3 / 3** |

| Ticket | Agents involved | Delegations | Boss set | Human decision | Cash change | Final |
|---|---|---|---|---|---|---|
| 101 | Boss, Inventory, Accounting, Customer Service | Boss → Inventory, Inventory → Accounting, Boss → Customer Service | escalated | invoice payment $840: approved by King | −$840 | Resolved |
| 102 | Boss, Facilities | Boss → Facilities | escalated | rent payment $2,400: approved by King | −$2,400 | Resolved |
| 103 | Boss, Accounting, Inventory, Customer Service | Boss → Accounting, Accounting → Inventory, Boss → Customer Service | escalated | price override: rejected by King | $0 | Resolved |

More detail:
- **`output/desk_tickets.html`:** the Expected vs Actual comparison for each ticket, and the Cash reconciliation.
- **`output/resolved_tickets.json`:** what each agent did, plus approvals and payments.
- **`output/resolved_board.html`:** dashboard screenshots of each resolved ticket.

## Output Files

| File | What it is |
|---|---|
| `output/harness.md` | This reference |
| `output/desk_tickets.html` | Expected plan vs actual results for each ticket, the Cash tab, and Reflection (empty for now) |
| `output/resolved_tickets.json` | Final status, outcome, each agent's work, delegations, MCP tools and human approvals for 101, 102 and 103 |
| `output/resolved_board.html` + `output/screenshots/` | Dashboard screenshots (live activity and agent summaries) of the 3 resolved tickets |
| `output/audit_trail.json` | Append-only log of every agent step and human action, across all runs |
| `output/approvals.json` | Every approval request and its decision (pending, approved, rejected, failed, voided) |
| `output/design.md` | Dashboard design: layout, agent visuals, resolved and cash display, design choices |
| `output/agent_run.json` | Full output of an earlier Boss run on all tickets (Problem 5/6) |
| `output/mcp_smoke.json` | MCP tool smoke test against the database (Problem 4) |
| `output/github_url.txt` | Link to the public GitHub repository (Problem 11) |
