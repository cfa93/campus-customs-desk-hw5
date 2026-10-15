import { useState } from 'react'
import { AGENTS, agentLabel, APPROVAL_KINDS, money } from '../format'
import type { AgentSummary, AgentName } from '../types'
import { AgentAvatar } from './AgentAvatar'
import { StatusBadge } from './StatusBadge'

const ORDER: AgentName[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

export function AgentSummaries({ agents, ticketId }: { agents: AgentSummary[]; ticketId: number }) {
  const sorted = [...agents].sort((a, b) => ORDER.indexOf(a.agent) - ORDER.indexOf(b.agent))
  const idle = ORDER.filter((n) => !agents.some((a) => a.agent === n))
  return (
    <div className="agent-grid">
      {sorted.map((a) => (
        <AgentCard key={a.agent} summary={a} ticketId={ticketId} />
      ))}
      {idle.length > 0 && (
        <div className="agent-idle">
          Not involved: {idle.map((n) => AGENTS[n].label).join(', ')}
        </div>
      )}
    </div>
  )
}

function AgentCard({ summary: a, ticketId }: { summary: AgentSummary; ticketId: number }) {
  const [open, setOpen] = useState(a.agent === 'boss')
  const working = a.status === 'working'
  const decision = a.plan?.decisions.find((d) => d.ticket_id === ticketId) ?? a.plan?.decisions[0]
  const reports = a.tasks.filter((t) => t.report)
  const lastReport = reports[reports.length - 1]?.report

  return (
    <article className={`agent-card ${working ? 'is-working' : ''}`}>
      <header className="agent-card-head" onClick={() => setOpen(!open)}>
        <AgentAvatar name={a.agent} working={working} />
        <div className="agent-card-title">
          <b>{AGENTS[a.agent].label}</b>
          <span className="muted">{AGENTS[a.agent].role}</span>
        </div>
        <span className={`pill ${working ? 'pill-live' : 'pill-done'}`}>{working ? 'Working' : 'Done'}</span>
        <button className="chevron" aria-expanded={open} aria-label={open ? 'Collapse' : 'Expand'}>
          {open ? '−' : '+'}
        </button>
      </header>

      {/* One-line headline that is always visible */}
      <p className="agent-headline">
        {a.plan ? a.plan.summary : lastReport ? lastReport.answer : working ? 'Working on it…' : '—'}
      </p>

      <div className="agent-stats">
        <span>{a.model_responses} model steps</span>
        <span>{a.tools.reduce((n, t) => n + t.count, 0)} lookups</span>
        {a.asked.length > 0 && <span>asked {a.asked.map((x) => agentLabel(x.to)).join(', ')}</span>}
      </div>

      {open && (
        <div className="agent-detail">
          {a.tools.length > 0 && (
            <div className="tool-chips">
              {a.tools.map((t) => (
                <code key={t.tool}>
                  {t.tool}
                  {t.count > 1 && <sup>×{t.count}</sup>}
                </code>
              ))}
            </div>
          )}

          {a.plan && (
            <div className="plan">
              {decision && (
                <div className="decision">
                  <div className="decision-head">
                    Decision <StatusBadge status={decision.new_status} />
                  </div>
                  <p>{decision.decision}</p>
                  {decision.customer_message && <Draft text={decision.customer_message} />}
                </div>
              )}
              {a.plan.approvals_needed.length > 0 && (
                <div className="kv">
                  <h4>Asked a human to approve</h4>
                  <ul>
                    {a.plan.approvals_needed.map((r, i) => (
                      <li key={i}>
                        <b>{APPROVAL_KINDS[r.kind] ?? r.kind}</b> {money(r.amount)}: {r.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {a.plan.risks.length > 0 && (
                <div className="kv">
                  <h4>Risks flagged</h4>
                  <ul>
                    {a.plan.risks.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {a.tasks.map((t, i) => (
            <div key={i} className="task">
              <div className="task-from">
                Task from <b>{agentLabel(t.from)}</b>
              </div>
              <q className="task-text">{t.task}</q>
              {t.error && <div className="decided-error">{t.error}</div>}
              {t.report && (
                <>
                  <p className="task-answer">{t.report.answer}</p>
                  {t.report.facts.length > 0 && (
                    <ul className="facts-list">
                      {t.report.facts.map((f, j) => (
                        <li key={j}>
                          {f.statement} <span className="src">{f.source_table}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {t.report.recommended_actions.length > 0 && (
                    <div className="kv">
                      <h4>Recommends</h4>
                      <ul>
                        {t.report.recommended_actions.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {t.report.customer_message && <Draft text={t.report.customer_message} />}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

function Draft({ text }: { text: string }) {
  return (
    <div className="draft">
      <div className="draft-label">Draft message · not sent</div>
      <p>{text}</p>
    </div>
  )
}
