// Shapes returned by the FastAPI backend (backend/main.py).

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  status: string
  notes: string | null
  created_at: string
}

export interface TicketsResponse {
  desk_date: string
  count: number
  tickets: Ticket[]
}

export interface InventoryRow {
  sku: string
  name: string
  size: string
  qty: number
  location: string
}

/** GET /tickets/{id}: the ticket plus every record it links to. */
export interface TicketContext {
  ticket: Ticket & { sku: string | null; size: string | null; qty: number | null; lease_id: number | null; invoice_id: number | null }
  desk_date: string
  cash_accounts: { name: string; balance: number; date: string }[]
  inventory_requested_size?: InventoryRow | null
  inventory_all_sizes?: InventoryRow[]
  pricing?: { sku: string; unit_cost: number; list_price: number } | null
  invoice?: { id: number; vendor_id: number; amount: number; due_date: string; status: string; description: string | null } | null
  vendor?: { id: number; name: string; specialty: string; lead_days: number } | null
  invoice_payments?: unknown[]
  lease?: { id: number; space_name: string; landlord: string; monthly_rent: number; next_due: string } | null
  lease_payments?: unknown[]
  warnings: string[]
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  desk_date: string
  open_invoices_total: number
  rent_total: number
  after_all_obligations: number
}

export interface Approval {
  id: number
  created_at: string
  run_id: string
  dry_run_request: boolean
  ticket_id: number | null
  kind: string
  ref_id: number | null
  amount: number | null
  reason: string
  status: 'pending' | 'approved' | 'rejected' | 'failed' | 'voided'
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
  payment: Record<string, unknown> | null
  error: string | null
}

export interface Fact {
  statement: string
  source_table: string
}

export interface AgentReport {
  agent: AgentName
  answer: string
  facts: Fact[]
  recommended_actions: string[]
  needs_human_approval: boolean
  approval_reason: string | null
  customer_message: string | null
}

export interface TicketDecision {
  ticket_id: number
  owner: AgentName
  new_status: string
  decision: string
  customer_message: string | null
}

export interface ApprovalRequest {
  kind: string
  ticket_id: number | null
  ref_id: number | null
  amount: number | null
  reason: string
}

export interface BossPlan {
  summary: string
  decisions: TicketDecision[]
  approvals_needed: ApprovalRequest[]
  risks: string[]
}

export interface AgentSummary {
  agent: AgentName
  status: 'working' | 'done'
  model_responses: number
  tools: { tool: string; count: number }[]
  asked: { to: AgentName; task: string }[]
  tasks: { from: AgentName; task: string; depth: number; report: AgentReport | null; error: string | null }[]
  plan: BossPlan | null
}

export interface Delegation {
  from: AgentName
  to: AgentName
  depth: number
  task: string
  done: boolean
}

export interface RunState {
  run_id: string
  ticket_id: number
  status: 'running' | 'completed' | 'failed'
  dry_run: boolean
  started_at: string
  finished_at: string | null
  plan: BossPlan | null
  usage: { requests: number; tool_calls: number; input_tokens: number; output_tokens: number } | null
  approvals_queued: Approval[]
  error: string | null
  delegations: Delegation[]
  agents: AgentSummary[]
}

export interface RunListItem {
  run_id: string
  ticket_id: number
  status: RunState['status']
  dry_run: boolean
  started_at: string
  finished_at: string | null
  error: string | null
}

export interface ActivityItem {
  timestamp: string
  run_id: string
  agent: string
  event: string
  depth: number
  message?: string | null
  tools_requested?: string[]
  tool?: string
  args?: string
  result?: string
  to?: string
  usage?: Record<string, number> | null
}
