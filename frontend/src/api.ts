import type {
  ActivityItem,
  Approval,
  Cash,
  RunListItem,
  RunState,
  Ticket,
  TicketContext,
  TicketsResponse,
} from './types'

// FastAPI backend (backend/main.py). It allows requests from http://localhost:5173 (CORS).
// Override with VITE_API_URL in frontend/.env if the backend runs elsewhere.
export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const BASE = API_URL.replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, { headers: { 'Content-Type': 'application/json' }, ...init })
  } catch {
    throw new ApiError(`Cannot reach the backend at ${API_URL}. Is it running?`, 0)
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message ?? (Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join('; ') : res.statusText)
    throw new ApiError(message || `Request failed (${res.status})`, res.status)
  }
  return body as T
}

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) })

export const api = {
  tickets: () => request<TicketsResponse>('/tickets'),
  ticket: (id: number) => request<TicketContext>(`/tickets/${id}`),
  startRun: (id: number, apply: boolean) =>
    post<{ run_id: string; status: string; dry_run: boolean }>(`/tickets/${id}/runs`, { apply }),
  run: (runId: string) => request<RunState>(`/runs/${runId}`),
  runs: () => request<{ runs: RunListItem[] }>('/runs'),
  activity: (runId: string, limit = 500) =>
    request<{ count: number; activity: ActivityItem[] }>(`/activity?run_id=${encodeURIComponent(runId)}&limit=${limit}`),
  approvals: () => request<{ approvals: Approval[] }>('/approvals'),
  approve: (id: number, approvedBy: string) =>
    post<{ approval: Approval; checking_balance?: number }>(`/approvals/${id}/approve`, { approved_by: approvedBy }),
  reject: (id: number, rejectedBy: string, reason: string) =>
    post<{ approval: Approval }>(`/approvals/${id}/reject`, { rejected_by: rejectedBy, reason }),
  resolve: (id: number, resolvedBy: string, note?: string) =>
    post<{ ticket: Ticket }>(`/tickets/${id}/resolve`, { resolved_by: resolvedBy, note }),
  cash: () => request<Cash>('/cash'),
  reset: () => post<{ ok: boolean; approvals_voided: number }>('/reset'),
}
