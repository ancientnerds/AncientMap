import { createContext, type MouseEvent, type ReactNode, useContext, useState } from 'react'

import type { Loaded } from './useStats'

interface PanelProps {
  /** The question the panel answers — that is its title. */
  question: string
  /** Spans both columns from 720 px. */
  wide?: boolean
  children: ReactNode
}

/** Whether the panel around a piece of text has its explanations open. */
const ExplainOpen = createContext(false)

/** The panel's anchor, from its question: "Is the audience growing?" →
 *  "is-the-audience-growing". The page's jump bar links to it. */
export function panelId(question: string): string {
  return question
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

/** What a click inside a panel does on its own; such a click does not also
 *  open or close the explanations. */
const OWN_CLICK = 'a, button, summary, input, select, textarea, label'

/**
 * The shared panel shell: green left border, question as title. The numbers
 * show; the texts that explain them stay closed until the founder clicks the
 * panel (owner, 2026-10-09: "Erklärtexte standardmäßig aus, per Klick auf den
 * Bereich"). The title is the keyboard way in, a button with aria-expanded.
 */
export function Panel({ question, wide = false, children }: PanelProps) {
  const [open, setOpen] = useState(false)
  const onPanelClick = (e: MouseEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).closest(OWN_CLICK)) return
    // Selecting a number to copy it is reading, not asking for the method.
    if (window.getSelection()?.toString()) return
    setOpen(o => !o)
  }
  const classes = ['dash-panel', wide && 'dash-panel--wide', open && 'dash-panel--explained'].filter(Boolean)
  return (
    <section id={panelId(question)} className={classes.join(' ')} onClick={onPanelClick}>
      <h2>
        <button type="button" className="dash-explain-toggle" aria-expanded={open} onClick={() => setOpen(o => !o)}>
          {question}
        </button>
      </h2>
      <ExplainOpen.Provider value={open}>{children}</ExplainOpen.Provider>
    </section>
  )
}

/** A text that explains the numbers rather than being one: closed until its
 *  panel is clicked. Closed means `hidden`, not absent - the SSR tests and a
 *  search on the page still read it. */
export function Explain({ children }: { children: ReactNode }) {
  const open = useContext(ExplainOpen)
  return (
    <div className="dash-explain" hidden={!open}>
      {children}
    </div>
  )
}

/** The method behind a panel's numbers. On a phone the page ran to 16,500 px
 *  when every panel answered every question in the open (2026-09-25): the
 *  numbers stay visible, the reasoning opens with the panel's other texts. */
export function HowCounted({ children }: { children: ReactNode }) {
  return (
    <Explain>
      <p className="dash-note dash-how">
        <b>How this is counted.</b> {children}
      </p>
    </Explain>
  )
}

/** Loading / failed line for a resource that has no data yet; null once data is there. */
export function Status<T>({ state }: { state: Loaded<T> }) {
  if (state.data) return null
  if (state.error === 'failed') return <p className="dash-status dash-status--error">Data unavailable.</p>
  if (state.error === 'unauthorized') return <p className="dash-status">Session expired.</p>
  return <p className="dash-status">Loading…</p>
}
