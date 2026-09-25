import { BarList, type BarItem } from './BarList'
import { fmtInt } from './format'
import { HowCounted, Panel, Status } from './Panel'
import type { LogCoverage, LogFamily, LogHost, LogStatus, SourceRow, SourcesData } from './types'
import type { Loaded } from './useStats'

export type SourceBucket = 'search' | 'ai' | 'discord' | 'youtube' | 'direct' | 'other'

const BUCKET_LABELS: Array<[SourceBucket, string]> = [
  ['search', 'Search'],
  ['ai', 'AI assistants'],
  ['discord', 'Discord'],
  ['youtube', 'YouTube'],
  ['direct', 'Direct'],
  ['other', 'Other'],
]

const RAW_ROWS = 8

/** The founders' six buckets over pipeline/stats_analysis.py source_family(). */
export function sourceBucket(family: string): SourceBucket {
  const f = family.toLowerCase()
  if (f === 'google' || f === 'search') return 'search'
  if (f === 'ai') return 'ai'
  if (f === 'direct') return 'direct'
  if (f.includes('discord')) return 'discord'
  if (f.includes('youtube') || f.includes('youtu.be')) return 'youtube'
  return 'other'
}

/** Sessions per bucket, in the fixed display order. The taxonomy is fixed, so
 *  a bucket nobody arrived through keeps its row and reads 0 — but no rows at
 *  all is not "six zeroes", it is no data, and the list says so instead. */
export function bucketTotals(rows: SourceRow[]): Array<[SourceBucket, string, number]> {
  if (rows.length === 0) return []
  const totals: Record<SourceBucket, number> = { search: 0, ai: 0, discord: 0, youtube: 0, direct: 0, other: 0 }
  for (const r of rows) totals[sourceBucket(r.family)] += r.sessions
  return BUCKET_LABELS.map(([bucket, label]) => [bucket, label, totals[bucket]])
}

/** What nginx counted per family, with the bots it saw on the side. One bot is
 *  the live value on the ai family today, so the singular is not decoration. */
export function familyItem(f: LogFamily): BarItem {
  return {
    key: `log:${f.family}`,
    label: f.family,
    value: f.visits,
    hint: f.bots ? `+ ${fmtInt(f.bots)} ${f.bots === 1 ? 'bot' : 'bots'}` : undefined,
  }
}

/** One referring host as nginx counted it — the row that makes the panel's
 *  claim checkable against the Umami list above it. */
export function hostItem(h: LogHost): BarItem {
  return { key: `loghost:${h.host}`, label: h.host, value: h.visits }
}

/** What each answer means. BarList only paints `tone` on a row that has a
 *  `hint`, so a warn without a hint is a no-op — every status needs one. */
const STATUS_MEANING: Record<number, string> = {
  410: 'story withdrawn on purpose',
  499: 'visitor left before we answered',
  500: 'our fault',
  502: 'our fault',
  503: 'our fault',
  504: 'our fault',
}

/** An answer to a referred human that nothing else on this page can see. */
export function statusItem(s: LogStatus): BarItem {
  return {
    key: `status:${s.status}`,
    label: String(s.status),
    value: s.visits,
    hint: STATUS_MEANING[s.status] ?? 'unexpected',
    tone: s.status === 410 || s.status >= 500 ? 'warn' : undefined,
  }
}

/** How many pages Google had Chrome fetch ahead of a click. On 2026-09-25
 *  they were 279 of 479 search arrivals in the access log: counted as
 *  arrivals, they made Umami look as if it saw a third of the visitors. */
export function prefetchLine(n: number): string {
  if (n === 0) return ''
  const what = n === 1 ? '1 page' : `${fmtInt(n)} pages`
  return ` Not counted either: ${what} that Chrome prefetched for a Google result page (Sec-Purpose: prefetch) — fetched in case the searcher clicks, looked at by nobody unless they do, and a click on one shows up in Umami.`
}

/** Why "other" reads zero on a log that has lines in it. The status code does
 *  not separate a scanner from a visitor on its own: 17 lines of the live log
 *  are an SEO referrer-spam campaign that asks for the front page and is
 *  answered 200 (pipeline/referral_log.py UNKNOWN_HOST_MIN). */
export function spamLine(n: number): string {
  const what = n === 1 ? '1 arrival' : `${fmtInt(n)} arrivals`
  return `A status alone does not catch everything: ${what} in this window came from a host in no known family that we saw exactly once, which is what SEO referrer spam looks like — one request per throwaway domain, asking for the front page and answered 200 — so they are out of both lists and counted only here.`
}

function Coverage({ log }: { log: LogCoverage }) {
  return (
    <>
      <div className="dash-lists">
        <div>
          <h3>Arrivals nginx saw</h3>
          <BarList items={log.families.map(familyItem)} empty="No referred arrival in this window." />
        </div>
        <div>
          <h3>Answers nothing else can see</h3>
          <BarList items={log.statuses.map(statusItem)} empty="Every referred visitor got a page." />
        </div>
      </div>
      <h3>Hosts nginx saw</h3>
      <BarList items={log.hosts.map(hostItem)} empty="No referred arrival in this window." />
      <HowCounted>
        The upper half of this panel is Umami: sessions whose browser ran our script. This half is nginx:
        every request that arrived with a foreign referer, over {log.covered_days} days of the log (
        {fmtInt(log.lines)} lines, counted from 25 Sep 2026, when nginx began logging which requests
        are prefetches). Put one host against the other and compare views, not sessions: a visitor who
        comes back from Google three times is one Umami session and three arrivals. Measured over four
        days of the access log on 2026-09-25, Umami recorded 186 of about 207 real views from search
        (90 %); the rest loaded the tracker and sent nothing — Do Not Track, which the tracker honours on
        purpose, or a visitor gone before the page finished loading. An arrival is a page request we
        answered 200 or 410: redirects are not counted, because each is followed by its own 200, and 4xx
        is not counted, because every 404 and 403 in this log is a forged referer probing /wp-admin/ — a
        real 404 raises an event the Problems panel already ranks.{prefetchLine(log.prefetched)}{' '}
        {spamLine(log.unverified)} Our own development server is out of every list too. A 410 is a story
        we withdrew on purpose and Google still links to; it raises no event at all, which is why it is
        here and nowhere else.
      </HowCounted>
    </>
  )
}

/** Where the sessions came from, and how many arrivals the tracker missed. */
export function Sources({ state }: { state: Loaded<SourcesData> }) {
  const s = state.data
  return (
    <Panel question="Where do they come from, and how many do we miss?" wide>
      <Status state={state} />
      {s && (
        <>
          <div className="dash-lists">
            <div>
              <h3>Umami sessions by bucket</h3>
              <BarList
                items={bucketTotals(s.sources).map(([bucket, label, n]) => ({ key: bucket, label, value: n }))}
                empty="No sessions in this window."
              />
            </div>
            <div>
              <h3>Individual sources</h3>
              <BarList
                items={s.sources.slice(0, RAW_ROWS).map((r: SourceRow) => ({
                  key: r.source,
                  label: r.source,
                  value: r.sessions,
                  hint: `${fmtInt(r.views)} views`,
                }))}
                empty="No sources."
              />
            </div>
          </div>
          {s.log ? <Coverage log={s.log} /> : <p className="dash-note">{s.log_reason}</p>}
        </>
      )}
    </Panel>
  )
}
