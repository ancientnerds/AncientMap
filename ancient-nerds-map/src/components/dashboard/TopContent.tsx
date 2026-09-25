import { BarList, type BarItem } from './BarList'
import { fmtInt } from './format'
import { Panel, Status } from './Panel'
import type { ContentData, ContentRow } from './types'
import type { Loaded } from './useStats'

const MAIN_ORIGIN = 'https://ancientnerds.com'

/** A story or paper path as a title: the slug is the title with dashes, and
 *  a story's ends in its id. "/news-archive/howard-vyses-1837-excavation-8395"
 *  reads "Howard vyses 1837 excavation". */
export function readablePath(path: string): string {
  const slug = path.replace(/\/+$/, '').split('/').pop() ?? ''
  const words = slug.replace(/-\d+$/, '').replace(/-/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : path
}

/** A content row as a list item, ranked by people: the bar is the visitors,
 *  the hint the opens behind them when there were more, or what a search
 *  found. Paths read as titles and link to the page, a site keeps its
 *  country, and a search that found nothing says so. */
export function item(row: ContentRow): BarItem {
  const label = row.label || '—'
  const isPath = label.startsWith('/')
  const shown = isPath ? readablePath(label) : label
  const people = row.visitors ?? row.n
  let hint: string | undefined
  if (row.event_name === 'search') {
    if (row.results === 0) hint = 'no results'
    else if (row.results !== null) hint = `${fmtInt(row.results)} ${row.results === 1 ? 'result' : 'results'}`
  } else if (row.n > people) {
    hint = `${fmtInt(row.n)} opens`
  }
  return {
    key: `${row.event_name}:${label}`,
    label: row.country ? `${shown} · ${row.country}` : shown,
    value: people,
    hint,
    tone: row.event_name === 'search' && row.results === 0 ? 'warn' : undefined,
    href: isPath ? `${MAIN_ORIGIN}${label}` : undefined,
  }
}

/** Why a list is empty, named per list and never in the abstract. All four
 *  events fire since 2026-09-20 (story_open and paper_open from the lists,
 *  search once a visitor stops typing), so an empty list is a quiet window. */
const WHY_EMPTY: Record<string, string> = {
  Stories: 'nobody opened a story from a list in this window',
  Papers: 'nobody opened a paper from a list in this window',
  'Search terms': 'nobody searched in this window',
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
