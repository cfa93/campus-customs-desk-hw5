import { useEffect, useRef, type ReactNode } from 'react'
import { agentLabel, argsText, time } from '../format'
import type { ActivityItem } from '../types'
import { AgentAvatar } from './AgentAvatar'

/** One line per agent step: what it is doing (tools, delegations) and what it says. */
function describe(item: ActivityItem): { kind: string; text: ReactNode } {
  switch (item.event) {
    case 'run_start':
      return { kind: 'start', text: <>Started: <q>{item.message}</q></> }
    case 'model_response':
      if (item.message) return { kind: 'say', text: <q>{item.message}</q> }
      return {
        kind: 'think',
        text: item.tools_requested?.length ? <>Decided to use {item.tools_requested.map((t) => <code key={t}>{t.replace('final_result', 'answer')}</code>)}</> : 'Thinking…',
      }
    case 'tool_call':
      return { kind: 'tool', text: <>Looked up <code>{item.tool}({argsText(item.args)})</code></> }
    case 'tool_blocked':
      return { kind: 'blocked', text: <>Blocked from <code>{item.tool}</code> (not allowed for this role)</> }
    case 'delegation':
      return { kind: 'ask', text: <>Asked <b>{agentLabel(item.to ?? '')}</b>: <q>{item.message}</q></> }
    case 'delegation_refused':
      return { kind: 'blocked', text: <>Couldn’t ask <b>{agentLabel(item.to ?? '')}</b>: loop limit reached</> }
    case 'run_end':
      return { kind: 'done', text: <>Finished: <q>{item.message}</q></> }
    case 'approval_created':
      return { kind: 'approval', text: 'Sent a request for human approval' }
    case 'error':
      return { kind: 'blocked', text: <>Error: {item.message}</> }
    default:
      return { kind: 'other', text: item.event }
  }
}

export function LiveFeed({ items, running }: { items: ActivityItem[]; running: boolean }) {
  const end = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLOListElement>(null)

  // Follow new steps while running, unless the user scrolled up to read.
  useEffect(() => {
    const el = box.current
    if (!el || !running) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    if (nearBottom) end.current?.scrollIntoView({ block: 'nearest' })
  }, [items.length, running])

  if (!items.length) {
    return <div className="empty">{running ? 'Waiting for the first step…' : 'No activity for this run.'}</div>
  }
  return (
    <ol className="feed" ref={box}>
      {items.map((item, i) => {
        const d = describe(item)
        return (
          <li key={i} className={`feed-item kind-${d.kind}`} style={{ marginLeft: `${item.depth * 18}px` }}>
            <AgentAvatar name={item.agent} size="sm" />
            <div className="feed-body">
              <div className="feed-head">
                <b>{agentLabel(item.agent)}</b>
                <span className="feed-time">{time(item.timestamp)}</span>
              </div>
              <div className="feed-text">{d.text}</div>
            </div>
          </li>
        )
      })}
      {running && (
        <li className="feed-item kind-pending">
          <span className="dots" aria-label="working">
            <i />
            <i />
            <i />
          </span>
        </li>
      )}
      <div ref={end} />
    </ol>
  )
}
