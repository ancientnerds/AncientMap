/**
 * NewsFeedPage - Dedicated full-page news feed with grid layout.
 * Accessed via /news.html (separate Vite entry point).
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { getCategoryColor, getPeriodColor, categorizePeriod } from '../data/sites'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'

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
  post_text: string | null
  facts: string[] | null
  timestamp_range: string | null
  timestamp_seconds: number | null
  screenshot_url: string | null
  youtube_url: string | null
  youtube_deep_url: string | null
  video: NewsVideoInfo
  created_at: string
  site_id: string | null
  site_name: string | null
  site_lat: number | null
  site_lon: number | null
  site_type: string | null
  site_period_name: string | null
  site_period_start: number | null
  site_country: string | null
  site_name_extracted: string | null
}

interface NewsFeedResponse {
  items: NewsItemData[]
  total_count: number
  page: number
  has_more: boolean
}

interface NewsStats {
  total_items: number
  total_videos: number
  total_channels: number
  total_articles: number
  latest_item_date: string | null
}

interface NewsChannel {
  id: string
  name: string
}

interface NewsFilterSiteOption {
  id: string
  name: string
}

interface NewsFilters {
  channels: NewsChannel[]
  sites: NewsFilterSiteOption[]
  categories: string[]
  periods: string[]
  countries: string[]
}

interface ActiveFilters {
  channel: string | null
  site: string | null
  category: string | null
  period: string | null
  country: string | null
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

  // Stats bar state
  const [stats, setStats] = useState<NewsStats | null>(null)

  // Multi-dimension filter state
  const [filters, setFilters] = useState<NewsFilters | null>(null)
  const [activeFilters, setActiveFilters] = useState<ActiveFilters>({
    channel: null, site: null, category: null, period: null, country: null,
  })
  const [filtersExpanded, setFiltersExpanded] = useState(false)


  const fetchFeed = useCallback(async (pageNum: number, append: boolean = false, af?: ActiveFilters) => {
    try {
      setLoading(true)
      setError(null)
      let url = `${config.api.baseUrl}/news/feed?page=${pageNum}&page_size=30`
      const f = af || activeFilters
      if (f.channel) url += `&channel_id=${encodeURIComponent(f.channel)}`
      if (f.site) url += `&site_id=${encodeURIComponent(f.site)}`
      if (f.category) url += `&category=${encodeURIComponent(f.category)}`
      if (f.period) url += `&period=${encodeURIComponent(f.period)}`
      if (f.country) url += `&country=${encodeURIComponent(f.country)}`
      const resp = await fetch(url)
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
  }, [activeFilters])

  // Initial feed load
  useEffect(() => {
    fetchFeed(1)
  }, [fetchFeed])

  // Fetch stats on mount (non-blocking)
  useEffect(() => {
    fetch(`${config.api.baseUrl}/news/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setStats(data) })
      .catch(() => {})
  }, [])

  // Fetch filter options on mount
  useEffect(() => {
    fetch(`${config.api.baseUrl}/news/filters`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setFilters(data) })
      .catch(() => {})
  }, [])

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    if (!sentinelRef.current || !hasMore || loading) return
    const af = activeFilters
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          fetchFeed(page + 1, true, af)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchFeed, activeFilters])

  const toggleExpand = (id: number) => {
    setExpandedId(prev => prev === id ? null : id)
  }

  const handleFilterToggle = (dimension: keyof ActiveFilters, value: string | null) => {
    const newFilters = { ...activeFilters }
    newFilters[dimension] = activeFilters[dimension] === value ? null : value
    setActiveFilters(newFilters)
    setItems([])
    setPage(1)
    setHasMore(false)
    fetchFeed(1, false, newFilters)
  }

  const activeFilterCount = Object.values(activeFilters).filter(Boolean).length

  return (
    <div className="news-page">
      {/* Sticky header: brand + Lyra in one line */}
      <header className="news-page-header">
        <a href="/" className="news-page-brand">
          <img src="/an-logo.svg" alt="" className="news-page-logo" />
          <span className="news-page-brand-text">ANCIENT NERDS</span>
        </a>
        <div className="news-page-divider" />
        <img
          src="/lyra.png"
          alt="Lyra Wiskerbyte"
          className="news-page-avatar lyra-avatar-clickable"
          onClick={() => setShowLyraProfile(true)}
        />
        <div className="news-page-lyra-label">
          <span className="news-page-lyra-name" style={{ cursor: 'pointer' }} onClick={() => setShowLyraProfile(true)}>Lyra Wiskerbyte</span>
          <span className="news-page-lyra-badge" title="AI agent monitoring archaeology channels 24/7">Archaeological Agent</span>
        </div>
        <div className="news-page-count">
          {stats ? (
            <>
              <span className="news-page-stat-number">{stats.total_items}</span> stories from{' '}
              <span className="news-page-stat-number">{stats.total_videos}</span> videos across{' '}
              <span className="news-page-stat-number">{stats.total_channels}</span> channels
            </>
          ) : totalCount > 0 ? (
            <>{totalCount} stories</>
          ) : null}
        </div>
      </header>

      {/* Multi-dimension filter section */}
      {filters && (
        <div className="news-page-filters">
          <button
            className="news-page-filters-toggle"
            onClick={() => setFiltersExpanded(prev => !prev)}
          >
            <svg
              className={filtersExpanded ? 'rotated' : ''}
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
            >
              <path d="M9 18l6-6-6-6" />
            </svg>
            Filters
            {activeFilterCount > 0 && (
              <span className="news-page-filters-count">{activeFilterCount}</span>
            )}
          </button>

          {filtersExpanded && (
            <div className="news-page-filters-body">
              {/* Channel row */}
              {filters.channels.length > 0 && (
                <div className="news-page-filter-row">
                  <span className="news-page-filter-label">Channel</span>
                  <div className="news-page-chips">
                    {filters.channels.map(ch => (
                      <button
                        key={ch.id}
                        className={`news-page-chip${activeFilters.channel === ch.id ? ' active' : ''}`}
                        onClick={() => handleFilterToggle('channel', ch.id)}
                      >
                        {ch.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Category row */}
              {filters.categories.length > 0 && (
                <div className="news-page-filter-row">
                  <span className="news-page-filter-label">Category</span>
                  <div className="news-page-chips">
                    {filters.categories.map(cat => {
                      const color = getCategoryColor(cat)
                      return (
                        <button
                          key={cat}
                          className={`news-page-chip${activeFilters.category === cat ? ' active' : ''}`}
                          style={activeFilters.category !== cat && color ? { borderColor: color, color } : undefined}
                          onClick={() => handleFilterToggle('category', cat)}
                        >
                          {cat}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Period row */}
              {filters.periods.length > 0 && (
                <div className="news-page-filter-row">
                  <span className="news-page-filter-label">Period</span>
                  <div className="news-page-chips">
                    {filters.periods.map(p => {
                      const color = getPeriodColor(p)
                      return (
                        <button
                          key={p}
                          className={`news-page-chip${activeFilters.period === p ? ' active' : ''}`}
                          style={activeFilters.period !== p && color ? { borderColor: color, color } : undefined}
                          onClick={() => handleFilterToggle('period', p)}
                        >
                          {p}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Country row */}
              {filters.countries.length > 0 && (
                <div className="news-page-filter-row">
                  <span className="news-page-filter-label">Country</span>
                  <div className="news-page-chips">
                    {filters.countries.map(c => {
                      const flagUrl = getCountryFlatFlagUrl(c)
                      return (
                        <button
                          key={c}
                          className={`news-page-chip${activeFilters.country === c ? ' active' : ''}`}
                          onClick={() => handleFilterToggle('country', c)}
                        >
                          {flagUrl && <img className="news-page-chip-flag" src={flagUrl} alt="" />}
                          {c}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Site row */}
              {filters.sites.length > 0 && (
                <div className="news-page-filter-row">
                  <span className="news-page-filter-label">Site</span>
                  <div className="news-page-chips">
                    {filters.sites.map(s => (
                      <button
                        key={s.id}
                        className={`news-page-chip${activeFilters.site === s.id ? ' active' : ''}`}
                        onClick={() => handleFilterToggle('site', s.id)}
                      >
                        {s.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="news-page-error">
          {error}
          <button onClick={() => fetchFeed(1, false, activeFilters)}>Retry</button>
        </div>
      )}

      {/* Empty state */}
      {!error && items.length === 0 && !loading && (
        <div className="news-page-empty">No news items yet. Check back soon.</div>
      )}

      {/* Grid */}
      <div className="news-page-grid">
        {items.map(item => {
          const screenshotSrc = item.screenshot_url
            ? `${config.api.baseUrl}${item.screenshot_url.replace('/api', '')}`
            : item.video.thumbnail_url
          const deepLink = item.youtube_deep_url || item.youtube_url || '#'

          return (
          <div
            key={item.id}
            className={`news-page-card${expandedId === item.id ? ' expanded' : ''}`}
            onClick={() => toggleExpand(item.id)}
          >
            <div className="news-page-card-body">
              <div className="news-page-card-meta">
                <span className="news-page-card-channel">{item.video.channel_name}</span>
                <span className="news-page-card-date">{formatRelativeDate(item.video.published_at)}</span>
              </div>
              <div className="news-page-card-post-text">{item.post_text || item.headline}</div>

              {item.site_id && (() => {
                const period = item.site_period_name || (item.site_period_start != null ? categorizePeriod(item.site_period_start) : null)
                const isGenericType = !item.site_type || ['site', 'unknown'].includes(item.site_type.toLowerCase())
                const categoryColor = !isGenericType ? getCategoryColor(item.site_type!) : null
                const periodColor = period && period !== 'Unknown' ? getPeriodColor(period) : null
                const flagUrl = item.site_country ? getCountryFlatFlagUrl(item.site_country) : null
                return (
                  <div className="news-feed-site-block">
                    <div className="news-feed-site-row">
                      <span className="news-page-card-site-name">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                          <circle cx="12" cy="10" r="3"></circle>
                        </svg>
                        {item.site_name || item.site_name_extracted}
                      </span>
                      {flagUrl && <img className="news-feed-site-flag" src={flagUrl} alt={item.site_country || ''} />}
                    </div>
                    {(categoryColor || periodColor) && (
                      <div className="news-feed-site-badges">
                        {categoryColor && <span className="news-feed-site-badge" style={{ borderColor: categoryColor, color: categoryColor }}>{item.site_type}</span>}
                        {periodColor && <span className="news-feed-site-badge" style={{ borderColor: periodColor, color: periodColor }}>{period}</span>}
                      </div>
                    )}
                  </div>
                )
              })()}

              {!item.site_id && item.site_name_extracted && (
                <div className="news-feed-site-row news-feed-site-unmatched">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.4">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                    <circle cx="12" cy="10" r="3"></circle>
                  </svg>
                  <span className="news-feed-site-unmatched-name">{item.site_name_extracted}</span>
                </div>
              )}

              {screenshotSrc && (
                <a
                  className="news-page-card-thumb"
                  href={deepLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                >
                  <img src={screenshotSrc} alt="" loading="lazy" />
                  <svg className="news-page-card-play" width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                  </svg>
                </a>
              )}

              {expandedId === item.id && (
                <div className="news-page-card-expanded">
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
                      href={deepLink}
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
          )
        })}
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
