import type { ReactNode } from 'react'

import type { Loaded } from './useStats'

interface PanelProps {
  /** The question the panel answers — that is its title. */
  question: string
  /** Spans both columns from 720 px. */
  wide?: boolean
  children: ReactNode
}

/** The shared panel shell: green left border, question as title. */
export function Panel({ question, wide = false, children }: PanelProps) {
  return (
    <section className={wide ? 'dash-panel dash-panel--wide' : 'dash-panel'}>
      <h2>{question}</h2>
      {children}
    </section>
  )
}

/** Loading / failed line for a resource that has no data yet; null once data is there. */
export function Status<T>({ state }: { state: Loaded<T> }) {
  if (state.data) return null
  if (state.error === 'failed') return <p className="dash-status dash-status--error">Data unavailable.</p>
  if (state.error === 'unauthorized') return <p className="dash-status">Session expired.</p>
  return <p className="dash-status">Loading…</p>
}
