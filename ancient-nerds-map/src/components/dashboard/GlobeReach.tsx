import { type BarItem, BarList } from './BarList'
import { fmtInt } from './format'
import { HowCounted, Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { GlobeData, GlobeDevice, GlobeEndings, GlobeTimes } from './types'
import type { Loaded } from './useStats'

/** "9.4 s" / "80.4 s" — the globe's times are seconds, never milliseconds.
 *  toFixed rounds the binary double, so the live minimum of 9450 ms reads
 *  "9.4 s", not "9.5 s": 9450 / 1000 is 9.4499999999999992895. */
export function secs(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

/** "9.4 s at best, 19.9 s in the middle, 80.4 s at worst" — the middle only
 *  once the response carries one (five samples), never "null". */
function spread(t: GlobeTimes, low: string, high: string): string {
  const middle = t.median === null ? '' : `, ${secs(t.median)} in the middle`
  return `${secs(t.min ?? 0)} ${low}${middle}, ${secs(t.max ?? 0)} ${high}`
}

/**
 * The sentence under the two numbers. Counts, never a percentage on its own:
 * eight successes out of thirty-three loads is a direction, and the reader has
 * to see both numbers to know that. No p75 either — eight live samples come
 * from six browsers and two of those contributed two loads each.
 */
export function timesLine(g: GlobeData): string {
  const t = g.ready_ms
  if (t.samples === 0) return 'No globe came up in this window.'
  // One report is not a best and a worst. Eleven globe_ready events in the
  // live seven-day window (2026-09-19) and eight two days earlier: a quiet
  // week reaches one, and "9.4 s at best, 9.4 s at worst" out of a single
  // measurement reads as a spread that was never measured.
  if (t.samples === 1) return `The one globe_ready report we have waited ${secs(t.min ?? 0)}.`
  // "reports", not "visitors": samples counts globe_ready events and is not
  // capped to `reached`, which is capped to page views (globe_funnel's
  // docstring says why). The two agree today and need not tomorrow.
  return `The ${fmtInt(t.samples)} globe_ready reports we have waited ${spread(t, 'at best', 'at worst')}.`
}

/** How long the loads counted as "left while loading" had waited, by the
 *  rules of timesLine. Here the samples ARE loads: globe_funnel keeps only
 *  the abandons its split counted. Empty without one. */
export function abandonLine(g: GlobeData): string {
  const t = g.abandon_ms
  if (t.samples === 0) return ''
  if (t.samples === 1) return `The one load left while loading had waited ${secs(t.min ?? 0)}.`
  return `The ${fmtInt(t.samples)} loads left while loading had waited ${spread(t, 'at the shortest', 'at the longest')}.`
}

/** Printed after abandonLine whenever it says something: the two spreads look
 *  alike and are not measured alike. globe_ready's ms counts from navigation
 *  (useGlobeReady), the abandon's from the start of the load (createLoadClock),
 *  so on a phone the ready times carry the time spent reading the gate. */
const CLOCKS_NOTE =
  ' These waits count from the start of the load, on a phone the tap on 3D Globe; the globe_ready' +
  ' times above count from the page load, reading the phone gate included, so on phones the two do not compare.'

/** One label per ending. The literal's key order is the row order: the order
 *  a load meets them (gate, capability check, start, leaving), then what
 *  nothing explains. A Record, so a new ending without a label does not compile. */
const ENDING_LABELS: Record<keyof GlobeEndings, string> = {
  gate: 'Stopped at the phone gate',
  unsupported: 'Device cannot run the globe',
  error: 'Error while starting',
  abandoned: 'Left while loading',
  no_signal: 'No signal',
}

/** The rows of the split, in fixed order — zeros stay, the order is the
 *  reading. */
export function endingItems(g: GlobeData): BarItem[] {
  const n = g.not_reached
  const median = g.abandon_ms.median
  return (Object.keys(ENDING_LABELS) as Array<keyof GlobeEndings>)
    .map(key => ({
      key,
      label: ENDING_LABELS[key],
      value: n[key],
      ...(key === 'abandoned' && median !== null ? { hint: `median ${secs(median)}` } : {}),
    }))
}

const DEVICE_WORDS: Record<string, string> = {
  mobile: 'Phones',
  desktop: 'Computers',
  tablet: 'Tablets',
  unknown: 'Unknown devices',
}

/** "Phones 4 of 8 · Computers 17 of 18 loads reached the globe." Phones are
 *  their own question - the gate, the layout - and one total hides them. */
export function devicesLine(devices: GlobeDevice[] | undefined): string {
  if (!devices || devices.length === 0) return ''
  const parts = devices.map(d => `${DEVICE_WORDS[d.device] ?? d.device} ${fmtInt(d.reached)} of ${fmtInt(d.loads)}`)
  return `${parts.join(' · ')} loads reached the globe.`
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
          {devicesLine(g.by_device) && <p className="dash-note">{devicesLine(g.by_device)}</p>}
          <p className="dash-note">
            {timesLine(g)} The denominator is page loads of /globe.html, not visitors — one person
            reloading counts twice, on purpose. {visitorsLine(g)} Counted from the build of 24 Sep 2026
            on, the first that reports how a load ends; loads of the earlier build are left out.
          </p>
          {/* An answer without the split is an API older than this bundle — every
              deploy has that window, because ci.yml builds the frontend before it
              rebuilds the API. The tiles above stay; the split says so. */}
          {!g.not_reached && <p className="dash-status dash-status--error">Data unavailable.</p>}
          {g.not_reached && g.gave_up > 0 && (
            <>
              <h3>How the other loads ended</h3>
              <BarList items={endingItems(g)} empty="No load ended without the globe in this window." />
              {g.abandon_ms.samples > 0 && <p className="dash-note">{abandonLine(g)}</p>}
              <HowCounted>
                {g.abandon_ms.samples > 0 && CLOCKS_NOTE} Counts per load, but Umami ties an event to a visitor and never to one
                page load, so a visitor's endings are matched to their loads in this order. No signal:
                the page loaded and nothing else arrived — a crashed tab, or a visitor gone before the
                tracker loaded.
              </HowCounted>
            </>
          )}
          {g.not_reached && g.gave_up === 0 && g.loads > 0 && (
            <p className="dash-note">Every load in this window reached the globe.</p>
          )}
        </>
      )}
    </Panel>
  )
}
