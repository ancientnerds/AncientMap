import { useEffect, useState, useRef, useCallback } from 'react'
import { config } from '../../config'
import NewsCard from '../news/NewsCard'
import type { LibrarySource, ParentRef } from '../../types/library'
import type { NewsItemData } from '../../types/news'

const TIER_LABELS: Record<number, { label: string; className: string }> = {
  1: { label: 'Academic', className: 'library-tier-academic' },
  2: { label: 'Reputable', className: 'library-tier-reputable' },
  3: { label: 'General', className: 'library-tier-general' },
}

const PARENT_LINKS: Record<string, { label: string; href: (id: string) => string }> = {
  story: { label: 'Story', href: (id) => `/news.html?highlight=${id}` },
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
  const [hoveredStory, setHoveredStory] = useState<NewsItemData | null>(null)
  const [hoverLoading, setHoverLoading] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>()
  const hoverCache = useRef<Map<string, NewsItemData>>(new Map())

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleStoryHover = useCallback((ref: ParentRef) => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    hoverTimer.current = setTimeout(async () => {
      // Check cache first
      const cached = hoverCache.current.get(ref.id)
      if (cached) {
        setHoveredStory(cached)
        return
      }
      setHoverLoading(true)
      try {
        const resp = await fetch(`${config.api.baseUrl}/news/item/${ref.id}`)
        if (!resp.ok) return
        const data: NewsItemData = await resp.json()
        hoverCache.current.set(ref.id, data)
        setHoveredStory(data)
      } catch { /* ignore */ } finally {
        setHoverLoading(false)
      }
    }, 200)
  }, [])

  const handleStoryLeave = useCallback(() => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    setHoveredStory(null)
    setHoverLoading(false)
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
                const link = PARENT_LINKS[ref.type]
                const isStory = ref.type === 'story'
                return (
                  <li
                    key={`${ref.type}-${ref.id}-${i}`}
                    className={isStory ? 'library-ref-story' : undefined}
                    onMouseEnter={isStory ? () => handleStoryHover(ref) : undefined}
                    onMouseLeave={isStory ? handleStoryLeave : undefined}
                  >
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
          </div>
        )}

        {/* Story hover preview */}
        {(hoveredStory || hoverLoading) && (
          <div className="library-story-preview" onMouseEnter={handleStoryLeave}>
            {hoverLoading && !hoveredStory && (
              <div className="library-loading">Loading story...</div>
            )}
            {hoveredStory && (() => {
              const item = hoveredStory
              const screenshotSrc = item.screenshot_url
                ? `${config.api.baseUrl}${item.screenshot_url.replace('/api', '')}`
                : item.video.thumbnail_url
              const deepLink = item.youtube_deep_url || item.youtube_url || '#'
              return (
                <div className="news-page-card">
                  <div className="news-page-card-body">
                    <NewsCard
                      size="lg"
                      headline={item.headline}
                      postText={item.post_text}
                      channelName={item.video.channel_name}
                      publishedAt={item.video.published_at}
                      significance={item.significance}
                      newsCategory={item.news_category}
                      speculativeTag={item.speculative_tag}
                      screenshotUrl={screenshotSrc}
                      deepLink={deepLink}
                      videoId={item.video.id}
                      videoTitle={item.video.title}
                      durationMinutes={item.video.duration_minutes}
                      timestampSeconds={item.timestamp_seconds}
                      siteName={item.site_name || item.site_name_extracted}
                      siteNameExtracted={item.site_name_extracted}
                      siteId={item.site_id}
                      siteCountry={item.site_country}
                      siteType={item.site_type}
                      sitePeriodName={item.site_period_name}
                      sitePeriodStart={item.site_period_start}
                      facts={item.facts}
                      webSources={item.web_sources}
                      verified={item.verified}
                    />
                  </div>
                </div>
              )
            })()}
          </div>
        )}
      </div>
    </div>
  )
}
