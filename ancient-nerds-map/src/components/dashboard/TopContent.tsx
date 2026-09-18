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

/** The most opened sites, stories and papers, and what people typed into the search. */
export function TopContent({ state }: { state: Loaded<ContentData> }) {
  const c = state.data
  return (
    <Panel question="What gets opened, what gets searched?" wide>
      <Status state={state} />
      {c && (
        <div className="dash-lists">
          <div>
            <h3>Sites</h3>
            <BarList items={c.sites.map(item)} empty="No site opened." />
          </div>
          <div>
            <h3>Search terms</h3>
            <BarList items={c.searches.map(item)} empty="No search." />
          </div>
          <div>
            <h3>Stories</h3>
            <BarList items={c.stories.map(item)} empty="No story opened." />
          </div>
          <div>
            <h3>Papers</h3>
            <BarList items={c.papers.map(item)} empty="No paper opened." />
          </div>
        </div>
      )}
    </Panel>
  )
}
