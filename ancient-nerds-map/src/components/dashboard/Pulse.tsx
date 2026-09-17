import { fmtInt, fmtShare } from './format'
import { Panel, Status } from './Panel'
import type { HourBucket, Overview } from './types'
import type { Loaded } from './useStats'

/** How many of the hourly buckets the strip shows: two days is readable at 390 px. */
const SPARK_HOURS = 48

/** Sign and size of today's change against yesterday at the same time of day. */
function delta(today: number, yesterday: number): { arrow: string; text: string; cls: string } {
  if (yesterday === 0) return { arrow: '', text: 'gestern 0', cls: '' }
  const pct = Math.round(((today - yesterday) / yesterday) * 100)
  if (pct === 0) return { arrow: '=', text: 'wie gestern', cls: '' }
  return pct > 0
    ? { arrow: '▲', text: `${pct} % zu gestern`, cls: 'dash-delta--up' }
    : { arrow: '▼', text: `${-pct} % zu gestern`, cls: 'dash-delta--down' }
}

function Spark({ hours }: { hours: HourBucket[] }) {
  const recent = hours.slice(-SPARK_HOURS)
  if (recent.length < 2) return null
  const max = Math.max(...recent.map(h => h.views), 1)
  const first = new Date(recent[0].hour)
  const last = new Date(recent[recent.length - 1].hour)
  const label = (d: Date) => `${String(d.getUTCDate()).padStart(2, '0')}.${String(d.getUTCMonth() + 1).padStart(2, '0')}. ${String(d.getUTCHours()).padStart(2, '0')} Uhr`
  return (
    <>
      <svg className="dash-spark" viewBox={`0 0 ${recent.length} 20`} preserveAspectRatio="none" role="img" aria-label={`Seitenaufrufe pro Stunde, letzte ${recent.length} Stunden`}>
        {recent.map((h, i) => (
          <rect key={h.hour} x={i + 0.15} width={0.7} y={20 - (h.views / max) * 20} height={(h.views / max) * 20}>
            <title>{`${label(new Date(h.hour))} UTC: ${fmtInt(h.views)} Aufrufe, ${fmtInt(h.sessions)} Sessions`}</title>
          </rect>
        ))}
      </svg>
      <div className="dash-spark-axis">
        <span>{label(first)}</span>
        <span>Aufrufe / Stunde, UTC</span>
        <span>{label(last)}</span>
      </div>
    </>
  )
}

/** Three headline numbers: live now, today against yesterday, the window's human sessions. */
export function Pulse({ state, days }: { state: Loaded<Overview>; days: number }) {
  const o = state.data
  const d = o ? delta(o.today.views, o.yesterday.views) : null
  return (
    <Panel question="Wie viel ist gerade los?" wide>
      <Status state={state} />
      {o && d && (
        <>
          <div className="dash-tiles">
            <div className="dash-tile">
              <span className="dash-tile-label">Jetzt</span>
              <span className="dash-tile-value">{fmtInt(o.today.live)}</span>
              <span className="dash-tile-sub">Sessions, letzte 5 min</span>
            </div>
            <div className="dash-tile">
              <span className="dash-tile-label">Heute</span>
              <span className="dash-tile-value">{fmtInt(o.today.views)}</span>
              <span className={`dash-tile-sub ${d.cls}`}>
                {d.arrow} {d.text}
              </span>
            </div>
            <div className="dash-tile">
              <span className="dash-tile-label">{days} Tage</span>
              <span className="dash-tile-value">{fmtInt(o.sessions.human)}</span>
              <span className="dash-tile-sub">
                menschliche Sessions, {fmtShare(o.sessions.human, o.sessions.all)} von {fmtInt(o.sessions.all)}
              </span>
            </div>
          </div>
          <Spark hours={o.hours} />
        </>
      )}
    </Panel>
  )
}
