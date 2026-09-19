import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import type { ProblemKind, ProblemsData } from './types'
import type { Loaded } from './useStats'

export type Severity = 'high' | 'mid' | 'low'

/** Red breaks a page, amber slows it down, green-grey is a hint, not a defect. */
const SEVERITY: Record<ProblemKind, Severity> = {
  js_error: 'high',
  broken_link: 'high',
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
}

export function severity(kind: ProblemKind): Severity {
  return SEVERITY[kind]
}

export function problemLabel(kind: ProblemKind): string {
  return KIND_LABELS[kind]
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
                  <span className={`dash-dot dash-dot--${severity(item.kind)}`} aria-hidden="true" />
                  <span className="dash-problem-kind">{problemLabel(item.kind)}</span>
                  <span className="dash-problem-label" title={item.label}>
                    {item.label}
                  </span>
                  <span className="dash-problem-score">{fmtInt(item.score)}</span>
                  <span className="dash-problem-detail">{item.detail}</span>
                </li>
              ))}
            </ol>
          )}
          <p className="dash-note">
            Everything counts people, not events. The score makes the kinds comparable: a JS error counts triple
            per visitor it reached, a dead link double, a slow page once per measurement.
          </p>
        </>
      )}
    </Panel>
  )
}
