import { useEffect, useState, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
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
  const [storyData, setStoryData] = useState<NewsItemData | null>(null)
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>()
  const leaveTimer = useRef<ReturnType<typeof setTimeout>>()
  const cache = useRef<Map<string, NewsItemData>>(new Map())

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleStoryEnter = useCallback((ref: ParentRef) => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    if (leaveTimer.current) clearTimeout(leaveTimer.current)
    hoverTimer.current = setTimeout(async () => {
      const cached = cache.current.get(ref.id)
      if (cached) { setStoryData(cached); return }
      try {
        const resp = await fetch(`${config.api.baseUrl}/news/item/${ref.id}`)
        if (!resp.ok) return
        const data: NewsItemData = await resp.json()
        cache.current.set(ref.id, data)
        setStoryData(data)
      } catch { /* ignore */ }
    }, 200)
  }, [])

  const handleStoryLeave = useCallback(() => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    leaveTimer.current = setTimeout(() => setStoryData(null), 200)
  }, [])

  const keepOpen = useCallback(() => {
    if (leaveTimer.current) clearTimeout(leaveTimer.current)
  }, [])

  const dismiss = useCallback(() => {
    setStoryData(null)
  }, [])

  return (
    <div className="library-detail-backdrop" onClick={onClose}>
      <div className="library-detail-card" onClick={e => e.stopPropagation()}>
        <button className="library-detail-close" onClick={onClose}>&times;</button>

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
            <ul className="library-detail-refs">
              {source.parent_refs.map((ref: ParentRef, i: number) => {
                const isStory = ref.type === 'story'
                const link = PARENT_LINKS[ref.type]
                return (
                  <li
                    key={`${ref.type}-${ref.id}-${i}`}
                    className={isStory ? 'library-ref-story' : undefined}
                    onMouseEnter={isStory ? () => handleStoryEnter(ref) : undefined}
                    onMouseLeave={isStory ? handleStoryLeave : undefined}
                  >
                    <span className="library-card-type-pill">{isStory ? 'Story' : link?.label || ref.type}</span>
                    {isStory ? (
                      <span>{ref.title}</span>
                    ) : link ? (
                      <a href={link.href(ref.id)} target="_blank" rel="noopener noreferrer">{ref.title}</a>
                    ) : (
                      <span>{ref.title}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>

      {/* Story preview — fixed top-right, uses citation-popover class for identical look */}
      {storyData && createPortal(
        <div
          className="citation-popover library-story-fixed"
          onMouseEnter={keepOpen}
          onMouseLeave={dismiss}
        >
          <NewsCard size="sm" {...newsItemToCardProps(storyData)} />
        </div>,
        document.body
      )}
    </div>
  )
}
