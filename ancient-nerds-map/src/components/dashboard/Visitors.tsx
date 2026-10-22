import { BarList, type BarItem } from './BarList'
import { countryName, fmtDay, fmtInt, fmtStamp } from './format'
import { AxisChart, niceMax } from './Lines'
import { HowCounted, Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { Burst, RequestClass, RequestReport, SessionClass, SessionReason, VisitorsData } from './types'
import type { Loaded } from './useStats'

/** The four tiles: the two kinds of people, the scrapers, and the rest. */
const CLASS_TILES: Array<[SessionClass, string, string]> = [
  ['human', 'Humans', 'an act of their own, or a second page after a referral'],
  ['human_ai', 'From AI answers', 'humans an AI assistant sent'],
  ['scraper_js', 'JS scrapers', 'ran our JavaScript, marked by a machine rule'],
  ['unclear', 'Unclear', 'no proof either way'],
]

/** One stacked bar segment per class, people on the baseline. */
const CLASS_BARS: Array<[SessionClass, string]> = [
  ['human', 'dash-bar-human'],
  ['human_ai', 'dash-bar-paper'],
  ['undecided', 'dash-bar-amber'],
  ['unclear', 'dash-bar-muted'],
  ['scraper_js', 'dash-bar-red'],
]

/** Why a session is a JS scraper or stays unclear, in visitor_class's order. */
const REASONS: SessionReason[] = ['burst', 'volume', 'lockstep', 'no_pageview', 'one_page', 'cluster', 'multi_direct']

/** The request classes whose networks say who runs them. */
const ASN_CLASSES: RequestClass[] = ['scraper_nojs', 'robots_ignorer']

function ClassChart({ d }: { d: VisitorsData }) {
  const days = d.daily
  const totals = days.map(day => CLASS_BARS.reduce((sum, [cls]) => sum + day[cls], 0))
  const first = fmtDay(days[0].day)
  const last = fmtDay(days[days.length - 1].day)
  return (
    <AxisChart
      small
      left={{ max: niceMax(Math.max(...totals, 1)), format: v => fmtInt(Math.round(v)) }}
      bars={CLASS_BARS.map(([cls, className]) => ({ label: d.labels[cls], values: days.map(day => day[cls]), className }))}
      titles={days.map(day => `${fmtDay(day.day)}: ${CLASS_BARS.map(([cls]) => `${d.labels[cls]} ${fmtInt(day[cls])}`).join(', ')}`)}
      axis={[first, 'Sessions per UTC day, by class', last]}
      label={`Sessions per day by class from ${first} to ${last}`}
    />
  )
}

/** "1,204 clients · 310 from datacenters · 12 hit the trap · unverified" */
export function requestHint(r: RequestReport, cls: RequestClass): string {
  const c = r.classes[cls]
  const parts = [`${fmtInt(c.clients)} clients`]
  if (c.datacenter) parts.push(`${fmtInt(c.datacenter)} from datacenters`)
  if (c.honeypot) parts.push(`${fmtInt(c.honeypot)} hit the trap`)
  if (c.unverified) parts.push(c.unverified === c.clients ? 'unverified' : `${fmtInt(c.unverified)} unverified`)
  return parts.join(' · ')
}

/** Every request class that sent a page, biggest first. */
export function requestItems(r: RequestReport, labels: Record<string, string>): BarItem[] {
  return (Object.keys(r.classes) as RequestClass[])
    .filter(cls => r.classes[cls].requests > 0)
    .sort((a, b) => r.classes[b].requests - r.classes[a].requests)
    .map(cls => ({ key: `req:${cls}`, label: labels[cls], value: r.classes[cls].requests, hint: requestHint(r, cls), wrap: true }))
}

/** "22 Oct 16:42-16:54 UTC: 1,427 sessions of chrome / Windows 10 / 1280x1200 / en-US, mostly Singapore" */
export function burstLine(b: Burst): string {
  const what = [b.browser, b.os, b.screen, b.language].map(v => v ?? '?').join(' / ')
  const where = b.country && b.country !== '??' ? `, mostly ${countryName(b.country)}` : ''
  return `${fmtStamp(b.start)}-${fmtStamp(b.end).slice(-5)} UTC: ${fmtInt(b.sessions)} sessions of ${what}${where}`
}

/** The networks behind the two classes a published list cannot explain. */
function Networks({ r, labels }: { r: RequestReport; labels: Record<string, string> }) {
  const top = r.top_asns
  if (!top) return null
  return (
    <div className="dash-lists">
      {ASN_CLASSES.map(cls => (
        <div key={cls}>
          <h3>Networks: {labels[cls].toLowerCase()}</h3>
          <BarList
            items={top[cls].map(
              (a): BarItem => ({ key: `asn:${cls}:${a.asn}`, label: a.asn ? `AS${a.asn} ${a.name}` : a.name, value: a.clients, hint: 'clients', wrap: true })
            )}
            empty="None in the log so far."
          />
        </div>
      ))}
    </div>
  )
}

/** nginx's browser_js page requests beside Umami's page views, as totals. */
function BeaconCheck({ r }: { r: RequestReport }) {
  if (!r.covered_from) return null
  const { pages_with_js: nginx, umami_pageviews: umami } = r.beacon_check
  return (
    <p className="dash-note">
      Since {fmtStamp(r.covered_from)} UTC, on the server-rendered pages and without arrivals from a search engine:
      nginx saw {fmtInt(nginx)} page requests from browsers that ran our JavaScript, Umami counted {fmtInt(umami)}{' '}
      page views.
    </p>
  )
}

/**
 * Who is visiting - every session that ran our JavaScript by class, with the
 * rule behind each (Umami), and every page request by what sent it (nginx's
 * request log). Two sources, never joined per visitor.
 */
export function Visitors({ state }: { state: Loaded<VisitorsData> }) {
  const d = state.data
  const s = d?.sessions
  const req = d?.requests
  return (
    <Panel question="Who is visiting?" wide>
      <Status state={state} />
      {d && s && req && (
        <>
          <div className="dash-tiles">
            {CLASS_TILES.map(([cls, label, sub]) => (
              <Tile key={cls} label={label} value={s.classes[cls]} sub={sub} />
            ))}
          </div>
          {s.classes.undecided > 0 && (
            <p className="dash-note">
              Plus {fmtInt(s.classes.undecided)} just arrived and not decided yet, of {fmtInt(s.total)} sessions.
            </p>
          )}
          {d.daily.length >= 2 && <ClassChart d={d} />}
          <div className="dash-lists">
            <div>
              <h3>Sessions that are not confirmed humans, by rule</h3>
              <BarList
                items={REASONS.filter(r => s.reasons[r] > 0).map(
                  (r): BarItem => ({ key: `why:${r}`, label: d.labels[r], value: s.reasons[r], wrap: true })
                )}
                empty="Every session so far is a confirmed human."
              />
            </div>
            <div>
              <h3>Every page request, by what sent it</h3>
              {req.report ? (
                <BarList items={requestItems(req.report, d.labels)} empty="No page request in the log so far." />
              ) : (
                <p className="dash-status">{req.log_reason}</p>
              )}
            </div>
          </div>
          {req.report && <Networks r={req.report} labels={d.labels} />}
          {d.bursts.length > 0 && (
            <p className="dash-note">
              Bursts in the last 7 days: {d.bursts.map(burstLine).join('; ')}.
            </p>
          )}
          {s.humans_in_machine_groups > 0 && (
            <p className="dash-note">
              {fmtInt(s.humans_in_machine_groups)} confirmed{' '}
              {s.humans_in_machine_groups === 1
                ? "human shares a fingerprint with a burst or a day's volume and still counts"
                : "humans share fingerprints with a burst or a day's volume and still count"}{' '}
              as human: a rising number means traffic is pushing real visitors over the thresholds.
            </p>
          )}
          {req.report && <BeaconCheck r={req.report} />}
          {req.asn_reason && <p className="dash-note">{req.asn_reason}</p>}
          {req.report?.asn_as_of && (
            <p className="dash-note">Networks from iptoasn.com, as of {fmtStamp(req.report.asn_as_of)} UTC.</p>
          )}
        </>
      )}
      <HowCounted>
        Two sources, never joined per visitor - joining them would mean recomputing Umami's salted hash, which
        identifies visitors. The sessions come from Umami, so only from clients that ran our JavaScript. A session is
        human by the same rule as everywhere on this page (an act of its own, or a second page after arriving from
        a search, an assistant or a link); from AI answers when an assistant sent it. It is a JS scraper when its
        fingerprint - browser, operating system, screen size and language, never the country - started 8 or more
        sessions within 10 minutes, or 50 or more in one UTC day; those two rules never overrule a human. One rule
        does: 3 or more crawls of one fingerprint started in one minute (direct entry, 5 or more pages, no act of
        their own) mark every such crawl of it within a week as a scraper. It was made for 48 Chinese sessions of
        1 to 8 October 2026 that counted as human only through the second-page rule that held before 9 October, so
        the human counts of those days dropped by 48. A session that arrived under 30 minutes ago with no rule
        against it is undecided; the rest stays unclear, by the first that fits: no page view, a page and minute
        shared with 2 or more other sessions, a direct entry with several pages and no act, or one page and no
        act. The requests come from nginx's request log, which sees every client with its address: a known
        crawler counts only from its operator's published addresses (otherwise an impostor, and unverified where
        the operator publishes none); a browser counts as having run our JavaScript when the same address and
        browser sent one of our three beacons within two minutes of the page; without one it is a client without
        JavaScript, unless it sent Do Not Track or Global Privacy Control, which our tracker honours. The trap is
        a link only a client that ignores robots.txt follows. Datacenter networks are X4BNet's list, the network
        of an address a local copy of iptoasn.com. The page-view comparison sets the two sources side by side on
        the server-rendered pages only, as totals. Windows that start mid-day see only part of a day's volume, so
        a shorter window can mark slightly fewer scrapers; the human counts do not depend on it.
      </HowCounted>
    </Panel>
  )
}
