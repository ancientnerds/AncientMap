import { fmtInt } from './format'
import { HowCounted, Panel, Status } from './Panel'
import type { JourneysData, ReadingPage } from './types'
import type { Loaded } from './useStats'

export interface LadderCell {
  count: number
  /** Of the sessions that reached the first mark, the share that reached
   *  this one - the bar's width, never printed as a number (see below). */
  share: number
}

/**
 * One page type as a ladder: a cell per mark, its count, and a bar as wide as
 * the share of the first mark's readers who got that far. The bar shows the
 * drop-off; the number stays a count, because twenty readers cannot carry a
 * percentage and a founder would read a printed one as a rate.
 */
export function ladderCells(p: ReadingPage): LadderCell[] {
  const first = Math.max(p.sessions[0] ?? 0, 1)
  return p.sessions.map(count => ({ count, share: count / first }))
}

/**
 * How far visitors read. The list needs no cap: src/analytics/boot.ts arms the
 * scroll listener on five page types and on no others, so it is five rows at
 * worst. The column heads come out of the response rather than out of a
 * constant here, so the ladder in each row and its heads cannot drift apart.
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
      {r &&
        (r.pages.length === 0 ? (
          <p className="dash-empty">Nobody scrolled a page so far.</p>
        ) : (
          <>
            <table className="dash-ladder">
              <thead>
                <tr>
                  <th scope="col">Page</th>
                  {r.steps.map(s => (
                    <th key={s} scope="col">
                      {s} %
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {r.pages.map(p => (
                  <tr key={p.page}>
                    <th scope="row">{p.page}</th>
                    {ladderCells(p).map((cell, i) => (
                      <td key={r.steps[i]}>
                        <span className="dash-ladder-count">{fmtInt(cell.count)}</span>
                        <span className="dash-ladder-bar" aria-hidden="true">
                          <span style={{ width: `${cell.share * 100}%` }} />
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="dash-note">Sessions that scrolled to each mark of the page; {fmtInt(r.readers)} scrolled at all.</p>
          </>
        ))}
      {r && (
        <HowCounted>
          One row per page type: how many sessions reached {r.steps.map(s => `${s} %`).join(' · ')} of the page, in
          that order; the bar under each count is its share of the row's first mark, so the drop-off reads left to
          right. Counts only — a sample this size cannot carry a printed share. A mark is fired by
          src/analytics/boot.ts on a real scroll event and on nothing else, so the denominator is sessions that
          scrolled, never page views: story, site, paper, journal and country pages arm the listener, and a visitor
          who finished a short one without scrolling is in no column. These rows are not filtered to confirmed
          humans — on 2026-09-19 eight sessions fired a mark without a single page view, every one of them inside the
          two machine fingerprints the Scrapers panel names.
        </HowCounted>
      )}
    </Panel>
  )
}
