import { agentLabel } from '../format'
import type { Delegation } from '../types'
import { AgentAvatar } from './AgentAvatar'

/** Who handed work to whom, in order. Nested hand-offs are indented. */
export function RunFlow({ delegations }: { delegations: Delegation[] }) {
  if (!delegations.length) return <div className="empty small">The Boss is reading the ticket…</div>
  return (
    <ol className="flow">
      {delegations.map((d, i) => (
        <li key={i} style={{ marginLeft: `${(d.depth - 1) * 22}px` }} className={d.done ? 'done' : 'live'}>
          <AgentAvatar name={d.from} size="sm" />
          <span className="flow-arrow">→</span>
          <AgentAvatar name={d.to} size="sm" working={!d.done} />
          <span className="flow-text">
            <span>
              <b>{agentLabel(d.from)}</b> asked <b>{agentLabel(d.to)}</b>
            </span>
            <span className="flow-task" title={d.task}>{d.task}</span>
          </span>
          <span className={`pill ${d.done ? 'pill-done' : 'pill-live'}`}>{d.done ? 'answered' : 'working'}</span>
        </li>
      ))}
    </ol>
  )
}
