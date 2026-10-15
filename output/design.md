# Campus Customs Desk: Dashboard Design

The dashboard (`frontend/`, React + Vite + TypeScript) is the one screen a shop manager needs to work the ticket queue. It shows what the AI agents are doing, and it puts every money decision in a person's hands.

- **Open it at:** http://localhost:5173
- **Backend it talks to:** http://localhost:8000

## 1. Layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ● Campus Customs   ● Backend connected  Desk date   [ CHECKING $160 ]  Approving as [King]  Reset │
├──────────────┬────────────────────────────────────────────┬────────────────┤
│ TICKETS      │ #101 Bulldog tee                 [Needs approval] │ HUMAN APPROVALS│
│ ▌#101 …      │ "Needs a tee in size S."                   │  ┌ Rent $2,400 ┐│
│  #102 …      │ [Item][Stock S: 0][Other sizes][Price]…    │  │ Approve & pay││
│  #103 …      │ ⚠ warnings                                 │  └─────────────┘│
│              │ [Run agents] ☑ Save status     [Mark resolved]│ Recent decisions│
│              │ ── Live activity | Agent summaries ──      │                │
│              │ Who's working   │  Step by step feed        │                │
└──────────────┴────────────────────────────────────────────┴────────────────┘
```

The page has three columns, ordered the way a manager works: **pick a ticket → see what happened → make the decision**.

| Area | Purpose |
|---|---|
| **Top bar** (sticky) | Connection status, desk date, the **checking balance**, who is approving, and Reset. Always visible, because money is what every decision affects. |
| **Left: Tickets** | All 3 tickets as cards: id, subject, type, requester and status, plus live flags ("Agents working…", "2 awaiting approval"). |
| **Center: Ticket panel** | The selected ticket: request quote, key database facts, warnings, actions, then two tabs: **Live activity** and **Agent summaries**. |
| **Right: Human approvals** | Every payment, purchase or price request from the agents, with Approve/Reject, plus recent decisions. Sticky, so it stays in view while you scroll. |

**Smaller screens:** the approvals panel moves under the other two at ≤1200 px, and everything stacks into one column at ≤800 px.

## 2. How agents look different

Each agent has its own **colour, monogram and job line**. All three appear wherever the agent shows up: the feed, the handoff flow and the summary cards.

| Agent | Colour | Monogram | Role line on its card |
|---|---|---|---|
| Boss | Pink `#ff4fa3` (brand colour, the "lead") | **BS** | Coordinates the team and decides |
| Inventory | Cyan `#5ad1e6` | **IN** | Stock, sizes, restock lead times |
| Accounting | Amber `#f5b64e` | **AC** | Invoices, cash, pricing |
| Facilities | Violet `#a98bff` | **FA** | Lease and rent checks |
| Customer Service | Green `#4fd18b` | **CS** | Drafts replies to requesters |

- **Never colour alone:** every avatar has the agent's name next to it, and the colours are just a faster way to scan.
- **Working vs. done:**
  - **Working:** the avatar sends out a pulsing ring, and its pill reads **Working** in pulsing pink.
  - **Done:** the pill turns green and reads **Done** or **answered**.
- **Hierarchy is visible:**
  - **Feed:** each step is indented by delegation depth, so "Inventory asked Accounting" sits under "Boss asked Inventory".
  - **"Who's working":** shows the same tree as `Boss → Inventory → Accounting`.
- **Agents left out are named too:** the summaries tab ends with *"Not involved: Facilities"*. That shows the Boss sent only the specialists the ticket needed, which was a goal from Problem 6.

## 3. Resolved tickets

- **Status language for people:** database statuses get plain-English badges.
  - **`open`:** Open (grey).
  - **`in_progress`:** In progress (blue).
  - **`escalated`:** **Needs approval** (amber).
  - **`closed`:** **Resolved** (green).
- **Resolving is a deliberate, guarded step:**
  - **Disabled until it's allowed:** **Mark resolved** stays disabled while the agents are running or while the ticket has pending approvals. A hint says exactly why, e.g. "Approve or reject 2 pending requests first". The backend enforces the same rule (409).
  - **Inline confirm:** clicking it opens a small inline form with an optional resolution note, then **Confirm**.
- **Once resolved:**
  - **Badges:** the green **Resolved** badge shows in the list and in the ticket header.
  - **Buttons:** the button reads **Resolved ✓**, and **Run agents** is disabled.
  - **Records:** a note with your name is added to the ticket, and the action is logged in the audit trail.

## 4. Cash balance

- **The biggest number on the screen:** large, with tabular figures so digits don't jump, in a card in the sticky header.
- **Second line, "After open bills & next rent":** balance minus open invoices and the next rent. It turns **red** when it would go negative. That warns the manager before trouble, e.g. after paying August's rent it shows October's $2,400 against $160.
- **Updates you can see:**
  - **When it refreshes:** right after every approval, and every 8 seconds.
  - **Highlight:** when it changes, the card flashes **pink** when money goes out and **green** when it comes in.
  - **Toast:** a message confirms the new figure, e.g. *"Paid $840 (Invoice payment). Checking is now $160."*
- **Can't go negative:** if a payment would overdraw the account, the backend refuses it.
  - **Toast:** shows the reason, e.g. "would take checking from $160 to −$104".
  - **Record:** the request appears under Recent decisions as **failed**, with that message.

## 5. Creative choices for ease of use

1. **Watch the agents think, live.** The feed turns raw audit events into plain sentences:
   - *"Looked up `check_stock(sku="CC-TEE-WHITE", size="S")`"*
   - *"Asked **Accounting**: 'Invoice 501 …'"*
   - *"Finished: '…'"*

   Tool names are shown as pink code chips. The internal `final_result` step is renamed "answer". The feed follows new steps automatically, but stops following if you scroll up to read. Three blinking dots show that work is still going.
2. **Two views of one run.** **Live activity** answers "what is happening?" **Agent summaries** answers "what did each agent conclude?"
   - **Every card:** the agent's headline answer, its tools (with counts), who it asked, the facts it used (each tagged with its source table, like `inventory` or `invoices`) and its recommendations.
   - **The Boss card:** the ticket decision, the approvals it requested, and the risks it flagged.
3. **Facts before AI.** The ticket panel first shows the plain database facts as small labelled tiles, and highlights problems in amber (stock 0, overdue invoice), so a person can check the agents against the data.
4. **Drafts are clearly drafts.** Customer messages sit in a pink-bordered box labelled **"Draft message · not sent"**, because no agent can contact anyone.
5. **Approval cards that say what they'll do.**
   - **Look:** amber cards, so requests stand out from the rest of the UI.
   - **Explicit buttons:** the button reads **"Approve & pay $840"**, not just "Approve".
   - **Reasons required:** rejecting needs a typed reason.
   - **Dry-run tag:** requests from dry runs are marked "Requested during a dry run".
   - **History:** recent decisions are colour-coded on the left edge: green approved, grey rejected, red failed.
6. **A human name on every decision.** "Approving as" is prefilled and saved in the browser. Approve, reject and resolve are disabled without a name, and the backend rejects agent names like `boss`.
7. **Safe defaults with one clear switch.** **Save status decision** controls whether the Boss's status update is written. Leave it off to rehearse a run (dry run).
8. **Calm feedback, no pop-up spam.**
   - **Toasts:** results appear in the corner and fade away, and errors stay longer.
   - **Confirmation:** only the destructive **Reset data** asks for confirmation, in a modal that explains exactly what happens.
9. **Always know if the backend is up.** A green or red dot in the header. If the backend is down, a banner says how to start it.
10. **Black and pink, professional.**
    - **Dark surfaces:** near-black with thin borders.
    - **Pink only where it matters:** primary actions, the selected ticket, live state.
    - **Status colours:** amber for "needs attention", green for "done / money in".
    - **Accessibility:** visible keyboard focus rings, and `aria-live` on the balance and toasts.
