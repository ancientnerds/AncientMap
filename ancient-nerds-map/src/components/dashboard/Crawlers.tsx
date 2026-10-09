import { BarList, type BarItem } from './BarList'
import { fmtInt, fmtStamp } from './format'
import { HowCounted, Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { CrawlerBot, CrawlerKind, CrawlersData } from './types'
import type { Loaded } from './useStats'

const SITE = 'https://ancientnerds.com'

/** The four kinds that answer the panel's question, in the order they matter
 *  for being found: a search index first, a person's AI question second. */
const KIND_TILES: Array<[CrawlerKind, string, string]> = [
  ['search', 'Search engines', 'page fetches by Google, Bing and the rest'],
  ['ai_user', 'AI for a person', 'an assistant read a page to answer someone'],
  ['ai_search', 'AI search indexes', 'OAI-SearchBot, PerplexityBot, Claude-SearchBot'],
  ['training', 'AI training', 'GPTBot, ClaudeBot, CCBot and others'],
]

/** "200: 1,204 · 410: 31" in the order 2xx, 3xx, 4xx, 5xx. */
export function statusHint(bot: CrawlerBot): string {
  const classes = Object.entries(bot.statuses).sort(([a], [b]) => a.localeCompare(b))
  return [`${fmtInt(bot.pages)} pages`, ...classes.map(([cls, n]) => `${cls} ${fmtInt(n)}`)].join(' · ')
}

export function botItem(bot: CrawlerBot): BarItem {
  const mark = bot.verified === null ? ' (unverified)' : ''
  return { key: `bot:${bot.bot}`, label: `${bot.bot}${mark}`, value: bot.requests, hint: statusHint(bot) }
}

/**
 * Who crawls us — which search engines and AI systems fetched our pages in
 * the range, from nginx's crawler log, each line checked against the
 * operator's published addresses.
 */
export function Crawlers({ state }: { state: Loaded<CrawlersData> }) {
  const d = state.data
  const r = d?.report
  const byKind = (kind: CrawlerKind) =>
    (r?.bots ?? []).filter(b => b.kind === kind).reduce((sum, b) => sum + b.requests, 0)
  return (
    <Panel question="Who crawls us?" wide>
      <Status state={state} />
      {d && !r && <p className="dash-status">{d.log_reason}</p>}
      {r && (
        <>
          <div className="dash-tiles">
            {KIND_TILES.map(([kind, label, sub]) => (
              <Tile key={kind} label={label} value={byKind(kind)} sub={sub} />
            ))}
          </div>
          <div className="dash-lists">
            <div>
              <h3>Fetches per bot</h3>
              <BarList items={r.bots.map(botItem)} empty="No crawler fetched a page in this window." />
            </div>
            <div>
              <h3>Pages AI assistants read for someone</h3>
              <BarList
                items={r.ai_user_pages.map(
                  (p): BarItem => ({ key: `ai:${p.path}:${p.bot}`, label: p.path, value: p.requests, hint: p.bot, href: `${SITE}${p.path}`, path: true })
                )}
                empty="No assistant fetched a page for a person in this window."
              />
            </div>
          </div>
          {r.impostors.length > 0 && (
            <p className="dash-note">
              Not counted: {r.impostors.map(i => `${fmtInt(i.requests)} claiming to be ${i.bot}`).join(', ')} - from
              addresses their operator does not publish.
            </p>
          )}
          {r.covered_from && <p className="dash-note">The crawler log starts {fmtStamp(r.covered_from)} UTC.</p>}
        </>
      )}
      <HowCounted>
        nginx writes every page request whose user agent names a known crawler to its own log; assets, data files
        and images are left out, so a count is pages and sitemaps, not files. A user agent is only a claim, so a
        request counts only when it came from an address Google, Bing, OpenAI, Perplexity or Apple publish for that
        crawler; the rest is listed apart as an impostor. Anthropic and the smaller operators publish no addresses,
        and their bots are marked unverified. "AI for a person" is the clearest sign of being an answer: ChatGPT,
        Claude, Perplexity or Mistral read the page because someone asked them something. The log starts with the
        deploy of 9 October 2026; the server's older access log is not readable for the dashboard.
      </HowCounted>
    </Panel>
  )
}
