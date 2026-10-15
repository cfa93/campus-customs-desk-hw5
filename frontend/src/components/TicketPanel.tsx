import { useState } from 'react'
import { TICKET_TYPES, time } from '../format'
import type { ActivityItem, Approval, RunState, TicketContext } from '../types'
import { AgentSummaries } from './AgentSummaries'
import { LiveFeed } from './LiveFeed'
import { RunFlow } from './RunFlow'
import { StatusBadge } from './StatusBadge'
import { TicketFacts } from './TicketFacts'

interface Props {
  ctx: TicketContext | null
  run: RunState | null
  activity: ActivityItem[]
  approvals: Approval[]
  anyRunActive: boolean
  approver: string
  onRun: (apply: boolean) => void
  onResolve: (note: string) => Promise<void>
}

export function TicketPanel({ ctx, run, activity, approvals, anyRunActive, approver, onRun, onResolve }: Props) {
  const [apply, setApply] = useState(true)
  // ?tab=summary opens the Agent summaries tab directly.
  const [tab, setTab] = useState<'live' | 'summary'>(() =>
    new URLSearchParams(location.search).get('tab') === 'summary' ? 'summary' : 'live',
  )
  const [resolveNote, setResolveNote] = useState('')
  const [confirmResolve, setConfirmResolve] = useState(false)

  if (!ctx) return <section className="panel main-panel"><div className="empty">Loading ticket…</div></section>

  const t = ctx.ticket
  const running = run?.status === 'running'
  const pending = approvals.filter((a) => a.ticket_id === t.id && a.status === 'pending')
  const resolved = t.status === 'closed'
  const canResolve = !resolved && !running && pending.length === 0 && approver.trim().length >= 2
  const resolveHint = resolved
    ? 'Already resolved'
    : running
      ? 'Wait for the agents to finish'
      : pending.length
        ? `Approve or reject ${pending.length} pending request${pending.length > 1 ? 's' : ''} first`
        : approver.trim().length < 2
          ? 'Enter your name at the top first'
          : 'Close this ticket'

  return (
    <section className="panel main-panel" aria-label={`Ticket ${t.id}`}>
      <div className="ticket-head">
        <div>
          <div className="eyebrow">
            {TICKET_TYPES[t.type] ?? t.type} · from {t.requester}
          </div>
          <h1>
            #{t.id} {t.subject}
          </h1>
        </div>
        <StatusBadge status={t.status} />
      </div>

      <blockquote className="request">{(t.notes ?? '').split('\n')[0]}</blockquote>

      <TicketFacts ctx={ctx} />

      <div className="actions">
        <button className="btn primary" onClick={() => { setTab('live'); onRun(apply) }} disabled={anyRunActive || resolved}>
          {running ? 'Agents working…' : run ? 'Run agents again' : 'Run agents'}
        </button>
        <label className="toggle" title="When on, the Boss's status decision is saved to the database. When off, it's only previewed.">
          <input type="checkbox" checked={apply} onChange={(e) => setApply(e.target.checked)} disabled={anyRunActive} />
          <span>Save status decision</span>
        </label>
        <div className="spacer" />
        {confirmResolve ? (
          <form
            className="resolve-form"
            onSubmit={async (e) => {
              e.preventDefault()
              await onResolve(resolveNote)
              setConfirmResolve(false)
              setResolveNote('')
            }}
          >
            <input autoFocus value={resolveNote} onChange={(e) => setResolveNote(e.target.value)} placeholder="Resolution note (optional)" />
            <button className="btn success small" type="submit">Confirm</button>
            <button className="btn ghost small" type="button" onClick={() => setConfirmResolve(false)}>Cancel</button>
          </form>
        ) : (
          <button className="btn success" disabled={!canResolve} title={resolveHint} onClick={() => setConfirmResolve(true)}>
            {resolved ? 'Resolved ✓' : 'Mark resolved'}
          </button>
        )}
      </div>
      {!resolved && !canResolve && !running && pending.length > 0 && <div className="hint right">{resolveHint}</div>}

      {run ? (
        <div className="run">
          <div className="run-head">
            <div className="tabs" role="tablist">
              <button role="tab" aria-selected={tab === 'live'} className={tab === 'live' ? 'active' : ''} onClick={() => setTab('live')}>
                Live activity <span className="muted">{activity.length}</span>
              </button>
              <button role="tab" aria-selected={tab === 'summary'} className={tab === 'summary' ? 'active' : ''} onClick={() => setTab('summary')}>
                Agent summaries <span className="muted">{run.agents.length}</span>
              </button>
            </div>
            <div className="run-meta">
              <span className={`pill ${running ? 'pill-live' : run.status === 'failed' ? 'pill-bad' : 'pill-done'}`}>
                {running ? 'Running' : run.status === 'failed' ? 'Failed' : 'Finished'}
              </span>
              {run.dry_run && <span className="pill">Dry run</span>}
              <span className="muted">started {time(run.started_at)}</span>
              {run.usage && <span className="muted">· {run.usage.requests} model calls · {(run.usage.input_tokens + run.usage.output_tokens).toLocaleString()} tokens</span>}
            </div>
          </div>

          {run.error && <div className="alert">{run.error}</div>}

          {tab === 'live' ? (
            <div className="live-grid">
              <div>
                <h3 className="subhead">Who’s working</h3>
                <RunFlow delegations={run.delegations} />
              </div>
              <div>
                <h3 className="subhead">Step by step</h3>
                <LiveFeed items={activity} running={running} />
              </div>
            </div>
          ) : (
            <AgentSummaries agents={run.agents} ticketId={t.id} />
          )}
        </div>
      ) : (
        <div className="empty big">
          Run the agents to see the Boss pick the right specialists, what each one looks up and says, and any payments they ask you to approve.
        </div>
      )}
    </section>
  )
}
