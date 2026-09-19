import { getCountryFlatFlagUrl } from '../../utils/countryFlags'

import { countryName, fmtDayHour, fmtInt, fmtShare } from './format'
import { Panel, Status } from './Panel'
import type { CountriesData, CountryCount, CountryWindow, HourBucket, Overview } from './types'
import type { Loaded } from './useStats'

/** How many of the hourly buckets the strip shows: two days is readable at 390 px. */
const SPARK_HOURS = 48
/** The flag images live on the main host; this one only serves the dashboard. */
const FLAG_HOST = 'https://ancientnerds.com'

/** Sign and size of today's change against yesterday at the same time of day. */
function delta(today: number, yesterday: number): { arrow: string; text: string; cls: string } {
  if (yesterday === 0) return { arrow: '', text: 'none yesterday', cls: '' }
  const pct = Math.round(((today - yesterday) / yesterday) * 100)
  if (pct === 0) return { arrow: '=', text: 'same as yesterday', cls: '' }
  return pct > 0
    ? { arrow: '▲', text: `${pct} % vs yesterday`, cls: 'dash-delta--up' }
    : { arrow: '▼', text: `${-pct} % vs yesterday`, cls: 'dash-delta--down' }
}

/**
 * One line of flags with counts, biggest country first. It never wraps and it
 * never scrolls: whatever does not fit is simply cut off (owner, 2026-09-19),
 * so a tile always shows the strongest countries and nothing competes for the
 * space. The fade on the right says there is more.
 */
export function Flags({ rows }: { rows: CountryCount[] }) {
  if (rows.length === 0) return null
  return (
    <ul className="dash-flags">
      {rows.map(r => {
        const name = countryName(r.country)
        const flag = getCountryFlatFlagUrl(r.country)
        return (
          <li className="dash-flag" key={r.country} title={`${name}: ${fmtInt(r.sessions)}`}>
            {flag ? (
              <img src={`${FLAG_HOST}${flag}`} alt="" width="18" height="12" loading="lazy" decoding="async" />
            ) : (
              <span className="dash-flag-blank" aria-hidden="true" />
            )}
            <span className="dash-sr">{name}</span>
            {fmtInt(r.sessions)}
          </li>
        )
      })}
    </ul>
  )
}

function Tile({ label, sub, subCls, window: w }: { label: string; sub: string; subCls?: string; window: CountryWindow }) {
  return (
    <div className="dash-tile">
      <span className="dash-tile-label">{label}</span>
      <span className="dash-tile-value">{fmtInt(w.sessions)}</span>
      <span className={subCls ? `dash-tile-sub ${subCls}` : 'dash-tile-sub'}>{sub}</span>
      <Flags rows={w.countries} />
    </div>
  )
}

/** "human sessions, 34 % of 154" — the same sentence for every closed window. */
function humanSub(w: CountryWindow): string {
  return `human sessions, ${fmtShare(w.sessions, w.all)} of ${fmtInt(w.all)}`
}

function Spark({ hours }: { hours: HourBucket[] }) {
  const recent = hours.slice(-SPARK_HOURS)
  if (recent.length < 2) return null
  const max = Math.max(...recent.map(h => h.views), 1)
  const first = new Date(recent[0].hour)
  const last = new Date(recent[recent.length - 1].hour)
  const label = fmtDayHour
  return (
    <>
      <svg className="dash-spark" viewBox={`0 0 ${recent.length} 20`} preserveAspectRatio="none" role="img" aria-label={`Page views per hour, last ${recent.length} hours`}>
        {recent.map((h, i) => (
          <rect key={h.hour} x={i + 0.15} width={0.7} y={20 - (h.views / max) * 20} height={(h.views / max) * 20}>
            <title>{`${label(new Date(h.hour))} UTC: ${fmtInt(h.views)} views, ${fmtInt(h.sessions)} sessions`}</title>
          </rect>
        ))}
      </svg>
      <div className="dash-spark-axis">
        <span>{label(first)}</span>
        <span>Views per hour, UTC</span>
        <span>{label(last)}</span>
      </div>
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
  const d = o ? delta(o.today.sessions, o.yesterday.sessions) : null
  return (
    <Panel question="Who is here right now?" wide>
      <Status state={countries} />
      {c && (
        <div className="dash-tiles">
          <Tile label="Now" sub="sessions, last 5 min" window={c.now} />
          <Tile label="Today" sub={d ? `${d.arrow} ${d.text}` : humanSub(c.today)} subCls={d?.cls} window={c.today} />
          <Tile label="7 days" sub={humanSub(c.d7)} window={c.d7} />
          <Tile label="30 days" sub={humanSub(c.d30)} window={c.d30} />
        </div>
      )}
      {o && <Spark hours={o.hours} />}
    </Panel>
  )
}
