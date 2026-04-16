import { useEffect, useState } from 'react'
import { config } from '../../config'
import NewsCard, { newsItemToCardProps } from '../news/NewsCard'
import type { LibrarySource, ParentRef } from '../../types/library'
import type { NewsItemData } from '../../types/news'

const TIER_LABELS: Record<number, { label: string; className: string }> = {
  1: { label: 'Academic', className: 'library-tier-academic' },
  2: { label: 'Reputable', className: 'library-tier-reputable' },
  3: { label: 'General', className: 'library-tier-general' },
}

const PARENT_LINKS: Record<string, { label: string; href: (id: string) => string }> = {
  story: { label: 'Story', href: () => '/news.html' },
  journal: { label: 'Journal', href: () => '/articles.html' },
  research: { label: 'Research', href: (id) => `/research.html?id=${id}` },
  site: { label: 'Site', href: (id) => `/site.html?id=${id}` },
}

interface LibraryDetailCardProps {
  source: LibrarySource
  onClose: () => void
}

export default function LibraryDetailCard({ source, onClose }: LibraryDetailCardProps) {
  const tier = TIER_LABELS[source.reliability_tier]

  // Fetch all story items on mount so we can render inline cards
  const storyRefs = source.parent_refs.filter(r => r.type === 'story')
  const nonStoryRefs = source.parent_refs.filter(r => r.type !== 'story')
  const [storyItems, setStoryItems] = useState<Map<string, NewsItemData>>(new Map())

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  useEffect(() => {
    if (storyRefs.length === 0) return
    const controller = new AbortController()
    Promise.all(
      storyRefs.map(ref =>
        fetch(`${config.api.baseUrl}/news/item/${ref.id}`, { signal: controller.signal })
          .then(r => r.ok ? r.json() : null)
          .catch(() => null)
          .then(data => data ? [ref.id, data] as const : null)
      )
    ).then(results => {
      const map = new Map<string, NewsItemData>()
      for (const r of results) if (r) map.set(r[0], r[1])
      setStoryItems(map)
    })
    return () => controller.abort()
  }, [source.id])

  return (
    <div className="library-detail-backdrop" onClick={onClose}>
      <div className="library-detail-card" onClick={e => e.stopPropagation()}>
        <button className="library-detail-close" onClick={onClose}>&times;</button>
        <div className="library-detail-card-inner">

        <div className="library-detail-header">
          {source.domain && (
            <img
              className="library-detail-favicon"
              src={`https://www.google.com/s2/favicons?domain=${source.domain}&sz=64`}
              alt=""
              width={24}
              height={24}
            />
          )}
          <div>
            <h3 className="library-detail-title">{source.title}</h3>
            <span className="library-detail-domain">{source.domain}</span>
            {tier && <span className={`library-card-tier ${tier.className}`}>{tier.label}</span>}
          </div>
        </div>

        {source.snippet && (
          <p className="library-detail-snippet">{source.snippet}</p>
        )}

        <a
          className="library-detail-visit"
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Visit source &rarr;
        </a>

        {source.parent_refs.length > 0 && (
          <div className="library-detail-cited-in">
            <h4>Cited in</h4>

            {/* Non-story refs as text links */}
            {nonStoryRefs.length > 0 && (
              <ul className="library-detail-refs">
                {nonStoryRefs.map((ref: ParentRef, i: number) => {
                  const link = PARENT_LINKS[ref.type]
                  return (
                    <li key={`${ref.type}-${ref.id}-${i}`}>
                      <span className="library-card-type-pill">{link?.label || ref.type}</span>
                      {link ? (
                        <a href={link.href(ref.id)} target="_blank" rel="noopener noreferrer">{ref.title}</a>
                      ) : (
                        <span>{ref.title}</span>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}

            {/* Story refs as headline-only NewsCards */}
            {storyRefs.length > 0 && (
              <div className="gallery-stories-list">
                {storyRefs.map((ref, i) => {
                  const item = storyItems.get(ref.id)
                  if (!item) return (
                    <div key={`${ref.id}-${i}`} className="news-feed-item" style={{ opacity: 0.5 }}>
                      <div className="news-card-headline">{ref.title}</div>
                    </div>
                  )
                  return <NewsCard key={`${ref.id}-${i}`} size="sm" headlinesOnly {...newsItemToCardProps(item)} />
                })}
              </div>
            )}
          </div>
        )}
        </div>
      </div>
    </div>
  )
}
