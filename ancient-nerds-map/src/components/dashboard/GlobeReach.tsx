import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { GlobeData } from './types'
import type { Loaded } from './useStats'

/** "9.4 s" / "80.4 s" — the globe's times are seconds, never milliseconds.
 *  toFixed rounds the binary double, so the live minimum of 9450 ms reads
 *  "9.4 s", not "9.5 s": 9450 / 1000 is 9.4499999999999992895. */
export function secs(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

/**
 * The sentence under the two numbers. Counts, never a percentage on its own:
 * eight successes out of thirty-three loads is a direction, and the reader has
 * to see both numbers to know that. No p75 either — eight live samples come
 * from six browsers and two of those contributed two loads each.
 */
export function timesLine(g: GlobeData): string {
  const t = g.ready_ms
  if (t.samples === 0) return 'No globe reached its layers in this window.'
  // One report is not a best and a worst. Eleven globe_ready events in the
  // live seven-day window (2026-09-19) and eight two days earlier: a quiet
  // week reaches one, and "9.4 s at best, 9.4 s at worst" out of a single
  // measurement reads as a spread that was never measured.
  if (t.samples === 1) return `The one globe_ready report we have waited ${secs(t.min ?? 0)}.`
  const middle = t.median === null ? '' : `, ${secs(t.median)} in the middle`
  // "reports", not "visitors": samples counts globe_ready events and is not
  // capped to `reached`, which is capped to page views (globe_funnel's
  // docstring says why). The two agree today and need not tomorrow.
  return `The ${fmtInt(t.samples)} globe_ready reports we have waited ${secs(t.min ?? 0)} at best${middle}, ${secs(t.max ?? 0)} at worst.`
}

/** How many *people* got to a globe, against how many opened one. The tiles
 *  above count page loads on purpose (one person reloading counts twice), so
 *  this is the only place the visitor figure is readable — and `sessions` is
 *  in every /globe response whether or not anything prints it. */
export function visitorsLine(g: GlobeData): string {
  const { reached, all } = g.sessions
  if (all === 0) return 'Nobody opened the globe in this window.'
  return `${fmtInt(reached)} of ${fmtInt(all)} visitors who opened it got there.`
}

/** Does the globe come up at all — the product's own pass rate. */
export function GlobeReach({ state }: { state: Loaded<GlobeData> }) {
  const g = state.data
  return (
    <Panel question="Does the globe actually come up?">
      <Status state={state} />
      {g && (
        <>
          <div className="dash-tiles">
            <Tile label="Globe loads" value={g.loads} sub={`${fmtInt(g.sessions.all)} visitors opened it`} />
            <Tile
              label="Reached the globe"
              value={g.reached}
              sub={`${fmtInt(g.gave_up)} loads never got there`}
            />
          </div>
          <p className="dash-note">
            {timesLine(g)} The denominator is page loads of /globe.html, not visitors — one person
            reloading counts twice, on purpose. {visitorsLine(g)}
          </p>
        </>
      )}
    </Panel>
  )
}
