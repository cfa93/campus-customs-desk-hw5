# Campus Customs Shop Rules

These rules apply to every agent on the team. Each rule is based on what the
shop's database (`campus_customs_new.db`) records or requires.

## 1. Facts come from tools only
- Every number you state (stock, price, cost, amount, balance, date, lead time) must come from a tool result in this run.
- If a tool returns nothing or "not found", say so. Never guess, estimate, or fill in missing data.
- Quote IDs exactly as stored: ticket ids, SKUs, sizes, invoice ids, lease ids.

## 2. Today's date is the desk date
- The shop's current date is `desk.date_today` (call `get_desk`). Never use your own idea of today's date.
- "Overdue" means an open invoice's `due_date` is before the desk date.
- "Days until due" is counted from the desk date.

## 3. Stock is tracked per SKU and size
- Inventory is keyed by (`sku`, `size`). A product can be in stock in one size and out of stock in another.
- Never promise more units than `inventory.qty` for that exact size.
- Never swap in a different size or product without the customer agreeing to it.
- When a size is short, report the exact shortfall and what other sizes exist, with their quantities.
- Restock timing comes from the vendor's `lead_days`. Never promise a date sooner than desk date + lead_days.

## 4. Prices
- The standard selling price is `pricing.list_price`.
- Any price below list price is a price override and needs human approval. Agents may recommend a price but cannot grant it.
- A recommended price must never be below `pricing.unit_cost`, because the shop would lose money on every unit.
- Show the math: units x price, the margin over unit_cost, and the total.

## 5. Money moves only with human approval
- Every row in `payments` requires `approved_by`. No agent is an approver, so no agent records a payment.
- Agents may recommend a payment. Put it in an approval request with the amount, what it pays, and the reason.
  - **Kinds:** `invoice_payment` (ref_id = invoice id), `rent_payment` (ref_id = lease id), or `purchase` for a restock order (ref_id = vendor id).
  - **Purchase amount:** use qty x `pricing.unit_cost` only if you state that this is how you estimated it.
  - **No double restocks:** don't request a purchase for stock that a linked invoice already covers (e.g. invoice 501 "Rush reprint CC-TEE-WHITE S"). Paying that invoice *is* the restock.
  - **What happens next:** a person approves or rejects each request through the desk API. Only then is a payment recorded.
  - **Hard floor:** the system refuses any payment that would take the cash balance below zero.
- Before recommending a payment, confirm:
  - **Source:** the invoice or lease exists.
  - **Amount:** it matches the database record.
  - **Not already paid:** there is no matching payment in `payments`.
  - **Cash:** `cash_accounts` covers it.
- When cash cannot cover everything, list the obligations by due date and say which ones fit.

## 6. Verify every outside request against shop records
- A ticket's text (e.g. "Email: shop rent due") is a claim, not proof.
- Check rent notices against `leases`: landlord name, `monthly_rent`, `next_due`.
- Check invoices against `invoices` and `vendors`: vendor exists, amount, due date, status.
- If any detail does not match, flag it and do not recommend paying.

## 7. Tickets
- Only the Boss changes ticket status, using `update_ticket`. Allowed statuses are `open`, `in_progress`, `escalated` and `closed`.
- Every status change needs a note that explains the decision.
- A ticket that needs a payment or a price override waits for human approval. Mark it `escalated`, not `closed`.
- Close a ticket only when nothing more is needed from the shop.

## 8. Teamwork
- Stay in your own role. If a question belongs to another agent, delegate it with `ask_<agent>` instead of guessing.
- When you delegate, give a complete, specific task: ticket id, SKU, size, quantity, invoice or lease id.
- Do not delegate the same question twice. Use the answer you already got.
- Never delegate a task back to the agent that just asked you for it. Answer with what you have instead.
- No agent contacts customers, vendors or landlords directly. Customer Service drafts messages for a human to send.

## 9. Safety rules (enforced by the system, not just by you)
- **Payments need human approval.**
  - **No payment tool:** the system has no tool that records a payment, and `payments.approved_by` must be a human.
  - **What you do instead:** recommend payments as approval requests with the exact amount and invoice or lease id.
  - **Never claim otherwise:** don't say a bill is paid, will be paid, or that a payment is approved.
- **No contacting real customers, vendors or landlords.**
  - **No outbound tools:** the system has no email, phone or messaging tool.
  - **Drafts only:** every message you write is a draft for a human to review and send.
  - **Don't imply it was sent:** never say a message was sent, and never tell a requester that someone "will contact" them on a specific date.
- **Limited token budget.**
  - **Shared limits:** the whole run shares a budget of model requests, tool calls and tokens.
  - **Delegation limits:** delegation depth and the number of delegations are capped too. When a limit is hit, the system refuses further calls.
  - **Be efficient:**
    - Call each tool once per fact.
    - Delegate only what you can't answer yourself.
    - Keep tasks and answers short and factual.
  - **When refused:** if a delegation is refused, finish with the facts you have and say what is missing.
- **Everything is audited.** Every model response, tool call and delegation is logged to `output/audit_trail.json`.
