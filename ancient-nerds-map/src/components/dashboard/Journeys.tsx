import { Fragment } from 'react'

import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import type { JourneysData } from './types'
import type { Loaded } from './useStats'

/** The separator api/services/founders_stats.py journeys() joins the steps with. */
const ARROW = ' → '

/**
 * The event names that can appear as a step — JOURNEY_EVENTS in
 * api/services/founders_stats.py. Everything else in a chain is a page type.
 * "search" is both a page and an event; a chain is a plain string, so a search
 * step always reads as an action.
 */
const ACTION_STEPS = new Set(['site_open', 'search', 'paper_open', 'story_open', 'lyra_chat', 'share', 'feedback'])

export type ChipTone = 'entry' | 'page' | 'action'

export interface Chip {
  label: string
  tone: ChipTone
}

/** One chain string into its chips: the first step is where the session came from. */
export function chainChips(chain: string): Chip[] {
  return chain.split(ARROW).map((label, i) => ({
    label,
    tone: i === 0 ? 'entry' : ACTION_STEPS.has(label) ? 'action' : 'page',
  }))
}

/** The ten most walked paths through the site, as chip chains with their count. */
export function Journeys({ state }: { state: Loaded<JourneysData> }) {
  const j = state.data
  return (
    <Panel question="Wie bewegen sie sich?" wide>
      <Status state={state} />
      {j && (
        <>
          {j.chains.length === 0 ? (
            <p className="dash-empty">Keine Wege in diesem Zeitraum.</p>
          ) : (
            <ol className="dash-journeys">
              {j.chains.map(c => (
                <li key={c.chain} className="dash-journey">
                  <span className="dash-journey-chain">
                    {chainChips(c.chain).map((chip, i) => (
                      <Fragment key={`${i}-${chip.label}`}>
                        {i > 0 && (
                          <span className="dash-journey-arrow" aria-hidden="true">
                            →
                          </span>
                        )}
                        <span className={`dash-chip dash-chip--${chip.tone}`}>{chip.label}</span>
                      </Fragment>
                    ))}
                  </span>
                  <span className="dash-journey-count">{fmtInt(c.sessions)}</span>
                </li>
              ))}
            </ol>
          )}
          <p className="dash-note">
            Nur bestätigt menschliche Sitzungen, höchstens sechs Schritte je Kette. Der erste Chip ist die Quelle.
          </p>
        </>
      )}
    </Panel>
  )
}
