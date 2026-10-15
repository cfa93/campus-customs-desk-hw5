# Campus Customs Desk: Multi-Agent Ticket Handling (HW5)

Campus Customs is a small Yale merchandise shop on Chapel Street. Its desk has three open tickets:

- **#101:** a customer wants a size S tee that's out of stock.
- **#102:** an emailed rent notice.
- **#103:** a student club asking for a bulk hoodie discount.

This project handles them with **5 PydanticAI agents** (Boss, Inventory, Accounting, Facilities, Customer Service). The agents reach the shop's SQLite database **only through an MCP server**. A **FastAPI backend** runs the agents, and a **React dashboard** lets a person watch them work and approve every payment.

- **Model:** every agent uses `gpt-6-luna` through the **Portkey** gateway.
- **Payments:** agents can't approve payments, contact anyone, or take cash below $0.

```
Person ──► React dashboard (frontend/, :5173) ──► FastAPI desk API (backend/main.py, :8000)
                                                     │ runs agents        │ approvals / cash / reset
                                                     ▼                    │
                         Boss ⇄ Inventory ⇄ Accounting ⇄ Facilities ⇄ Customer Service
                                                     │ role-filtered MCP tools
                                                     ▼                    ▼
                                    MCP server "campus-customs" (mcp_server/server.py)
                                                     ▼
                                         data/campus_customs_new.db
```

## Repository layout

| Path | What it is |
|---|---|
| `data/campus_customs.db` | **Original** database. Never modified. It's the source for resets. |
| `data/campus_customs_new.db` | **Working copy** the app reads and writes. As committed, it holds the final Problem 9 state: all 3 tickets resolved, 2 payments, checking $160. |
| `mcp_server/server.py` | FastMCP server with 18 tools, the only path to the database ([README](mcp_server/README.md)) |
| `backend/agents.py` | The 5 agents: delegation, loop limits, audit logging |
| `backend/prompts/` | `shop_rules.md` plus one role prompt per agent |
| `backend/models.py` | Data types (agent outputs, approvals, audit entries) |
| `backend/main.py` | FastAPI desk API |
| `backend/approvals.py`, `backend/audit.py` | Human-approval queue and append-only audit trail |
| `frontend/` | React + Vite + TypeScript dashboard |
| `output/` | All results: harness, desk tickets page, resolved tickets, screenshots, audit trail (see below) |
| `.mcp.json` | Connects the MCP server to Claude Code |
| `AI_prompts.md` | Every prompt used to build this, by problem |

## Setup (once)

You need **Python 3.12+** and **Node.js 20+**.

```bash
git clone <this repo>
cd <repo>

pip install -r requirements.txt          # Python: MCP server, agents, backend
cd frontend && npm install && cd ..      # dashboard

cp .env.example .env                     # Windows: copy .env.example .env
# then edit .env and set PORTKEY_API_KEY=<your Portkey key>
```

- **Key location:** the agents read `PORTKEY_API_KEY` from `.env` in this folder (or its parent folder).
- **Never commit `.env`:** `.gitignore` already excludes it.
- **No key needed:** the MCP server, the dashboard and the reset work without a key. Only running the agents needs one.

## 1. Reset the database to the original data

The working copy is restored from the read-only original, so `data/campus_customs.db` is never changed. Use any of these:

| Way | How |
|---|---|
| Dashboard | Click **Reset data** (top right) → confirm |
| API | `curl -X POST http://localhost:8000/reset` (or **POST /reset** at http://localhost:8000/docs) |
| Without the server | `cp data/campus_customs.db data/campus_customs_new.db` (Windows: `copy data\campus_customs.db data\campus_customs_new.db`) |

After a reset:
- **Tickets:** 101, 102 and 103 are `open`.
- **Checking:** $3,400.
- **Payments:** none.
- **API/dashboard reset only:** any pending approvals are marked `voided`, and the audit trail is kept.

## 2. Start the MCP server

You usually don't start it by hand:
- **Backend:** it starts the server automatically (stdio) for the agents and the API.
- **Claude Code:** it starts the server through `.mcp.json`. Open this folder in Claude Code, approve `campus-customs`, then check with `/mcp`.

To run it on its own:

```bash
python mcp_server/server.py
```

It speaks MCP over stdio and uses only `data/campus_customs_new.db`.

## 3. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000     # or: python -m uvicorn main:app --reload --port 8000
```

- **Docs:** http://localhost:8000/docs.
- **Use `main:app`:** not just `main`.
- **Windows shortcut:** `start_backend.bat` does the same thing.

| Method | Route | What it does |
|---|---|---|
| GET | `/tickets` | All tickets and their status |
| GET | `/tickets/{id}` | One ticket plus every record it links to |
| POST | `/tickets/{id}/runs` | Start the agents on a ticket in the background. `{"apply": true}` saves the Boss's status decision. |
| GET | `/runs/{run_id}` | Live run state: handoffs and a summary per agent |
| GET | `/activity?run_id=` | Each agent step: messages and tools used |
| GET | `/approvals` | Payment, purchase and price requests waiting for a person |
| POST | `/approvals/{id}/approve` · `/reject` | A **named person** decides. Payments are recorded through MCP. |
| POST | `/tickets/{id}/resolve` | A person marks a ticket resolved (blocked while approvals are pending) |
| GET | `/cash` | Checking balance from the database |
| POST | `/reset` | Restore the working database from the original |

The full list, with the older blocking `POST /tickets/{id}/run`, is in [output/harness.md](output/harness.md).

## 4. Start the React dashboard

```bash
cd frontend
npm run dev          # http://localhost:5173
```

With the backend running on port 8000, open **http://localhost:5173**:
1. **Pick a ticket.**
2. **Click Run agents.** Watch **Live activity** (who's working, each lookup and message) and **Agent summaries**.
3. **Approve or reject** payments in **Human approvals**. The checking balance updates.
4. **Click Mark resolved.**

**Deep links:** `?ticket=102&tab=summary` opens a specific ticket and tab.

### Command line (optional)

```bash
python backend/agents.py                      # Boss handles all open tickets (dry run)
python backend/agents.py --agent inventory --task "Is CC-HOOD-NAVY M in stock for 20?"
```

## Safety rules (enforced in code)

- **Payments need a human.** Agents only *request* payments.
  - **Human-only tool:** `record_payment` is never given to any agent, and it refuses agent names as `approved_by`.
  - **Amounts re-checked:** it re-checks every amount against the invoice or lease.
  - **Never below $0:** it refuses anything that would take cash below $0.
- **No contacting anyone.** There are no email, phone or web tools, and customer replies are drafts only.
- **Token and loop limits per run:** 60 model calls, 100 tool calls, 250k tokens, 3 handoffs deep, 15 handoffs total.
- **Least privilege:** each agent sees only its role's MCP tools, and only the Boss can update a ticket.
- **Everything is audited** in `output/audit_trail.json` (append-only).

## Results (`output/`)

| File | Contents |
|---|---|
| [`harness.md`](output/harness.md) | Full reference: tables, MCP tools, agents, routes, dashboard, safety, final results |
| [`desk_tickets.html`](output/desk_tickets.html) | For each ticket: Expected plan vs Actual run, a **Cash** reconciliation ($3,400 → $160), and a **Reflection** |
| [`resolved_tickets.json`](output/resolved_tickets.json) | Final status, outcome, each agent's work, and human approvals for 101/102/103 |
| [`resolved_board.html`](output/resolved_board.html) + `screenshots/` | Dashboard screenshots of the 3 resolved tickets |
| [`design.md`](output/design.md) | Dashboard design choices |
| `audit_trail.json`, `approvals.json` | Every agent step and human decision |
| `agent_run.json`, `mcp_smoke.json` | Earlier runs: the Boss on all tickets, and the MCP tool smoke test |
| `github_url.txt` | Link to this repository |

**Final run (Problem 9):**
- **All 3 tickets resolved.**
- **Payments:** King approved the $840 invoice and the $2,400 rent, and rejected the discount.
- **Checking:** $3,400 → $160, matching `cash_accounts`.
