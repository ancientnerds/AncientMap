import { Flag } from './Flag'
import { fmtInt, fmtStamp } from './format'
import { HowCounted, Panel, Status } from './Panel'
import type { ProblemKind, ProblemsData, Visitor } from './types'
import type { Loaded } from './useStats'

export type Severity = 'high' | 'mid' | 'low'

/** Red breaks a page, amber slows it down, green-grey is a hint, not a defect. */
const SEVERITY: Record<ProblemKind, Severity> = {
  js_error: 'high',
  broken_link: 'high',
  webgl_lost: 'high',
  slow_page: 'mid',
  shallow_exit: 'low',
  empty_search: 'low',
}

/** The kind names of pipeline/stats_analysis.py problems(), in founder words. */
const KIND_LABELS: Record<ProblemKind, string> = {
  js_error: 'JS error',
  slow_page: 'Slow',
  broken_link: 'Dead link',
  shallow_exit: 'Bounce',
  empty_search: 'Empty search',
  webgl_lost: 'WebGL lost',
}

export function severity(kind: ProblemKind): Severity {
  return SEVERITY[kind]
}

export function problemLabel(kind: ProblemKind): string {
  return KIND_LABELS[kind]
}

/**
 * When it last happened and to whom. There is no user in cookieless
 * analytics: the visitor is Umami's session, which recognises the same
 * browser for one calendar month — flag, browser, device and eight
 * characters of that id, enough to see two rows are the same person.
 */
function When({ at, last }: { at: string | null; last: Visitor | null }) {
  if (!at && !last) return null
  return (
    <span className="dash-problem-who">
      {at && <time dateTime={at}>{fmtStamp(at)}</time>}
      {last && (
        <span className="dash-flag">
          <Flag country={last.country} />
        </span>
      )}
      {last && [last.browser, last.device].filter(Boolean).join(' · ')}
      {last && <code>{last.session}</code>}
    </span>
  )
}

/** What fails the visitors, worst first: a severity dot, what broke, the numbers. */
export function Problems({ state }: { state: Loaded<ProblemsData> }) {
  const p = state.data
  return (
    <Panel question="Where does the platform fail them?" wide>
      <Status state={state} />
      {p && (
        <>
          {p.problems.length === 0 ? (
            <p className="dash-empty">No problems in this window.</p>
          ) : (
            <ol className="dash-problems">
              {p.problems.map(item => (
                <li key={`${item.kind}:${item.label}:${item.detail}`} className="dash-problem">
                  {/* Not aria-hidden: the dot is the only thing on the row
                      that carries severity, and the list is sorted by score,
                      so hue alone decides whether "Dead link · 24" outranks
                      "Bounce · 38" for the reader. */}
                  <span
                    className={`dash-dot dash-dot--${severity(item.kind)}`}
                    role="img"
                    aria-label={severity(item.kind)}
                  />
                  <span className="dash-problem-kind">{problemLabel(item.kind)}</span>
                  <span className="dash-problem-label" title={item.label}>
                    {item.label}
                  </span>
                  <span className="dash-problem-score">{fmtInt(item.score)}</span>
                  <span className="dash-problem-detail">{item.detail}</span>
                  <When at={item.at} last={item.last} />
                </li>
              ))}
            </ol>
          )}
          <HowCounted>
            Everything counts people, not events. The score makes the kinds comparable: a JS error and a lost
            WebGL context count triple per visitor they reached, a dead link double, a bounce and an empty
            search once; a slow page counts its visitors times how far past its budget it is, so a page that
            misses the threshold by a millisecond cannot outrank a crash. A red dot breaks a page, amber slows
            it, green is a hint and not a defect. The eight worst are listed. A story we withdrew on purpose
            answers 410 and raises no event, so retired links never appear here — the Sources panel counts
            those.
          </HowCounted>
        </>
      )}
    </Panel>
  )
}
