import type { AgentName } from './types'

export const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 2 })

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export const AGENTS: Record<AgentName, { label: string; short: string; role: string }> = {
  boss: { label: 'Boss', short: 'BS', role: 'Coordinates the team and decides' },
  inventory: { label: 'Inventory', short: 'IN', role: 'Stock, sizes, restock lead times' },
  accounting: { label: 'Accounting', short: 'AC', role: 'Invoices, cash, pricing' },
  facilities: { label: 'Facilities', short: 'FA', role: 'Lease and rent checks' },
  customer_service: { label: 'Customer Service', short: 'CS', role: 'Drafts replies to requesters' },
}

export const agentLabel = (name: string) => AGENTS[name as AgentName]?.label ?? (name === 'human' ? 'You' : name)

export const TICKET_TYPES: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

export const STATUS: Record<string, { label: string; tone: 'neutral' | 'info' | 'warn' | 'ok' }> = {
  open: { label: 'Open', tone: 'neutral' },
  in_progress: { label: 'In progress', tone: 'info' },
  escalated: { label: 'Needs approval', tone: 'warn' },
  closed: { label: 'Resolved', tone: 'ok' },
}

export const APPROVAL_KINDS: Record<string, string> = {
  invoice_payment: 'Invoice payment',
  rent_payment: 'Rent payment',
  purchase: 'Purchase',
  price_override: 'Price override',
  other: 'Other',
}

/** Turn a logged JSON args string into "key=value, key=value". */
export function argsText(args: string | undefined): string {
  if (!args) return ''
  try {
    const obj = JSON.parse(args)
    if (obj && typeof obj === 'object') {
      return Object.entries(obj)
        .filter(([k]) => k !== 'dry_run')
        .map(([k, v]) => `${k}=${typeof v === 'string' ? `"${v}"` : JSON.stringify(v)}`)
        .join(', ')
    }
  } catch {
    /* not JSON */
  }
  return args
}
