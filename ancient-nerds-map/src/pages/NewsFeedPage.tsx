/**
 * NewsFeedPage - Dedicated full-page news feed with grid layout.
 * Accessed via /news.html (separate Vite entry point).
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'

const LyraProfileModal = lazy(() => import('../components/LyraProfileModal'))

interface NewsVideoInfo {
  id: string
  title: string
  channel_name: string
  channel_id: string
  published_at: string
  thumbnail_url: string | null
  duration_minutes: number | null
}

interface NewsItemData {
  id: number
  headline: string
  summary: string
  facts: string[] | null
  timestamp_range: string | null
  timestamp_seconds: number | null
  youtube_url: string | null
  youtube_deep_url: string | null
  video: NewsVideoInfo
  created_at: string
}

interface NewsFeedResponse {
  items: NewsItemData[]
  total_count: number
  page: number
  has_more: boolean
}

function formatRelativeDate(isoDate: string): string {
  const date = new Date(isoDate)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffHours < 1) return 'Just now'
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function NewsFeedPage() {
  const [items, setItems] = useState<NewsItemData[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const sentinelRef = useRef<HTMLDivElement>(null)

  const fetchFeed = useCallback(async (pageNum: number, append: boolean = false) => {
    try {
      setLoading(true)
      setError(null)
      const resp = await fetch(`${config.api.baseUrl}/news/feed?page=${pageNum}&page_size=30`)
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

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    if (!sentinelRef.current || !hasMore || loading) return
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          fetchFeed(page + 1, true)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchFeed])

  const toggleExpand = (id: number) => {
    setExpandedId(prev => prev === id ? null : id)
  }

  return (
    <div className="news-page">
      {/* Header with Lyra branding */}
      <header className="news-page-header">
        <a href="/" className="news-page-back" title="Back to map">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5"></path>
            <path d="M12 19l-7-7 7-7"></path>
          </svg>
        </a>
        <div className="news-page-lyra-intro">
          <img
            src="/lyra.png"
            alt="Lyra Wiskerbyte"
            className="news-page-avatar lyra-avatar-clickable"
            onClick={() => setShowLyraProfile(true)}
          />
          <div className="news-page-lyra-speech">
            <div className="news-page-lyra-name">Lyra Wiskerbyte <span className="news-page-lyra-role">(Ancient Nerds Agent)</span></div>
            <div className="news-page-lyra-tagline">
              I watch every archaeology channel so you don't have to. Never miss a discovery, a dig update, or a wild ancient mystery.
            </div>
          </div>
        </div>
        {totalCount > 0 && (
          <div className="news-page-count">{totalCount} stories</div>
        )}
      </header>

      {/* Error state */}
      {error && (
        <div className="news-page-error">
          {error}
          <button onClick={() => fetchFeed(1)}>Retry</button>
        </div>
      )}

      {/* Empty state */}
      {!error && items.length === 0 && !loading && (
        <div className="news-page-empty">No news items yet. Check back soon.</div>
      )}

      {/* Grid */}
      <div className="news-page-grid">
        {items.map(item => (
          <div
            key={item.id}
            className={`news-page-card${expandedId === item.id ? ' expanded' : ''}`}
            onClick={() => toggleExpand(item.id)}
          >
            {item.video.thumbnail_url && (
              <a
                className="news-page-card-thumb"
                href={item.youtube_deep_url || item.youtube_url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
              >
                <img src={item.video.thumbnail_url} alt="" loading="lazy" />
                <svg className="news-page-card-play" width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                </svg>
              </a>
            )}
            <div className="news-page-card-body">
              <div className="news-page-card-headline">{item.headline}</div>
              <div className="news-page-card-meta">
                <span className="news-page-card-channel">{item.video.channel_name}</span>
                <span className="news-page-card-date">{formatRelativeDate(item.created_at)}</span>
              </div>

              {expandedId === item.id && (
                <div className="news-page-card-expanded">
                  <div className="news-page-card-summary">{item.summary}</div>

                  {item.facts && item.facts.length > 0 && (
                    <ul className="news-page-card-facts">
                      {item.facts.map((fact, i) => (
                        <li key={i}>{fact}</li>
                      ))}
                    </ul>
                  )}

                  {(item.youtube_deep_url || item.youtube_url) && (
                    <a
                      className="news-page-card-watch"
                      href={item.youtube_deep_url || item.youtube_url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={e => e.stopPropagation()}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                      </svg>
                      Watch on YouTube
                      {item.timestamp_range && <span className="news-page-card-ts"> ({item.timestamp_range})</span>}
                    </a>
                  )}

                  <div className="news-page-card-video-title">{item.video.title}</div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Loading / infinite scroll sentinel */}
      {loading && (
        <div className="news-page-loading">Loading...</div>
      )}
      <div ref={sentinelRef} style={{ height: 1 }} />

      {showLyraProfile && (
        <Suspense fallback={null}>
          <LyraProfileModal onClose={() => setShowLyraProfile(false)} />
        </Suspense>
      )}
    </div>
  )
}
