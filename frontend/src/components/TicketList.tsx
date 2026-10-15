import { TICKET_TYPES } from '../format'
import type { Approval, Ticket } from '../types'
import { StatusBadge } from './StatusBadge'

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  onSelect: (id: number) => void
  approvals: Approval[]
  runningTicketId: number | null
}

export function TicketList({ tickets, selectedId, onSelect, approvals, runningTicketId }: Props) {
  return (
    <nav className="panel ticket-list" aria-label="Tickets">
      <div className="panel-head">
        <h2>Tickets</h2>
        <span className="muted">{tickets.length}</span>
      </div>
      <ul>
        {tickets.map((t) => {
          const pending = approvals.filter((a) => a.ticket_id === t.id && a.status === 'pending').length
          return (
            <li key={t.id}>
              <button
                className={`ticket-item ${selectedId === t.id ? 'selected' : ''}`}
                onClick={() => onSelect(t.id)}
                aria-current={selectedId === t.id}
              >
                <div className="ticket-item-top">
                  <span className="ticket-id">#{t.id}</span>
                  <StatusBadge status={t.status} />
                </div>
                <div className="ticket-subject">{t.subject}</div>
                <div className="ticket-meta">
                  {TICKET_TYPES[t.type] ?? t.type} · {t.requester}
                </div>
                <div className="ticket-flags">
                  {runningTicketId === t.id && <span className="flag running">Agents working…</span>}
                  {pending > 0 && <span className="flag pending">{pending} awaiting approval</span>}
                </div>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
