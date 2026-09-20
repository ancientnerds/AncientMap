import { fmtDayHour, fmtInt, fmtShare } from './format'
import { Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { CountriesData, CountryWindow, HourBucket, Overview } from './types'
import type { Loaded } from './useStats'

/** Height of the strip's viewBox; the CSS scales it to the panel's width. */
const STRIP_HEIGHT = 20

export interface HourStack {
  humanY: number
  humanH: number
  restY: number
  restH: number
}

/**
 * One hour as two stacked rects: confirmed humans on the baseline, everything
 * else above them. Two segments, not three — at 390 px a bar is 4.9 px wide
 * and one session at the 48-hour peak is 6 px tall, below the size at which
 * any colour difference survives. The AI count is a number in the legend and
 * in the tooltip instead.
 */
export function stackHour(h: HourBucket, max: number, height = STRIP_HEIGHT): HourStack {
  const unit = height / Math.max(max, 1)
  const humanH = h.human * unit
  const restH = (h.sessions - h.human) * unit
  return { humanY: height - humanH, humanH, restY: height - humanH - restH, restH }
}

/** "human sessions, 34 % of 154" — the same sentence for every closed window. */
function humanSub(w: CountryWindow): string {
  return `human sessions, ${fmtShare(w.sessions, w.all)} of ${fmtInt(w.all)}`
}

function Strip({ o }: { o: Overview }) {
  const hours = o.hours
  if (hours.length < 2) return null
  const max = Math.max(...hours.map(h => h.sessions), 1)
  const first = new Date(hours[0].hour)
  const last = new Date(hours[hours.length - 1].hour)
  return (
    <>
      <svg
        className="dash-spark"
        viewBox={`0 0 ${hours.length} ${STRIP_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Sessions per hour, last ${hours.length} hours`}
      >
        {hours.map((h, i) => {
          const s = stackHour(h, max)
          const title = `${fmtDayHour(new Date(h.hour))} UTC: ${fmtInt(h.sessions)} sessions, ${fmtInt(h.human)} human, ${fmtInt(h.ai)} from AI`
          return (
            <g key={h.hour}>
              <rect x={i + 0.15} width={0.7} y={s.restY} height={s.restH}>
                <title>{title}</title>
              </rect>
              <rect className="dash-spark-human" x={i + 0.15} width={0.7} y={s.humanY} height={s.humanH}>
                <title>{title}</title>
              </rect>
            </g>
          )
        })}
      </svg>
      <div className="dash-spark-axis">
        <span>{fmtDayHour(first)}</span>
        <span>Sessions per hour, UTC</span>
        <span>{fmtDayHour(last)}</span>
      </div>
      <p className="dash-note">
        Bright green is a confirmed human — an interaction or a second page. The rest may be a bot, or a
        person who read the headline and left; cookieless data cannot tell them apart. AI assistants sent{' '}
        {fmtInt(o.sessions.ai)} of {fmtInt(o.sessions.all)} sessions in this window.
      </p>
    </>
  )
}

/**
 * Four windows of one question — who is here now, today, this week, this month
 * — each with its total and the countries behind it. The windows are fixed:
 * the page's range switch drives the other panels, not this one.
 */
export function Pulse({ state, countries }: { state: Loaded<Overview>; countries: Loaded<CountriesData> }) {
  const o = state.data
  const c = countries.data
  return (
    <Panel question="Who is here right now?" wide>
      <Status state={countries} />
      {c && (
        <div className="dash-tiles">
          <Tile label="Now" value={c.now.sessions} sub="sessions, last 5 min" countries={c.now.countries} />
          <Tile label="Today" value={c.today.sessions} sub={humanSub(c.today)} countries={c.today.countries} />
          <Tile label="7 days" value={c.d7.sessions} sub={humanSub(c.d7)} countries={c.d7.countries} />
          <Tile label="30 days" value={c.d30.sessions} sub={humanSub(c.d30)} countries={c.d30.countries} />
        </div>
      )}
      {/* Two resources, two statuses. /overview is the heaviest query on the
          page and fails on its own; without this line the panel keeps its four
          tiles and quietly loses the 48-hour strip and the AI sentence. */}
      {o ? <Strip o={o} /> : <Status state={state} />}
    </Panel>
  )
}
