import { fmtInt } from './format'

export interface BarItem {
  key: string
  label: string
  value: number
  /** Text after the value, e.g. a share. */
  hint?: string
  /** 'warn' paints the row's hint red — a search that found nothing. */
  tone?: 'warn'
  href?: string
}

interface BarListProps {
  items: BarItem[]
  /** Shown when the list is empty. */
  empty: string
}

/**
 * A ranked list with one thin bar per row, scaled to the largest value. The
 * label carries identity, the bar the magnitude, the number sits in text ink.
 */
export function BarList({ items, empty }: BarListProps) {
  if (items.length === 0) return <p className="dash-empty">{empty}</p>
  const max = Math.max(...items.map(i => i.value), 1)
  return (
    <ul className="dash-bars">
      {items.map(item => (
        <li key={item.key} className="dash-bar">
          <span className="dash-bar-label" title={item.label}>
            {item.href ? <a href={item.href}>{item.label}</a> : item.label}
          </span>
          <span className="dash-bar-value">{fmtInt(item.value)}</span>
          {/* A sibling of the value, not a child of it: the hint is the longest
              text in most rows, and inside the auto-sized value column it ate
              the label's width (dashboard.css, .dash-bar-hint). */}
          {item.hint && (
            <span className={`dash-bar-hint${item.tone === 'warn' ? ' dash-bar-hint--warn' : ''}`}>
              {item.hint}
            </span>
          )}
          <span className="dash-bar-track" aria-hidden="true">
            <span className="dash-bar-fill" style={{ width: `${(item.value / max) * 100}%` }} />
          </span>
        </li>
      ))}
    </ul>
  )
}
