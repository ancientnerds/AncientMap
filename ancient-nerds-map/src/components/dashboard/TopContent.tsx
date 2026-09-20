import { BarList, type BarItem } from './BarList'
import { Panel, Status } from './Panel'
import type { ContentData, ContentRow } from './types'
import type { Loaded } from './useStats'

const MAIN_ORIGIN = 'https://ancientnerds.com'

/** A content row as a list item; paths become links, a site keeps its country,
 *  and a search that found nothing says so. */
export function item(row: ContentRow): BarItem {
  const label = row.label || '—'
  const empty = row.results === 0
  return {
    key: `${row.event_name}:${label}`,
    label: row.country ? `${label} · ${row.country}` : label,
    value: row.n,
    hint: empty ? 'no results' : undefined,
    tone: empty ? 'warn' : undefined,
    href: label.startsWith('/') ? `${MAIN_ORIGIN}${label}` : undefined,
  }
}

/** Why a list is empty, named per list and never in the abstract. Verified
 *  2026-09-19 against the whole events table, not a window: story_open,
 *  paper_open and search had never been recorded, not once. The search line
 *  names a bug on purpose — ticket T2 in the build plan. Describing a known
 *  defect as a design choice ("reports only once a visitor settles on a term")
 *  would be the worst sentence on the page.
 *
 *  The sentence is built from the response and not hard-coded, because the day
 *  one of those events starts firing — which is what T2 is for — a fixed
 *  "never fired, not once" would sit directly under the ranked list of it. */
const WHY_EMPTY: Record<string, string> = {
  Stories: 'the story list raises no open event yet (story_open has never fired)',
  Papers: 'the paper list raises no open event yet (paper_open has never fired)',
  'Search terms':
    'search is swallowed by a bug in useSiteSearch (ticket T2), so an empty search list here is our fault, not a finding',
  Sites: 'nobody opened a site in this window',
}

/** "Only what the site actually reports is listed." plus a clause per empty
 *  list — and nothing else when every list has rows. */
export function emptyNote(titles: string[]): string {
  const head = 'Only what the site actually reports is listed.'
  if (titles.length === 0) return head
  const why = titles.map(t => `${t}: ${WHY_EMPTY[t]}`).join('; ')
  return `${head} Nothing to show under ${why}.`
}

/** The most opened sites, and whatever else the site has actually reported. */
export function TopContent({ state }: { state: Loaded<ContentData> }) {
  const c = state.data
  // The empty sentence travels with every list even though only the filled
  // ones are drawn: BarList requires it, and the day one of the three dead
  // events starts firing this panel must already know what to say when its
  // window happens to be quiet.
  const lists: Array<[string, ContentRow[], string]> = [
    ['Sites', c?.sites ?? [], 'No site opened.'],
    ['Search terms', c?.searches ?? [], 'No search.'],
    ['Stories', c?.stories ?? [], 'No story opened.'],
    ['Papers', c?.papers ?? [], 'No paper opened.'],
  ]
  const filled = lists.filter(([, rows]) => rows.length > 0)
  const bare = lists.filter(([, rows]) => rows.length === 0).map(([title]) => title)
  return (
    <Panel question="What gets opened, what gets searched?" wide>
      <Status state={state} />
      {c && (
        <>
          {filled.length === 0 ? (
            <p className="dash-empty">Nothing was opened in this window.</p>
          ) : (
            <div className="dash-lists">
              {filled.map(([title, rows, empty]) => (
                <div key={title}>
                  <h3>{title}</h3>
                  <BarList items={rows.map(item)} empty={empty} />
                </div>
              ))}
            </div>
          )}
          <p className="dash-note">{emptyNote(bare)}</p>
        </>
      )}
    </Panel>
  )
}
