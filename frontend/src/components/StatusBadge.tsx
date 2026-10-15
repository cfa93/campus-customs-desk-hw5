import { STATUS } from '../format'

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, tone: 'neutral' as const }
  return <span className={`badge tone-${s.tone}`}>{s.label}</span>
}
