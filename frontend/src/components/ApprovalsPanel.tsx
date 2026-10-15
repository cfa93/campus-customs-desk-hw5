import { useState } from 'react'
import { APPROVAL_KINDS, money } from '../format'
import type { Approval } from '../types'

interface Props {
  approvals: Approval[]
  approver: string
  onApprove: (a: Approval) => Promise<void>
  onReject: (a: Approval, reason: string) => Promise<void>
  busyId: number | null
}

const MOVES_MONEY = new Set(['invoice_payment', 'rent_payment', 'purchase'])

function target(a: Approval) {
  if (a.kind === 'invoice_payment') return `Invoice #${a.ref_id}`
  if (a.kind === 'rent_payment') return `Lease #${a.ref_id}`
  if (a.kind === 'purchase') return `Vendor #${a.ref_id}`
  return a.ref_id != null ? `Ref #${a.ref_id}` : ''
}

export function ApprovalsPanel({ approvals, approver, onApprove, onReject, busyId }: Props) {
  const [rejecting, setRejecting] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const pending = approvals.filter((a) => a.status === 'pending')
  const decided = approvals.filter((a) => a.status !== 'pending').slice(-6).reverse()
  const noName = approver.trim().length < 2

  return (
    <aside className="panel approvals" aria-label="Human approvals">
      <div className="panel-head">
        <h2>Human approvals</h2>
        <span className={`count ${pending.length ? 'hot' : ''}`}>{pending.length}</span>
      </div>
      <p className="panel-note">Agents can only request payments. Nothing moves until a person approves here.</p>

      {pending.length === 0 && <div className="empty">No requests waiting.</div>}

      {pending.map((a) => (
        <article key={a.id} className="approval">
          <div className="approval-top">
            <span className="approval-kind">{APPROVAL_KINDS[a.kind] ?? a.kind}</span>
            <span className="approval-amount">{money(a.amount)}</span>
          </div>
          <div className="approval-target">
            {target(a)} {a.ticket_id != null && <span className="muted">· ticket #{a.ticket_id}</span>}
          </div>
          <p className="approval-reason">{a.reason}</p>
          {a.dry_run_request && <div className="hint">Requested during a dry run.</div>}

          {rejecting === a.id ? (
            <form
              className="reject-form"
              onSubmit={async (e) => {
                e.preventDefault()
                await onReject(a, reason)
                setRejecting(null)
                setReason('')
              }}
            >
              <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason for rejecting" />
              <div className="row">
                <button type="submit" className="btn danger small" disabled={reason.trim().length < 2 || busyId === a.id}>
                  Confirm reject
                </button>
                <button type="button" className="btn ghost small" onClick={() => setRejecting(null)}>
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <div className="row">
              <button
                className="btn primary small"
                disabled={noName || busyId === a.id}
                onClick={() => onApprove(a)}
                title={noName ? 'Enter your name at the top first' : `Approve as ${approver}`}
              >
                {busyId === a.id ? 'Approving…' : MOVES_MONEY.has(a.kind) ? `Approve & pay ${money(a.amount)}` : 'Approve'}
              </button>
              <button className="btn ghost small" disabled={noName || busyId === a.id} onClick={() => setRejecting(a.id)}>
                Reject
              </button>
            </div>
          )}
        </article>
      ))}

      {decided.length > 0 && (
        <>
          <h3 className="subhead">Recent decisions</h3>
          <ul className="decided">
            {decided.map((a) => (
              <li key={a.id} className={`decided-${a.status}`}>
                <div>
                  <b>{APPROVAL_KINDS[a.kind] ?? a.kind}</b> {money(a.amount)} <span className="muted">· {target(a)}</span>
                </div>
                <div className="decided-status">
                  {a.status}
                  {a.decided_by && ` by ${a.decided_by}`}
                </div>
                {a.error && <div className="decided-error">{a.error}</div>}
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  )
}
