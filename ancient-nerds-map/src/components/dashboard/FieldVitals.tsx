import { fmtDay, fmtInt } from './format'
import { LineChart } from './Lines'
import { HowCounted, Panel, Status } from './Panel'
import type { FieldVitalsData, FormFactorVitals } from './types'
import type { Loaded } from './useStats'

type Metric = 'lcp' | 'inp' | 'cls'

/** Google's own bands (web.dev/vitals): at or below `good` is good, above
 *  `poor` is poor, between them needs improvement. */
export const BANDS: Record<Metric, { good: number; poor: number }> = {
  lcp: { good: 2500, poor: 4000 },
  inp: { good: 200, poor: 500 },
  cls: { good: 0.1, poor: 0.25 },
}

export const NAMES: Record<Metric, string> = {
  lcp: 'Largest paint',
  inp: 'Reaction to input',
  cls: 'Layout shift',
}

export type Rating = 'good' | 'ni' | 'poor'

export function rating(metric: Metric, value: number): Rating {
  const band = BANDS[metric]
  if (value <= band.good) return 'good'
  return value <= band.poor ? 'ni' : 'poor'
}

export function fmtVital(metric: Metric, value: number): string {
  if (metric === 'lcp') return `${(value / 1000).toFixed(1)} s`
  if (metric === 'inp') return `${fmtInt(Math.round(value))} ms`
  return value.toFixed(2)
}

/** The newest week that has a number; INP goes missing in a thin week. */
export function latest(values: (number | null)[]): { value: number; index: number } | null {
  for (let i = values.length - 1; i >= 0; i--) {
    const v = values[i]
    if (v !== null) return { value: v, index: i }
  }
  return null
}

const RATING_WORD: Record<Rating, string> = { good: 'good', ni: 'needs improvement', poor: 'poor' }

function Row({ ff, metric }: { ff: FormFactorVitals; metric: Metric }) {
  const now = latest(ff[metric])
  if (!now) return null
  const r = rating(metric, now.value)
  return (
    <li className="dash-vital">
      <span className="dash-vital-name">{NAMES[metric]}</span>
      <span className={`dash-vital-value dash-vital--${r}`}>{fmtVital(metric, now.value)}</span>
      <span className="dash-vital-band">
        {RATING_WORD[r]} · good up to {fmtVital(metric, BANDS[metric].good)}
      </span>
      <LineChart
        small
        series={[{ label: NAMES[metric], values: ff[metric], className: 'dash-line-human' }]}
        titles={ff.weeks.map((w, i) => {
          const v = ff[metric][i]
          return `28 days to ${fmtDay(w)}: ${v === null ? 'too few samples' : fmtVital(metric, v)}`
        })}
        label={`${NAMES[metric]} per week, ${ff.weeks.length} weeks`}
        max={Math.max(BANDS[metric].poor, ...ff[metric].filter((v): v is number => v !== null))}
      />
    </li>
  )
}

/**
 * Are we fast for Google — the numbers Google's ranking reads: the 75th
 * percentile of real Chrome users over 28 days (CrUX), phone and desktop,
 * with half a year of weekly history beside each. Its window is its own.
 */
export function FieldVitals({ state }: { state: Loaded<FieldVitalsData> }) {
  const d = state.data
  return (
    <Panel question="Are we fast for Google?">
      <Status state={state} />
      {d && (
        <>
          <div className="dash-lists">
            {(
              [
                ['Phone', d.phone],
                ['Desktop', d.desktop],
              ] as const
            ).map(([name, ff]) => (
              <div key={name}>
                <h3>
                  {name} · 28 days to {fmtDay(ff.weeks[ff.weeks.length - 1])}
                </h3>
                <ul className="dash-vitals">
                  <Row ff={ff} metric="lcp" />
                  <Row ff={ff} metric="inp" />
                  <Row ff={ff} metric="cls" />
                </ul>
              </div>
            ))}
          </div>
        </>
      )}
      <HowCounted>
        Google's Chrome UX Report for the whole origin: the value three in four real Chrome visits stayed under, over
        a rolling 28 days, published once a week - the field data Google's page-experience signal reads, not the
        measurements our own tracker sends (those are in "Where does the platform fail them?"). Largest paint is
        when the biggest element of the page appeared, reaction to input how long the page took to answer a tap or
        click, layout shift how much the page jumped while loading. The bands are Google's: green good, amber needs
        improvement, red poor. A week with too few samples has no point; the number shown is the newest week that
        has one. The line under each number is the last {fmtInt(d?.phone.weeks.length ?? 25)} weeks, scaled so the
        poor threshold always fits.
      </HowCounted>
    </Panel>
  )
}
