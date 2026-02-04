/**
 * NewsFeedPanel - Collapsible glass panel showing Lyra news feed items
 * Can be docked on the right side or detached as a free-floating draggable window.
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { createPortal } from 'react-dom'
import { config } from '../config'

const LyraProfileModal = lazy(() => import('./LyraProfileModal'))

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

interface Props {
  onClose: () => void
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

export default function NewsFeedPanel({ onClose }: Props) {
  const [items, setItems] = useState<NewsItemData[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Detach / drag state
  const [detached, setDetached] = useState(false)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragStartRef = useRef({ x: 0, y: 0, posX: 0, posY: 0 })
  const savedDetachRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const fetchFeed = useCallback(async (pageNum: number, append: boolean = false) => {
    try {
      setLoading(true)
      setError(null)
      const resp = await fetch(`${config.api.baseUrl}/news/feed?page=${pageNum}&page_size=20`)
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

  // Remove body class when detached so right-side UI shifts back
  useEffect(() => {
    if (detached) {
      document.body.classList.remove('news-feed-open')
    } else {
      document.body.classList.add('news-feed-open')
    }
  }, [detached])

  // Drag handlers
  const handleTitleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!detached) return
    e.preventDefault()
    setIsDragging(true)
    dragStartRef.current = {
      x: e.clientX, y: e.clientY,
      posX: position.x, posY: position.y,
    }
  }, [detached, position])

  useEffect(() => {
    if (!isDragging) return
    const onMove = (e: MouseEvent) => {
      const dx = e.clientX - dragStartRef.current.x
      const dy = e.clientY - dragStartRef.current.y
      let newX = dragStartRef.current.posX + dx
      let newY = dragStartRef.current.posY + dy
      // Keep within viewport
      const w = panelRef.current?.offsetWidth ?? 340
      const h = panelRef.current?.offsetHeight ?? 500
      newX = Math.max(0, Math.min(window.innerWidth - w, newX))
      newY = Math.max(0, Math.min(window.innerHeight - h, newY))
      setPosition({ x: newX, y: newY })
    }
    const onUp = () => setIsDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [isDragging])

  const handleDetach = () => {
    if (savedDetachRef.current) {
      // Restore previous detached position and size
      const s = savedDetachRef.current
      setPosition({ x: s.x, y: s.y })
      setSize({ w: s.w, h: s.h })
    } else {
      // First detach: position where the docked panel is
      const rect = panelRef.current?.getBoundingClientRect()
      setPosition({
        x: rect ? rect.left : window.innerWidth - 360,
        y: rect ? rect.top : 40,
      })
      setSize(null)
    }
    setDetached(true)
  }

  const handleDock = () => {
    // Save current detached position + size before docking
    const el = panelRef.current
    if (el) {
      savedDetachRef.current = {
        x: position.x,
        y: position.y,
        w: el.offsetWidth,
        h: el.offsetHeight,
      }
    }
    setSize(null)
    setDetached(false)
  }

  const loadMore = () => {
    if (hasMore && !loading) {
      fetchFeed(page + 1, true)
    }
  }

  const toggleExpand = (id: number) => {
    setExpandedId(prev => prev === id ? null : id)
  }

  const panelClass = detached
    ? `news-feed-panel news-feed-detached${isDragging ? ' news-feed-dragging' : ''}`
    : 'news-feed-panel'

  const panelStyle: React.CSSProperties = detached
    ? {
        left: position.x,
        top: position.y,
        ...(size ? { width: size.w, height: size.h } : {}),
      }
    : {}

  return (
    <div className={panelClass} style={panelStyle} ref={panelRef}>
      {/* Header - draggable when detached */}
      <div
        className="news-feed-header"
        onMouseDown={handleTitleMouseDown}
        style={detached ? { cursor: 'grab' } : undefined}
      >
        <div className="news-feed-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1"></path>
            <path d="M18 14v4h4"></path>
            <circle cx="18" cy="18" r="4"></circle>
          </svg>
          <span>News Feed</span>
          {totalCount > 0 && <span className="news-feed-badge">{totalCount}</span>}
        </div>
        <div className="news-feed-actions">
          {/* Detach / Dock toggle */}
          {detached ? (
            <button className="news-feed-btn" onClick={handleDock} title="Dock to side">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2"></rect>
                <line x1="15" y1="3" x2="15" y2="21"></line>
              </svg>
            </button>
          ) : (
            <button className="news-feed-btn" onClick={handleDetach} title="Detach window">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="2" width="16" height="16" rx="2"></rect>
                <path d="M14 8h6v6"></path>
                <path d="M14 14L22 6"></path>
              </svg>
            </button>
          )}
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
        {error && (
          <div className="news-feed-error">
            {error}
            <button onClick={() => fetchFeed(1)}>Retry</button>
          </div>
        )}

        {!error && items.length === 0 && !loading && (
          <div className="news-feed-empty">No news items yet</div>
        )}

        {items.map(item => (
          <div
            key={item.id}
            className={`news-feed-item${expandedId === item.id ? ' expanded' : ''}`}
            onClick={() => toggleExpand(item.id)}
          >
            <div className="news-feed-item-header">
              {item.video.thumbnail_url && (
                <a
                  className="news-feed-thumbnail"
                  href={item.youtube_deep_url || item.youtube_url || '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                >
                  <img src={item.video.thumbnail_url} alt="" loading="lazy" />
                  <svg className="news-feed-play-icon" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                  </svg>
                </a>
              )}
              <div className="news-feed-headline">{item.headline}</div>
              <div className="news-feed-meta">
                <span className="news-feed-channel">{item.video.channel_name}</span>
                <span className="news-feed-date">{formatRelativeDate(item.created_at)}</span>
              </div>
            </div>

            {expandedId === item.id && (
              <div className="news-feed-expanded">
                <div className="news-feed-summary">{item.summary}</div>

                {item.facts && item.facts.length > 0 && (
                  <ul className="news-feed-facts">
                    {item.facts.map((fact, i) => (
                      <li key={i}>{fact}</li>
                    ))}
                  </ul>
                )}

                {(item.youtube_deep_url || item.youtube_url) && (
                  <a
                    className="news-feed-watch-btn"
                    href={item.youtube_deep_url || item.youtube_url || '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                    </svg>
                    Watch on YouTube
                    {item.timestamp_range && <span className="news-feed-timestamp"> ({item.timestamp_range})</span>}
                  </a>
                )}

                <div className="news-feed-video-title">{item.video.title}</div>
              </div>
            )}
          </div>
        ))}

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
