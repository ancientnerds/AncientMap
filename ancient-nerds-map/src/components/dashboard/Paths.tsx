import { Fragment } from 'react'

import { BarList, type BarItem } from './BarList'
import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import type { EntryPage, ExitPage, JourneysData, OutboundLink } from './types'
import type { Loaded } from './useStats'

/** The separator pipeline/stats_analysis.py journeys() joins the steps with. */
const ARROW = ' → '

/**
 * The event names that can appear as a step — JOURNEY_EVENTS in
 * pipeline/stats_analysis.py. Everything else in a chain is a page type.
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

/** "story · 248, 151 of them went no further" — counts, never a bounce rate. */
export function entryItem(e: EntryPage): BarItem {
  return {
    key: `entry:${e.page}`,
    label: e.page,
    value: e.sessions,
    hint: e.stopped ? `${fmtInt(e.stopped)} went no further` : undefined,
    tone: e.stopped && e.stopped === e.sessions ? 'warn' : undefined,
  }
}

/** The last page a session was on, against how often that type was seen. */
export function exitItem(x: ExitPage): BarItem {
  return {
    key: `exit:${x.page}`,
    label: x.page,
    value: x.sessions,
    hint: `of ${fmtInt(x.views)} views`,
  }
}

/** A link out of the site. There is no Discord row: see the panel's note. */
export function outboundItem(o: OutboundLink): BarItem {
  return {
    key: `out:${o.host}`,
    label: o.host,
    value: o.clicks,
    hint: `${fmtInt(o.visitors)} ${o.visitors === 1 ? 'visitor' : 'visitors'}`,
  }
}

/** Where they land, where they stop, the whole chain, and where they leave to. */
export function Paths({ state }: { state: Loaded<JourneysData> }) {
  const j = state.data
  return (
    <Panel question="How do they move through the site, and where do they leave?" wide>
      <Status state={state} />
      {j && (
        <>
          <div className="dash-lists">
            <div>
              <h3>They land on</h3>
              <BarList items={j.pages.entries.map(entryItem)} empty="No human session opened a page." />
            </div>
            <div>
              <h3>They stop on</h3>
              <BarList items={j.pages.exits.map(exitItem)} empty="No human session opened a page." />
            </div>
          </div>
          <h3>Most walked paths</h3>
          {j.chains.length === 0 ? (
            <p className="dash-empty">No journeys in this window.</p>
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
          <h3>Links out of the site</h3>
          <BarList items={j.outbound.map(outboundItem)} empty="No outbound click in this window." />
          <p className="dash-note">
            Confirmed human sessions only, at most six steps per chain; the first chip is the source. Of{' '}
            {fmtInt(j.pages.sessions)} human sessions, {fmtInt(j.pages.one_page)} loaded exactly one page
            and {fmtInt(j.pages.moving)} moved. A session with no page view at all is not counted as
            human and is not in here — the Scrapers panel above is where those go. Discord clicks are
            missing from the outbound list: the CTA on the landing page, which the server log says gets
            most of them, runs no analytics module — read those with scripts/funnel_report.py.
          </p>
        </>
      )}
    </Panel>
  )
}
