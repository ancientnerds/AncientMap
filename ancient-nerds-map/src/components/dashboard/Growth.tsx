import { fmtDay, fmtInt } from './format'
import { LineChart } from './Lines'
import { HowCounted, Panel, Status } from './Panel'
import type { DailyData, DailyPoint } from './types'
import type { Loaded } from './useStats'

/** Days on each side of the comparison: whole weeks, so a quiet weekend
 *  weighs the same on both sides. */
const WEEK = 7

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
  const first = fmtDay(days[0].day)
  const last = fmtDay(days[days.length - 1].day)
  return (
    <LineChart
      series={[
        { label: 'every visitor', values: days.map(p => p.visitors), className: 'dash-line-all' },
        { label: 'confirmed human', values: days.map(p => p.human), className: 'dash-line-human' },
      ]}
      titles={days.map(p => `${fmtDay(p.day)}: ${fmtInt(p.visitors)} visitors, ${fmtInt(p.human)} human, ${fmtInt(p.ai)} from AI`)}
      axis={[first, `Visitors per day, UTC · top ${fmtInt(max)}`, last]}
      label={`Visitors per day from ${first} to ${last}`}
      max={max}
    />
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
              Today so far, not on the line yet: {fmtInt(d.today.visitors)} visitors, {fmtInt(d.today.human)} human.
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
