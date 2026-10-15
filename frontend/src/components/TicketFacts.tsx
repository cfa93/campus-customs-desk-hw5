import type { ReactNode } from 'react'
import { money } from '../format'
import type { TicketContext } from '../types'

/** Key database facts for a ticket, straight from GET /tickets/{id}. */
export function TicketFacts({ ctx }: { ctx: TicketContext }) {
  const t = ctx.ticket
  const facts: { label: string; value: ReactNode; tone?: 'warn' }[] = []

  if (t.sku) {
    const req = ctx.inventory_requested_size
    facts.push({ label: 'Item', value: `${req?.name ?? t.sku} · size ${t.size} · qty ${t.qty}` })
    facts.push({
      label: `Stock (${t.size})`,
      value: req ? `${req.qty} in ${req.location}` : 'not found',
      tone: req && t.qty != null && req.qty < t.qty ? 'warn' : undefined,
    })
    const others = (ctx.inventory_all_sizes ?? []).filter((r) => r.size !== t.size)
    if (others.length) facts.push({ label: 'Other sizes', value: others.map((r) => `${r.size} ${r.qty}`).join(' · ') })
    if (ctx.pricing) facts.push({ label: 'Price', value: `List ${money(ctx.pricing.list_price)} · cost ${money(ctx.pricing.unit_cost)}` })
  }
  if (ctx.invoice) {
    facts.push({
      label: `Invoice #${ctx.invoice.id}`,
      value: `${money(ctx.invoice.amount)} · due ${ctx.invoice.due_date} · ${ctx.invoice.status}`,
      tone: ctx.invoice.status === 'open' && ctx.invoice.due_date < ctx.desk_date ? 'warn' : undefined,
    })
    if (ctx.vendor) facts.push({ label: 'Vendor', value: `${ctx.vendor.name} · ${ctx.vendor.lead_days} lead days` })
  }
  if (ctx.lease) {
    facts.push({ label: `Lease #${ctx.lease.id}`, value: `${ctx.lease.space_name} · ${ctx.lease.landlord}` })
    facts.push({ label: 'Rent', value: `${money(ctx.lease.monthly_rent)} · next due ${ctx.lease.next_due}` })
  }

  return (
    <div className="facts">
      <dl>
        {facts.map((f) => (
          <div key={f.label} className={f.tone === 'warn' ? 'warn' : ''}>
            <dt>{f.label}</dt>
            <dd>{f.value}</dd>
          </div>
        ))}
      </dl>
      {ctx.warnings.length > 0 && (
        <ul className="warnings">
          {ctx.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
