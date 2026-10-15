import { useEffect, useRef, useState } from 'react'
import { money } from '../format'
import type { Cash } from '../types'

interface Props {
  cash: Cash | null
  approver: string
  onApproverChange: (name: string) => void
  onReset: () => void
  connected: boolean
}

export function Header({ cash, approver, onApproverChange, onReset, connected }: Props) {
  // Briefly highlight the balance whenever it changes (e.g. after a payment).
  const [flash, setFlash] = useState<'down' | 'up' | null>(null)
  const prev = useRef<number | null>(null)
  useEffect(() => {
    if (cash == null) return
    if (prev.current != null && cash.balance !== prev.current) {
      setFlash(cash.balance < prev.current ? 'down' : 'up')
      const t = setTimeout(() => setFlash(null), 1600)
      prev.current = cash.balance
      return () => clearTimeout(t)
    }
    prev.current = cash.balance
  }, [cash])

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" aria-hidden>C</span>
        <div>
          <div className="brand-name">Campus Customs</div>
          <div className="brand-sub">Desk operations</div>
        </div>
      </div>

      <div className="topbar-meta">
        <span className={`conn ${connected ? 'on' : 'off'}`}>{connected ? 'Backend connected' : 'Backend offline'}</span>
        {cash && <span className="chip">Desk date {cash.desk_date}</span>}
      </div>

      <div className={`balance ${flash ? `flash-${flash}` : ''}`} aria-live="polite">
        <div className="balance-label">Checking balance</div>
        <div className="balance-value">{cash ? money(cash.balance) : '—'}</div>
        {cash && (
          <div className="balance-sub" title="Balance minus all open invoices and the next rent payment">
            After open bills &amp; next rent: <b className={cash.after_all_obligations < 0 ? 'neg' : ''}>{money(cash.after_all_obligations)}</b>
          </div>
        )}
      </div>

      <div className="approver">
        <label htmlFor="approver">Approving as</label>
        <input
          id="approver"
          value={approver}
          onChange={(e) => onApproverChange(e.target.value)}
          placeholder="Your name"
          spellCheck={false}
        />
      </div>

      <button className="btn ghost small" onClick={onReset} title="Restore the working database to the original values">
        Reset data
      </button>
    </header>
  )
}
