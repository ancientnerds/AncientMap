import { BarList, type BarItem } from './BarList'
import { fmtInt } from './format'
import { HowCounted, Panel, Status } from './Panel'
import type { JourneysData, ReadingPage } from './types'
import type { Loaded } from './useStats'

/**
 * One page type as a row: the sessions that reached the first mark carry the
 * bar, the deeper marks follow as text. The hint opens with the same separator
 * the deeper marks use, so the row renders as one ladder — "17 · 15 · 13 · 10"
 * against the marks the note names. Counts throughout: a second bar scaled to
 * the first would be a drop-off rate, and twenty readers cannot carry one.
 */
export function readingItem(p: ReadingPage): BarItem {
  const [first, ...deeper] = p.sessions
  return {
    key: `read:${p.page}`,
    label: p.page,
    value: first,
    hint: deeper.length ? `· ${deeper.map(fmtInt).join(' · ')}` : undefined,
  }
}

/**
 * How far visitors read. The list needs no cap: src/analytics/boot.ts arms the
 * scroll listener on five page types and on no others, so it is five rows at
 * worst. The note spells the marks out of the response rather than out of a
 * constant here, so the ladder in each row and the ladder the sentence names
 * cannot drift apart.
 */
export function Reading({ state }: { state: Loaded<JourneysData> }) {
  // One key of the /journeys response, not a route of its own: the scroll_depth
  // rows travel with the chains, so this panel costs no query.
  const r = state.data?.reading
  return (
    <Panel question="How far do they read?">
      <Status state={state} />
      {/* An answer without this key is an API older than this bundle — every
          deploy has that window, because ci.yml builds the frontend before it
          rebuilds the API. Say so; a titled panel with nothing inside it is
          the one thing this page may not ship. */}
      {state.data && !r && <p className="dash-status dash-status--error">Data unavailable.</p>}
      {r && (
        <>
          <BarList items={r.pages.map(readingItem)} empty="Nobody scrolled a page in this window." />
          <HowCounted>
            One row per page type: how many sessions reached {r.steps.map(s => `${s} %`).join(' · ')} of
            the page, in that order. Counts only — {fmtInt(r.readers)} sessions scrolled at all in this
            window, and a sample that size cannot carry a share. A mark is fired by src/analytics/boot.ts
            on a real scroll event and on nothing else, so the denominator is sessions that scrolled,
            never page views: story, site, paper, journal and country pages arm the listener, and a
            visitor who finished a short one without scrolling is in no column. These rows are not
            filtered to confirmed humans — on 2026-09-19 eight sessions fired a mark without a single
            page view, every one of them inside the two machine fingerprints the Scrapers panel names.
          </HowCounted>
        </>
      )}
    </Panel>
  )
}
