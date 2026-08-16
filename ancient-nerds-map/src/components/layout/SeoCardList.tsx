/**
 * Linked title-plus-blurb cards — one definition for the research library
 * and the journal listing (react-ssr Tasks 12/13), so the two hubs cannot
 * drift apart card-wise. (Started as the React counterpart of the Python
 * renderer's _link_card(); Task 16 deleted that side.)
 */

import { blurb } from '../../seo/text'

export interface SeoCardItem {
  href: string
  title: string
  summary: string | null
}

export default function SeoCardList({ items }: { items: SeoCardItem[] }) {
  return (
    <div className="story-archive-list">
      {items.map(item => {
        const summary = blurb(item.summary)
        return (
          <a key={item.href} className="story-archive-card" href={item.href}>
            <h3>{item.title}</h3>
            {summary && <p>{summary}</p>}
          </a>
        )
      })}
    </div>
  )
}
