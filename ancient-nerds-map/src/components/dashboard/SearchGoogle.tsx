import { BarList, type BarItem } from './BarList'
import { fmtDay, fmtInt } from './format'
import { AxisChart, niceMax, rollingMean } from './Lines'
import { HowCounted, Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { SearchData, SearchDay, SearchRow } from './types'
import type { Loaded } from './useStats'

const SITE = 'https://ancientnerds.com'

/** "+86 % on the 28 days before" — the sub-line of a count tile. */
export function changeLine(now: number, before: number): { text: string; cls: string } {
  if (before === 0) return { text: 'none in the 28 days before', cls: '' }
  const pct = Math.round((now / before - 1) * 100)
  return {
    text: `${pct >= 0 ? '+' : '−'}${Math.abs(pct)} % on the 28 days before`,
    cls: pct >= 0 ? 'dash-delta--up' : 'dash-delta--down',
  }
}

/** The position tile's sub-line: a smaller number is a higher place. */
export function positionLine(now: number | null, before: number | null): { text: string; cls: string } {
  if (now === null || before === null) return { text: 'no position in one of the windows', cls: '' }
  return {
    text: `was ${before.toFixed(1)}`,
    cls: now <= before ? 'dash-delta--up' : 'dash-delta--down',
  }
}

function rowHint(r: SearchRow): string {
  return `${fmtInt(r.impressions)} shown · pos ${r.position.toFixed(1)}`
}

/** Shown and clicked on one chart, each against its own axis - impressions
 *  run in thousands, clicks in tens, and on one scale the clicks would be a
 *  flat line on the floor. Thin: each day; thick: the 7-day average. */
function SearchChart({ days }: { days: SearchDay[] }) {
  const shown = days.map(d => d.impressions)
  const clicks = days.map(d => d.clicks)
  const first = fmtDay(days[0].day)
  const last = fmtDay(days[days.length - 1].day)
  return (
    <AxisChart
      left={{ max: niceMax(Math.max(...shown, 1)), format: v => fmtInt(Math.round(v)) }}
      right={{ max: niceMax(Math.max(...clicks, 1)), format: v => fmtInt(Math.round(v)) }}
      lines={[
        { label: 'shown per day', values: shown, className: 'dash-line-all-thin', unlisted: true },
        { label: 'clicks per day', values: clicks, className: 'dash-line-human-thin', side: 'right', unlisted: true },
        { label: 'shown, 7-day average (left axis)', values: rollingMean(shown), className: 'dash-line-all-bold' },
        { label: 'clicks, 7-day average (right axis)', values: rollingMean(clicks), className: 'dash-line-human-bold', side: 'right' },
      ]}
      titles={days.map(d => `${fmtDay(d.day)}: shown ${fmtInt(d.impressions)}, ${fmtInt(d.clicks)} clicks${d.position === null ? '' : `, position ${d.position.toFixed(1)}`}`)}
      axis={[first, 'Per day; thin lines each day, thick the 7-day average', last]}
      label={`Google impressions and clicks per day from ${first} to ${last}`}
    />
  )
}

/** Google's average position per day, upside down so that up is better: the
 *  climb from page three to page one is the clearest thing Search Console
 *  says about us, and as a number on a tile it had no history. */
function PositionChart({ days }: { days: SearchDay[] }) {
  const position = days.map(d => d.position)
  const top = niceMax(Math.max(...position.filter((v): v is number => v !== null), 1))
  const flip = (v: number | null) => (v === null ? null : top - v)
  const first = fmtDay(days[0].day)
  const last = fmtDay(days[days.length - 1].day)
  return (
    <AxisChart
      small
      left={{ max: top, format: v => String(Math.max(1, Math.round(top - v))) }}
      lines={[
        { label: 'position per day', values: position.map(flip), className: 'dash-line-human-thin', unlisted: true },
        { label: 'average position, 7-day average (1 is the top of the results)', values: rollingMean(position).map(flip), className: 'dash-line-human-bold' },
      ]}
      titles={days.map(d => `${fmtDay(d.day)}: ${d.position === null ? 'not shown' : `position ${d.position.toFixed(1)}`}`)}
      axis={[first, 'Average position, upside down: up is better', last]}
      label={`Google's average position per day from ${first} to ${last}`}
    />
  )
}

/**
 * How Google shows us — Search Console's side of the visit: how often a page
 * of ours appeared in Google's results, how often someone clicked, at which
 * average place, for which queries and on which pages. The windows are its
 * own: the last 28 finished days against the 28 before, and the whole history
 * for the lines.
 */
export function SearchGoogle({ state }: { state: Loaded<SearchData> }) {
  const d = state.data
  const cur = d?.current
  const prev = d?.previous
  return (
    <Panel question="How does Google see us?" wide>
      <Status state={state} />
      {d && (!cur || !prev || d.days.length < 2) && (
        <p className="dash-empty">Search Console has no data for the property yet.</p>
      )}
      {d && cur && prev && d.days.length >= 2 && (
        <>
          <div className="dash-tiles">
            <Tile label="Clicks, 28 days" value={cur.clicks} {...sub(changeLine(cur.clicks, prev.clicks))} />
            <Tile label="Shown, 28 days" value={cur.impressions} {...sub(changeLine(cur.impressions, prev.impressions))} />
            <Tile
              label="Average position"
              value={cur.position === null ? '–' : cur.position.toFixed(1)}
              {...sub(positionLine(cur.position, prev.position))}
            />
            {d.pages_shown && (
              <Tile
                label="Pages shown"
                value={d.pages_shown.current}
                {...sub(changeLine(d.pages_shown.current, d.pages_shown.previous))}
              />
            )}
          </div>
          <p className="dash-note">
            {fmtDay(cur.start)}–{fmtDay(cur.end)} against {fmtDay(prev.start)}–{fmtDay(prev.end)}. Search Console's
            newest finished day is {fmtDay(cur.end)}.
          </p>
          <SearchChart days={d.days} />
          <PositionChart days={d.days} />
          <div className="dash-lists">
            <div>
              <h3>Queries that brought clicks</h3>
              <BarList
                items={d.queries.map((q): BarItem => ({ key: `q:${q.query}`, label: q.query, value: q.clicks, hint: rowHint(q) }))}
                empty="No query brought a click in these 28 days."
              />
            </div>
            <div>
              <h3>Pages that got the clicks</h3>
              <BarList
                items={d.pages.map((p): BarItem => ({ key: `p:${p.path}`, label: p.path, value: p.clicks, hint: rowHint(p), href: `${SITE}${p.path}`, path: true }))}
                empty="No page got a click in these 28 days."
              />
            </div>
          </div>
        </>
      )}
      <HowCounted>
        Google Search Console, the domain property: "shown" is an impression - a page of ours in a result someone
        saw - and a click is a visit from that result. The average position is Google's own mean place in the
        results, 1 being the top; a smaller number is better. "Pages shown" counts the pages that appeared at least
        once in the window, which a page can only do once Google has indexed it; a page Google holds as a soft 404
        never appears in it. Search Console's numbers are final two to three days late, so both windows end on its
        newest finished day, not on today. The lines run from the property's first day with data. Refreshed every
        hour.
      </HowCounted>
    </Panel>
  )
}

function sub(line: { text: string; cls: string }): { sub: string; subCls?: string } {
  return line.cls ? { sub: line.text, subCls: line.cls } : { sub: line.text }
}
