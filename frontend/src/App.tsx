import { useCallback, useEffect, useRef, useState } from 'react'
import { api, API_URL, ApiError } from './api'
import { ApprovalsPanel } from './components/ApprovalsPanel'
import { Header } from './components/Header'
import { TicketList } from './components/TicketList'
import { TicketPanel } from './components/TicketPanel'
import { APPROVAL_KINDS, money } from './format'
import type { ActivityItem, Approval, Cash, RunState, Ticket, TicketContext } from './types'
import './App.css'

const REFRESH_MS = 8000 // tickets, approvals, cash
const LIVE_MS = 1200 // while agents are running

type Toast = { id: number; tone: 'ok' | 'bad' | 'info'; text: string }

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [connected, setConnected] = useState(true)

  // ?ticket=102 opens that ticket directly (handy for links and screenshots).
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const n = Number(new URLSearchParams(location.search).get('ticket'))
    return Number.isInteger(n) && n > 0 ? n : null
  })
  const [ctx, setCtx] = useState<TicketContext | null>(null)

  const [runIdByTicket, setRunIdByTicket] = useState<Record<number, string>>({})
  const [runStates, setRunStates] = useState<Record<string, RunState>>({})
  const [activities, setActivities] = useState<Record<string, ActivityItem[]>>({})
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  const [approver, setApprover] = useState(() => localStorage.getItem('approver') ?? 'King')
  const [busyApproval, setBusyApproval] = useState<number | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastId = useRef(0)

  const toast = useCallback((tone: Toast['tone'], text: string) => {
    const id = ++toastId.current
    setToasts((t) => [...t, { id, tone, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'bad' ? 9000 : 5000)
  }, [])

  const errorText = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : String(e))

  // ---- shared data ---------------------------------------------------------
  const refreshAll = useCallback(async () => {
    try {
      const [t, a, c] = await Promise.all([api.tickets(), api.approvals(), api.cash()])
      setTickets(t.tickets)
      setApprovals(a.approvals)
      setCash(c)
      setConnected(true)
      setSelectedId((id) => id ?? t.tickets[0]?.id ?? null)
    } catch {
      setConnected(false)
    }
  }, [])

  const loadContext = useCallback(async (id: number) => {
    try {
      setCtx(await api.ticket(id))
    } catch (e) {
      toast('bad', errorText(e))
    }
  }, [toast])

  const fetchRun = useCallback(async (runId: string) => {
    const [run, act] = await Promise.all([api.run(runId), api.activity(runId)])
    setRunStates((s) => ({ ...s, [runId]: run }))
    setActivities((s) => ({ ...s, [runId]: [...act.activity].reverse() })) // oldest first
    return run
  }, [])

  useEffect(() => {
    refreshAll()
    // Pick up a run that is already going (e.g. after a page refresh).
    api
      .runs()
      .then(({ runs }) => {
        const map: Record<number, string> = {}
        for (const r of runs) {
          map[r.ticket_id] ??= r.run_id // newest first
          if (r.status === 'running') setActiveRunId(r.run_id)
        }
        setRunIdByTicket((m) => ({ ...map, ...m }))
        Object.values(map).forEach((id) => fetchRun(id).catch(() => undefined))
      })
      .catch(() => undefined)
    const t = setInterval(refreshAll, REFRESH_MS)
    return () => clearInterval(t)
  }, [refreshAll, fetchRun])

  useEffect(() => {
    if (selectedId != null) loadContext(selectedId)
  }, [selectedId, loadContext])

  // ---- live polling while agents run ---------------------------------------
  useEffect(() => {
    if (!activeRunId) return
    let stopped = false
    const tick = async () => {
      try {
        const run = await fetchRun(activeRunId)
        if (stopped) return
        if (run.status !== 'running') {
          setActiveRunId(null)
          await refreshAll()
          await loadContext(run.ticket_id)
          if (run.status === 'completed') {
            const n = run.approvals_queued.length
            toast('ok', `Agents finished ticket #${run.ticket_id}.` + (n ? ` ${n} request${n > 1 ? 's' : ''} need your approval.` : ''))
          } else toast('bad', `Agent run failed: ${run.error}`)
          return
        }
      } catch {
        /* keep polling */
      }
      if (!stopped) timer = setTimeout(tick, LIVE_MS)
    }
    let timer = setTimeout(tick, 300)
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [activeRunId, fetchRun, refreshAll, loadContext, toast])

  // ---- actions -------------------------------------------------------------
  const runAgents = async (apply: boolean) => {
    if (selectedId == null) return
    try {
      const { run_id } = await api.startRun(selectedId, apply)
      setRunIdByTicket((m) => ({ ...m, [selectedId]: run_id }))
      setActivities((s) => ({ ...s, [run_id]: [] }))
      setActiveRunId(run_id)
      await fetchRun(run_id)
      toast('info', `Agents started on ticket #${selectedId}.`)
    } catch (e) {
      toast('bad', errorText(e))
    }
  }

  const approve = async (a: Approval) => {
    setBusyApproval(a.id)
    try {
      const res = await api.approve(a.id, approver.trim())
      toast(
        'ok',
        res.checking_balance != null
          ? `Paid ${money(a.amount)} (${APPROVAL_KINDS[a.kind]}). Checking is now ${money(res.checking_balance)}.`
          : `Approved ${APPROVAL_KINDS[a.kind] ?? a.kind}.`,
      )
    } catch (e) {
      toast('bad', `Not approved: ${errorText(e)}`)
    } finally {
      setBusyApproval(null)
      await refreshAll()
      if (selectedId != null) loadContext(selectedId)
    }
  }

  const reject = async (a: Approval, reason: string) => {
    setBusyApproval(a.id)
    try {
      await api.reject(a.id, approver.trim(), reason)
      toast('info', `Rejected ${APPROVAL_KINDS[a.kind] ?? a.kind} ${money(a.amount)}. Nothing was paid.`)
    } catch (e) {
      toast('bad', errorText(e))
    } finally {
      setBusyApproval(null)
      await refreshAll()
      if (selectedId != null) loadContext(selectedId)
    }
  }

  const resolve = async (note: string) => {
    if (selectedId == null) return
    try {
      await api.resolve(selectedId, approver.trim(), note || undefined)
      toast('ok', `Ticket #${selectedId} marked resolved.`)
    } catch (e) {
      toast('bad', errorText(e))
    } finally {
      await refreshAll()
      loadContext(selectedId)
    }
  }

  const reset = async () => {
    setConfirmReset(false)
    try {
      const r = await api.reset()
      setRunIdByTicket({})
      setRunStates({})
      setActivities({})
      toast('info', `Database restored to original values.` + (r.approvals_voided ? ` ${r.approvals_voided} pending request(s) voided.` : ''))
    } catch (e) {
      toast('bad', errorText(e))
    } finally {
      await refreshAll()
      if (selectedId != null) loadContext(selectedId)
    }
  }

  const changeApprover = (name: string) => {
    setApprover(name)
    localStorage.setItem('approver', name)
  }

  const selectedRunId = selectedId != null ? runIdByTicket[selectedId] : undefined
  const selectedRun = selectedRunId ? runStates[selectedRunId] ?? null : null
  const runningTicketId = activeRunId ? runStates[activeRunId]?.ticket_id ?? null : null

  return (
    <div className="app">
      <Header cash={cash} approver={approver} onApproverChange={changeApprover} onReset={() => setConfirmReset(true)} connected={connected} />

      {!connected && (
        <div className="banner">
          Can’t reach the backend at <code>{API_URL}</code>. Start it from the <code>backend</code> folder with{' '}
          <code>uvicorn main:app --reload --port 8000</code>.
        </div>
      )}

      <main className="layout">
        <TicketList tickets={tickets} selectedId={selectedId} onSelect={setSelectedId} approvals={approvals} runningTicketId={runningTicketId} />
        <TicketPanel
          key={selectedId ?? 0}
          ctx={ctx && ctx.ticket.id === selectedId ? ctx : null}
          run={selectedRun}
          activity={selectedRunId ? activities[selectedRunId] ?? [] : []}
          approvals={approvals}
          anyRunActive={activeRunId != null}
          approver={approver}
          onRun={runAgents}
          onResolve={resolve}
        />
        <ApprovalsPanel approvals={approvals} approver={approver} onApprove={approve} onReject={reject} busyId={busyApproval} />
      </main>

      {confirmReset && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="reset-title">
          <div className="modal">
            <h2 id="reset-title">Reset to original data?</h2>
            <p>
              This restores <code>campus_customs_new.db</code> from the original: payments are removed, cash goes back to $3,400, and tickets
              reopen. Pending approvals are voided. The audit trail is kept.
            </p>
            <div className="row end">
              <button className="btn ghost" onClick={() => setConfirmReset(false)}>Cancel</button>
              <button className="btn danger" onClick={reset}>Reset data</button>
            </div>
          </div>
        </div>
      )}

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>{t.text}</div>
        ))}
      </div>
    </div>
  )
}
