/**
 * NewsFeedPanel - Collapsible glass panel showing Lyra news feed items.
 * Docked on the right side of the globe view.
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { createPortal } from 'react-dom'
import { config } from '../config'
import type { NewsItemData, NewsFeedResponse } from '../types/news'
import { formatDuration, formatRelativeDate } from '../utils/formatters'
import { SiteBadges, CountryFlag } from './metadata'
import LazyImage from './LazyImage'
import { getSignificanceColor, getSignificanceLabel, getSignificanceCardStyle, getNewsCategoryLabel } from './news/significance'
import './news/news-cards.css'

const LyraProfileModal = lazy(() => import('./LyraProfileModal'))

interface Props {
  onClose: () => void
  onSiteHover?: (siteId: string | null) => void
  onSiteClick?: (siteName: string, lat: number, lon: number) => void
}

export default function NewsFeedPanel({ onClose, onSiteHover, onSiteClick }: Props) {
  const [items, setItems] = useState<NewsItemData[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const [online, setOnline] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

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

  const toggleExpand = (id: number, el: HTMLElement) => {
    const collapsing = expandedId === id
    setExpandedId(collapsing ? null : id)
    if (!collapsing) {
      requestAnimationFrame(() => {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      })
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
          <div
            key={item.id}
            className={`news-feed-item${expandedId === item.id ? ' expanded' : ''}${item.site_id ? ' has-site' : ''}`}
            style={item.significance ? getSignificanceCardStyle(item.significance) : undefined}
            onClick={(e) => toggleExpand(item.id, e.currentTarget)}
            onMouseEnter={() => item.site_id && onSiteHover?.(item.site_id)}
            onMouseLeave={() => item.site_id && onSiteHover?.(null)}
          >
            <div className="news-card-meta">
              <span className="news-card-channel">{item.video.channel_name}</span>
              <span className="news-feed-date">{formatRelativeDate(item.video.published_at)}</span>
              {item.significance != null && item.significance >= 7 && (
                <span className="news-significance-badge" style={{ color: getSignificanceColor(item.significance) }}>
                  <span className="news-significance-dot" style={{ background: getSignificanceColor(item.significance) }} />
                  {getSignificanceLabel(item.significance)}
                </span>
              )}
            </div>
            <div className="news-card-post-text">{item.post_text || item.headline}</div>

            {item.news_category && item.news_category !== 'general' && (
              <span className="news-category-pill">{getNewsCategoryLabel(item.news_category)}</span>
            )}

            {item.site_id && (
                <div className="news-feed-site-block">
                  <div className="news-feed-site-row">
                    {item.site_country && <CountryFlag country={item.site_country} size="sm" showName />}
                    <button
                      className="news-page-card-site-name"
                      onClick={(e) => { e.stopPropagation(); onSiteClick?.(item.site_name!, item.site_lat!, item.site_lon!) }}
                      title={`Show ${item.site_name || 'site'} on map`}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                        <circle cx="12" cy="10" r="3"></circle>
                      </svg>
                      {item.site_name || 'Show on Map'}
                    </button>
                  </div>
                  <SiteBadges category={item.site_type} period={item.site_period_name} periodStart={item.site_period_start} size="sm" />
                </div>
            )}

            {!item.site_id && item.site_name_extracted && (
              <div className="news-feed-site-row news-feed-site-unmatched">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.4">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                  <circle cx="12" cy="10" r="3"></circle>
                </svg>
                <span className="news-feed-site-unmatched-name">{item.site_name_extracted}</span>
              </div>
            )}

            {screenshotSrc && (
              <a
                className="news-card-thumb"
                href={deepLink}
                target="_blank"
                rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
              >
                <LazyImage src={screenshotSrc} alt="" />
                <svg className="news-card-play" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                </svg>
                {item.video.duration_minutes != null && (
                  <span className="news-card-duration">{formatDuration(item.video.duration_minutes)}</span>
                )}
                {item.timestamp_seconds != null && (
                  <span className="news-card-timestamp">▶ {formatDuration(item.timestamp_seconds / 60)}</span>
                )}
              </a>
            )}

            {expandedId === item.id && (
              <div className="news-card-expanded">
                {item.facts && item.facts.length > 0 && (
                  <ul className="news-card-facts">
                    {item.facts.map((fact, i) => (
                      <li key={i}>{fact}</li>
                    ))}
                  </ul>
                )}

                {(item.youtube_deep_url || item.youtube_url) && (
                  <a
                    className="news-card-watch"
                    href={deepLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                    </svg>
                    Watch on YouTube
                    {item.timestamp_range && <span className="news-card-ts"> ({item.timestamp_range})</span>}
                  </a>
                )}

                <div className="news-card-video-title">{item.video.title}</div>
              </div>
            )}
          </div>
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
