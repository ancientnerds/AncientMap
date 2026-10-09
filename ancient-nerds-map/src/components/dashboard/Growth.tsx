import { fmtDay, fmtInt } from './format'
import { HowCounted, Panel, Status } from './Panel'
import type { DailyData, DailyPoint } from './types'
import type { Loaded } from './useStats'

/** Height of the chart's viewBox; the CSS scales it to the panel's width. */
const LINE_HEIGHT = 100
/** Days on each side of the comparison: whole weeks, so a quiet weekend
 *  weighs the same on both sides. */
const WEEK = 7

/** One polyline's `points`: day i at x = i, the value measured up from the
 *  baseline against `max`. A zero max draws the line on the baseline. */
export function linePoints(values: number[], max: number, height = LINE_HEIGHT): string {
  const unit = height / Math.max(max, 1)
  return values.map((v, i) => `${i},${height - v * unit}`).join(' ')
}

export interface WeekChange {
  /** Average per day over the first full week. */
  first: number
  /** Average per day over the last finished week. */
  last: number
  /** last / first − 1; null when the first week had nobody to divide by. */
  change: number | null
}

/** The first week against the last one; null until there are two weeks that
 *  do not overlap. */
export function weekChange(days: DailyPoint[], key: 'visitors' | 'human'): WeekChange | null {
  if (days.length < 2 * WEEK) return null
  const mean = (part: DailyPoint[]) => part.reduce((sum, p) => sum + p[key], 0) / part.length
  const first = mean(days.slice(0, WEEK))
  const last = mean(days.slice(-WEEK))
  return { first, last, change: first > 0 ? last / first - 1 : null }
}

function Change({ c }: { c: WeekChange }) {
  if (c.change === null) return <>new</>
  const pct = Math.round(c.change * 100)
  return <span className={pct >= 0 ? 'dash-delta--up' : 'dash-delta--down'}>{`${pct >= 0 ? '+' : '−'}${Math.abs(pct)} %`}</span>
}

function Trend({ days }: { days: DailyPoint[] }) {
  const visitors = weekChange(days, 'visitors')
  const human = weekChange(days, 'human')
  if (!visitors || !human) {
    return (
      <p className="dash-note">
        The week-on-week comparison starts once there are {2 * WEEK} finished days; there are {days.length}.
      </p>
    )
  }
  const firstWeek = `${fmtDay(days[0].day)}–${fmtDay(days[WEEK - 1].day)}`
  const lastWeek = `${fmtDay(days[days.length - WEEK].day)}–${fmtDay(days[days.length - 1].day)}`
  return (
    <p className="dash-trend">
      Last week ({lastWeek}): <b>{fmtInt(Math.round(visitors.last))}</b> visitors a day,{' '}
      {fmtInt(Math.round(human.last))} of them confirmed human. First week ({firstWeek}):{' '}
      {fmtInt(Math.round(visitors.first))} a day, {fmtInt(Math.round(human.first))} human. Change:{' '}
      <Change c={visitors} /> visitors, <Change c={human} /> humans.
    </p>
  )
}

function Chart({ days }: { days: DailyPoint[] }) {
  const max = Math.max(...days.map(p => p.visitors), 1)
  const width = days.length - 1
  return (
    <>
      <svg
        className="dash-line"
        viewBox={`0 0 ${width} ${LINE_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Visitors per day from ${fmtDay(days[0].day)} to ${fmtDay(days[width].day)}`}
      >
        <polyline className="dash-line-all" points={linePoints(days.map(p => p.visitors), max)} />
        <polyline className="dash-line-human" points={linePoints(days.map(p => p.human), max)} />
        {days.map((p, i) => (
          <rect key={p.day} className="dash-line-hit" x={i - 0.5} width={1} y={0} height={LINE_HEIGHT}>
            <title>{`${fmtDay(p.day)}: ${fmtInt(p.visitors)} visitors, ${fmtInt(p.human)} human, ${fmtInt(p.ai)} from AI`}</title>
          </rect>
        ))}
      </svg>
      <div className="dash-spark-axis">
        <span>{fmtDay(days[0].day)}</span>
        <span>Visitors per day, UTC · top {fmtInt(max)}</span>
        <span>{fmtDay(days[width].day)}</span>
      </div>
    </>
  )
}

/**
 * Is the audience growing — one point per finished day since the tracker's
 * first full day, every visitor (pale) and the confirmed humans among them
 * (bright), and one sentence that compares the last week with the first.
 * Its window is its own: the whole history, not the page's range switch.
 */
export function Growth({ state }: { state: Loaded<DailyData> }) {
  const d = state.data
  return (
    <Panel question="Is the audience growing?" wide>
      <Status state={state} />
      {d &&
        (d.days.length < 2 ? (
          <p className="dash-empty">The line needs two finished days.</p>
        ) : (
          <>
            <Chart days={d.days} />
            <Trend days={d.days} />
            <p className="dash-note">
              Pale: every visitor. Bright: the confirmed humans among them. Today so far, not on the line yet:{' '}
              {fmtInt(d.today.visitors)} visitors, {fmtInt(d.today.human)} human.
            </p>
          </>
        ))}
      <HowCounted>
        A visitor is one browser on one UTC day — Umami's id, which lives for a calendar month, so someone who
        comes back on another day counts on both days. Confirmed human means an interaction or a second page that
        day, the same rule as everywhere on this page. The line starts on 18 September, the tracker's first full
        day. Umami counts browsers that run its script: a scraper without JavaScript and a founder who switched
        tracking off are not in it. The human line has a step on 9 October: from that deploy on the tracker also
        sees scrolling inside panels and every link click, so more of the same visitors prove they are people. The
        visitor line has no such step.
      </HowCounted>
    </Panel>
  )
}
