import { Flag } from './Flag'
import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import type { LiveData, LiveVisitor } from './types'
import type { Loaded } from './useStats'

/** "< 1 min" / "6 min" / "2 h 11 min" — how long they have had this page open.
 *  formatDuration() in utils/formatters.ts is clock style ("6:52") and
 *  timeAgo() needs a timestamp, so neither answers this question. */
export function fmtSpan(seconds: number): string {
  if (seconds < 60) return '< 1 min'
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins} min`
  return `${Math.floor(mins / 60)} h ${mins % 60} min`
}

/** Seconds since an ISO stamp, for "last seen N ago". `here` cannot answer
 *  that: live_row() measures it from page_since, the start of that visitor's
 *  last page view, so it overstates by the whole time they spent on it —
 *  live rows show gaps of up to 4 min 40 s between the two today. */
export function secondsSince(iso: string, now = Date.now()): number {
  return Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
}

function Row({ v }: { v: LiveVisitor }) {
  return (
    <li className="dash-live-row">
      <span className="dash-dot dash-dot--live" aria-hidden="true" />
      <span className="dash-flag">
        <Flag country={v.country} />
      </span>
      <span className="dash-live-who">{[v.browser, v.device].filter(Boolean).join(' · ')}</span>
      <span className="dash-live-here">{fmtSpan(v.here)}</span>
      <span className="dash-live-page">{v.title}</span>
    </li>
  )
}

/** Who is here in the last half hour, and what they have open. */
export function LiveNow({ state }: { state: Loaded<LiveData> }) {
  const l = state.data
  return (
    <Panel question="What are they looking at right now?" wide>
      <Status state={state} />
      {l && (
        <>
          {l.total === 0 ? (
            <p className="dash-empty">
              Nobody in the last {l.window_minutes} minutes.
              {l.last ? (
                <>
                  {' '}
                  Last seen {fmtSpan(secondsSince(l.last.last_seen))} ago on <b>{l.last.title}</b>.
                </>
              ) : (
                // The route looks back lookback_hours for that last visitor, so
                // an empty `last` is a measured 24 hours of nobody, not a gap in
                // the panel. The number is the response's, never a literal here.
                <> Nobody in the {l.lookback_hours} hours before that either.</>
              )}
            </p>
          ) : (
            <ul className="dash-live">
              {l.visitors.map(v => (
                <Row key={v.session} v={v} />
              ))}
            </ul>
          )}
          <p className="dash-note">
            {fmtInt(l.total)} in the last {l.window_minutes} minutes, {fmtInt(l.shown)} shown. The Now
            tile above counts five minutes, so this list is the longer window. A visitor who fired only a
            Core Web Vital has no page to name and no row — ten of sixty-nine sessions in a day
            (2026-09-19). The headline is the page's own title, so it is in the visitor's language, not
            ours. This is the one panel on the page that can point at a single person: at one visitor it
            names their country, device, browser and the page they have open right now. It is cookieless
            and no id here survives the monthly salt rotation, but it is not anonymous in the moment — do
            not screenshot it into a public channel.
          </p>
        </>
      )}
    </Panel>
  )
}
