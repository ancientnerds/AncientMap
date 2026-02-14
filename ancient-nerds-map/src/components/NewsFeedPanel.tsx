/**
 * NewsFeedPanel - Collapsible glass panel showing Lyra news feed items.
 * Docked on the right side of the globe view.
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { createPortal } from 'react-dom'
import { config } from '../config'
import type { NewsItemData, NewsFeedResponse } from '../types/news'
import NewsCard from './news/NewsCard'
import './news/news-cards.css'

const LyraProfileModal = lazy(() => import('./LyraProfileModal'))

interface Props {
  onClose: () => void
  onSiteHover?: (siteId: string | null) => void
  onSiteClick?: (siteName: string, lat: number, lon: number) => void
  onAskLyra?: (newsItemId: number) => void
}

export default function NewsFeedPanel({ onClose, onSiteHover, onSiteClick, onAskLyra }: Props) {
  const [items, setItems] = useState<NewsItemData[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const [online, setOnline] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const fetchFeed = useCallback(async (pageNum: number, append: boolean = false) => {
    try {
      setLoading(true)
      setError(null)
      const resp = await fetch(`${config.api.baseUrl}/news/feed?page=${pageNum}&page_size=20&include_speculative=true`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: NewsFeedResponse = await resp.json()
      setItems(prev => append ? [...prev, ...data.items] : data.items)
      setTotalCount(data.total_count)
      setHasMore(data.has_more)
      setPage(pageNum)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchFeed(1)
  }, [fetchFeed])

  useEffect(() => {
    document.body.classList.add('news-feed-open')
    return () => { document.body.classList.remove('news-feed-open') }
  }, [])

  useEffect(() => {
    const check = () => {
      fetch(`${config.api.baseUrl}/news/lyra-status`)
        .then(r => r.ok ? r.json() : null)
        .then(d => setOnline(d ? d.status === 'online' : false))
        .catch(() => setOnline(false))
    }
    check()
    const id = setInterval(check, 60_000)
    return () => clearInterval(id)
  }, [])

  const loadMore = () => {
    if (hasMore && !loading) {
      fetchFeed(page + 1, true)
    }
  }


  return (
    <div className="news-feed-panel">
      <div className="news-feed-header">
        <div className="news-feed-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1"></path>
            <path d="M18 14v4h4"></path>
            <circle cx="18" cy="18" r="4"></circle>
          </svg>
          <span>News Feed</span>
          {totalCount > 0 && <span className="news-feed-badge">{totalCount}</span>}
        </div>
        <div className={`news-feed-live${online ? '' : ' offline'}`}>
          <span className="news-feed-live-dot" />
          <span className="news-feed-live-text">{online ? 'LIVE' : 'OFFLINE'}</span>
        </div>
        <div className="news-feed-actions">
          <button className="news-feed-btn" onClick={onClose} title="Close">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      </div>

      {/* Lyra intro */}
      <div className="news-feed-lyra">
        <img
          src="/lyra.png"
          alt="Lyra"
          className="news-feed-lyra-avatar lyra-avatar-clickable"
          onClick={() => setShowLyraProfile(true)}
        />
        <div className="news-feed-lyra-bubble">
          I watch every archaeology channel so you don't have to. Never miss a discovery!
        </div>
      </div>

      {/* Open in new tab button */}
      <a
        className="news-feed-open-tab"
        href="/news.html"
        target="_blank"
        rel="noopener noreferrer"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
          <polyline points="15 3 21 3 21 9"></polyline>
          <line x1="10" y1="14" x2="21" y2="3"></line>
        </svg>
        Open full news page
      </a>

      {/* Content */}
      <div className="news-feed-content" ref={scrollRef}>
        {/* AI disclosure */}
        <div className="news-feed-ai-notice">
          Content is AI-generated from YouTube video content. Always verify with original sources.
        </div>
        {error && (
          <div className="news-feed-error">
            {error}
            <button onClick={() => fetchFeed(1)}>Retry</button>
          </div>
        )}

        {!error && items.length === 0 && !loading && (
          <div className="news-feed-empty">No news items yet</div>
        )}

        {items.map(item => {
          const screenshotSrc = item.screenshot_url
            ? `${config.api.baseUrl}${item.screenshot_url.replace('/api', '')}`
            : item.video.thumbnail_url
          const deepLink = item.youtube_deep_url || item.youtube_url || '#'

          return (
            <NewsCard
              key={item.id}
              size="sm"
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
              onSiteLoaded={(site) => onSiteClick?.(site.title, site.coordinates[1], site.coordinates[0])}
              onSiteHover={(hovering) => onSiteHover?.(hovering && item.site_id ? item.site_id : null)}
              onAskLyra={onAskLyra ? () => onAskLyra(item.id) : undefined}
            />
          )
        })}

        {loading && (
          <div className="news-feed-loading">Loading...</div>
        )}

        {hasMore && !loading && (
          <button className="news-feed-load-more" onClick={(e) => { e.stopPropagation(); loadMore() }}>
            Load more
          </button>
        )}
      </div>

      {showLyraProfile && createPortal(
        <Suspense fallback={null}>
          <LyraProfileModal onClose={() => setShowLyraProfile(false)} />
        </Suspense>,
        document.body
      )}
    </div>
  )
}
