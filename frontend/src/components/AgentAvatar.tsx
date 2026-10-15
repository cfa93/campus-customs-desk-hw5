import { AGENTS } from '../format'
import type { AgentName } from '../types'

export function AgentAvatar({ name, working = false, size = 'md' }: { name: string; working?: boolean; size?: 'sm' | 'md' }) {
  const info = AGENTS[name as AgentName]
  return (
    <span className={`avatar avatar-${name} avatar-${size} ${working ? 'working' : ''}`} title={info?.label ?? name} aria-hidden>
      {info?.short ?? (name === 'human' ? 'YOU' : name.slice(0, 2).toUpperCase())}
    </span>
  )
}
