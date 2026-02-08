/**
 * NewsFeedPage - Dedicated full-page news feed with grid layout.
 * Accessed via /news.html (separate Vite entry point).
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { getCategoryColor, getPeriodColor } from '../data/sites'
import { DataStore } from '../data/DataStore'
import type { SiteData } from '../data/sites'
import type { NewsItemData, NewsFeedResponse, NewsStats, NewsFilters, ActiveFilters } from '../types/news'
import { formatDuration, formatRelativeDate } from '../utils/formatters'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { apiDetailToSiteData } from '../utils/siteApi'
import { SiteBadges, CountryFlag } from '../components/metadata'
import { SitePopupOverlay } from '../components/SitePopupOverlay'
import LazyImage from '../components/LazyImage'
import { getSignificanceColor, getSignificanceLabel, getSignificanceCardStyle, getNewsCategoryLabel } from '../components/news/significance'
import '../components/news/news-cards.css'

const LyraProfileModal = lazy(() => import('../components/LyraProfileModal'))

export default function NewsFeedPage() {
  const [items, setItems] = useState<NewsItemData[]>([])
  const [, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const pageRef = useRef<HTMLDivElement>(null)
  const [columnCount, setColumnCount] = useState(3)

  // Pull-to-refresh — single enum prevents conflicting states
  const [pullY, setPullY] = useState(0)
  const [pullPhase, setPullPhase] = useState<'idle' | 'refreshing' | 'done'>('idle')
  const refreshingRef = useRef(false)
  const doneTimer = useRef(0)

  // Site popup
  const [selectedSite, setSelectedSite] = useState<SiteData | null>(null)
  const [loadingSiteId, setLoadingSiteId] = useState<string | null>(null)

  // Live updates
  const [online, setOnline] = useState(true)
  const [newItemIds, setNewItemIds] = useState<Set<number>>(new Set())
  const itemsRef = useRef<NewsItemData[]>([])

  useEffect(() => {
    const el = gridRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      const w = entry.contentRect.width
      const cols = Math.max(1, Math.floor(w / 300))
      setColumnCount(cols)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Stats bar state
  const [stats, setStats] = useState<NewsStats | null>(null)

  // Multi-dimension filter state
  const [filters, setFilters] = useState<NewsFilters | null>(null)
  const [activeFilters, setActiveFilters] = useState<ActiveFilters>({
    channel: null, site: null, category: null, period: null, country: null,
    min_significance: null, news_category: null, sort: null,
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
      if (f.min_significance) url += `&min_significance=${f.min_significance}`
      if (f.news_category) url += `&news_category=${encodeURIComponent(f.news_category)}`
      if (f.sort) url += `&sort=${encodeURIComponent(f.sort)}`
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

  const PULL_THRESHOLD = 70

  const doRefresh = useCallback(async () => {
    window.clearTimeout(doneTimer.current)
    setPullPhase('refreshing')
    refreshingRef.current = true
    const t0 = Date.now()
    await fetchFeed(1, false, activeFilters)
    fetch(`${config.api.baseUrl}/news/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStats(d) })
      .catch(() => {})
    const elapsed = Date.now() - t0
    if (elapsed < 600) await new Promise(r => setTimeout(r, 600 - elapsed))
    setPullPhase('done')
    doneTimer.current = window.setTimeout(() => {
      setPullPhase('idle')
      refreshingRef.current = false   // unlock AFTER done phase ends
    }, 900)
  }, [fetchFeed, activeFilters])

  const doRefreshRef = useRef(doRefresh)
  doRefreshRef.current = doRefresh

  // Initial feed load
  useEffect(() => {
    fetchFeed(1)
  }, [fetchFeed])

  // Load source metadata on mount (for SitePopup display names)
  useEffect(() => { DataStore.loadSources() }, [])

  // Fetch stats on mount (non-blocking)
  useEffect(() => {
    fetch(`${config.api.baseUrl}/news/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setStats(data) })
      .catch(() => {})
  }, [])

  // Lyra heartbeat — drives the LIVE/OFFLINE LED
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

  // Keep itemsRef in sync for polling
  useEffect(() => { itemsRef.current = items }, [items])

  // Live polling — check for new items every 30s
  useEffect(() => {
    const poll = async () => {
      try {
        const resp = await fetch(`${config.api.baseUrl}/news/feed?page=1&page_size=5`)
        if (!resp.ok) return
        const data: NewsFeedResponse = await resp.json()
        const existingIds = new Set(itemsRef.current.map(i => i.id))
        const fresh = data.items.filter(i => !existingIds.has(i.id))
        if (fresh.length > 0) {
          setNewItemIds(prev => new Set([...prev, ...fresh.map(i => i.id)]))
          setItems(prev => [...fresh, ...prev])
          setTotalCount(data.total_count)
        }
      } catch { /* ignore — lyra-status drives the LED */ }
    }
    const id = setInterval(poll, 30_000)
    return () => clearInterval(id)
  }, [])

  // Pull-to-refresh: touch (mobile) + wheel/trackpad (desktop)
  useEffect(() => {
    const el = pageRef.current
    if (!el) return

    // --- Touch (mobile) ---
    let startY = 0
    let pulling = false
    let currentPull = 0

    const onTouchStart = (e: TouchEvent) => {
      if (el.scrollTop <= 0 && !refreshingRef.current) {
        startY = e.touches[0].clientY
      }
    }

    const onTouchMove = (e: TouchEvent) => {
      if (!startY || refreshingRef.current) return
      if (el.scrollTop > 0) {
        startY = 0
        currentPull = 0
        setPullY(0)
        return
      }
      const dy = e.touches[0].clientY - startY
      if (dy > 10) {
        pulling = true
        e.preventDefault()
        currentPull = Math.min(dy * 0.4, 100)
        setPullY(currentPull)
      }
    }

    const onTouchEnd = () => {
      if (pulling && currentPull >= PULL_THRESHOLD) {
        doRefreshRef.current()
      }
      setPullY(0)
      startY = 0
      pulling = false
      currentPull = 0
    }

    // --- Wheel / trackpad (desktop) ---
    let wheelPull = 0
    let wheelTimer = 0

    const onWheel = (e: WheelEvent) => {
      if (refreshingRef.current) return
      if (el.scrollTop > 0 || e.deltaY >= 0) {
        if (wheelPull > 0) {
          wheelPull = 0
          setPullY(0)
          window.clearTimeout(wheelTimer)
        }
        return
      }
      // At top, scrolling up (deltaY < 0)
      e.preventDefault()
      wheelPull = Math.min(wheelPull + Math.abs(e.deltaY) * 0.15, 100)
      setPullY(wheelPull)

      // Trigger immediately when threshold reached
      if (wheelPull >= PULL_THRESHOLD) {
        window.clearTimeout(wheelTimer)
        wheelPull = 0
        setPullY(0)
        doRefreshRef.current()
        return
      }

      // Didn't reach threshold — reset after user stops scrolling
      window.clearTimeout(wheelTimer)
      wheelTimer = window.setTimeout(() => {
        wheelPull = 0
        setPullY(0)
      }, 400)
    }

    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: false })
    el.addEventListener('touchend', onTouchEnd)
    el.addEventListener('wheel', onWheel, { passive: false })

    return () => {
      el.removeEventListener('touchstart', onTouchStart)
      el.removeEventListener('touchmove', onTouchMove)
      el.removeEventListener('touchend', onTouchEnd)
      el.removeEventListener('wheel', onWheel)
      window.clearTimeout(wheelTimer)
    }
  }, [])

  const toggleExpand = (id: number) => {
    setExpandedId(prev => prev === id ? null : id)
  }

  const handleFilterToggle = (dimension: keyof ActiveFilters, value: string | number | null) => {
    const newFilters = { ...activeFilters }
    const current = activeFilters[dimension]
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(newFilters as any)[dimension] = current === value ? null : value
    setActiveFilters(newFilters)
    setItems([])
    setPage(1)
    setHasMore(false)
    fetchFeed(1, false, newFilters)
  }

  const handleSiteClick = async (siteId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (loadingSiteId) return
    setLoadingSiteId(siteId)
    const resp = await fetch(`${config.api.baseUrl}/sites/${siteId}`)
    if (resp.ok) {
      const detail = await resp.json()
      setSelectedSite(apiDetailToSiteData(detail))
    }
    setLoadingSiteId(null)
  }

  const activeFilterCount = Object.values(activeFilters).filter(Boolean).length

  return (
    <div className="news-page" ref={pageRef}>
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
          <span className="news-page-lyra-name" style={{ cursor: 'pointer' }} onClick={() => setShowLyraProfile(true)}>News Feed</span>
          {stats && (
            <div className="news-page-stats">
              <span className="news-page-stats-item"><strong>{stats.total_videos}</strong> videos processed</span>
              <span className="news-page-stats-sep">→</span>
              <span className="news-page-stats-item"><strong>{stats.total_items}</strong> stories</span>
              <span className="news-page-stats-sep">·</span>
              <span className="news-page-stats-item"><strong>{stats.total_channels}</strong> channels</span>
            </div>
          )}
        </div>
        <div className={`news-page-live${online ? '' : ' offline'}`}>
          <span className="news-page-live-dot" />
          <span className="news-page-live-text">{online ? 'LIVE' : 'OFFLINE'}</span>
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

              {/* Significance threshold row */}
              <div className="news-page-filter-row">
                <span className="news-page-filter-label">Significance</span>
                <div className="news-page-chips">
                  {([
                    { label: 'All', value: null },
                    { label: 'Notable 5+', value: 5 },
                    { label: 'Significant 7+', value: 7 },
                    { label: 'Breaking 9+', value: 9 },
                  ] as const).map(opt => (
                    <button
                      key={opt.label}
                      className={`news-page-chip${activeFilters.min_significance === opt.value ? ' active' : ''}`}
                      onClick={() => handleFilterToggle('min_significance', opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Sort order row */}
              <div className="news-page-filter-row">
                <span className="news-page-filter-label">Sort</span>
                <div className="news-page-chips">
                  {([
                    { label: 'Latest', value: null },
                    { label: 'Top Rated', value: 'significance' },
                  ] as const).map(opt => (
                    <button
                      key={opt.label}
                      className={`news-page-chip${activeFilters.sort === opt.value ? ' active' : ''}`}
                      onClick={() => handleFilterToggle('sort', opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* News category row */}
              {filters.news_categories.length > 0 && (
                <div className="news-page-filter-row">
                  <span className="news-page-filter-label">Topic</span>
                  <div className="news-page-chips news-page-chips-scroll">
                    {filters.news_categories.map(cat => (
                      <button
                        key={cat}
                        className={`news-page-chip${activeFilters.news_category === cat ? ' active' : ''}`}
                        onClick={() => handleFilterToggle('news_category', cat)}
                      >
                        {getNewsCategoryLabel(cat)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Pull-to-refresh zone */}
      <div
        className="news-page-pull-zone"
        style={{ height: pullPhase !== 'idle' ? 52 : pullY > 0 ? Math.min(pullY * 0.7, 52) : 0 }}
      >
        {pullPhase === 'done' ? (
          <div key="done" className="news-page-pull-spinner done">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <span className="news-page-pull-text">Updated</span>
          </div>
        ) : pullPhase === 'refreshing' ? (
          <div key="refreshing" className="news-page-pull-spinner spinning">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            <span className="news-page-pull-text">Refreshing</span>
          </div>
        ) : (
          <div key="pull" className={`news-page-pull-spinner${pullY >= PULL_THRESHOLD ? ' ready' : ''}`}>
            <svg
              width="18" height="18" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
              style={{ transform: `rotate(${Math.min(pullY / PULL_THRESHOLD, 1) * 540}deg)` }}
            >
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            <span className="news-page-pull-text">
              {pullY >= PULL_THRESHOLD ? 'Release' : 'Pull to refresh'}
            </span>
          </div>
        )}
      </div>

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
      <div className="news-page-grid" ref={gridRef}>
        {Array.from({ length: columnCount }, (_, colIdx) => (
          <div key={colIdx} className="news-page-column">
            {items.filter((_, i) => i % columnCount === colIdx).map(item => {
              const screenshotSrc = item.screenshot_url
                ? `${config.api.baseUrl}${item.screenshot_url.replace('/api', '')}`
                : item.video.thumbnail_url
              const deepLink = item.youtube_deep_url || item.youtube_url || '#'

              return (
              <div
                key={item.id}
                className={`news-page-card${expandedId === item.id ? ' expanded' : ''}${newItemIds.has(item.id) ? ' new-item' : ''}`}
                style={item.significance ? getSignificanceCardStyle(item.significance) : undefined}
                onClick={() => toggleExpand(item.id)}
                onAnimationEnd={() => setNewItemIds(prev => { const next = new Set(prev); next.delete(item.id); return next })}
              >
            <div className="news-page-card-body">
              {item.news_category && item.news_category !== 'general' && (
                <span className="news-category-badge">{getNewsCategoryLabel(item.news_category)}</span>
              )}
              <div className="news-card-meta">
                <span className="news-card-channel">{item.video.channel_name}</span>
                <span>{formatRelativeDate(item.video.published_at)}</span>
              </div>
              {item.significance != null && (
                <div className="news-significance-stamp" style={{ color: getSignificanceColor(item.significance) }}>
                  {getSignificanceLabel(item.significance)}
                </div>
              )}
              <div className="news-card-post-text">{item.post_text || item.headline}</div>

              {item.site_id && (
                  <div className="news-feed-site-block">
                    <div className="news-feed-site-row">
                      {item.site_country && <CountryFlag country={item.site_country} size="sm" showName />}
                      <button
                        className="news-page-card-site-name"
                        onClick={(e) => handleSiteClick(item.site_id!, e)}
                        disabled={loadingSiteId === item.site_id}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                          <circle cx="12" cy="10" r="3"></circle>
                        </svg>
                        {loadingSiteId === item.site_id ? 'Loading...' : (item.site_name || item.site_name_extracted)}
                      </button>
                    </div>
                    <SiteBadges category={item.site_type} period={item.site_period_name} periodStart={item.site_period_start} size="sm" />
                  </div>
              )}

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
                  className="news-card-thumb"
                  href={deepLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                >
                  <LazyImage src={screenshotSrc} alt="" />
                  <svg className="news-card-play" width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                  </svg>
                  {item.video.duration_minutes != null && (
                    <span className="news-card-duration">
                      {formatDuration(item.video.duration_minutes)}
                    </span>
                  )}
                  {item.timestamp_seconds != null && (
                    <span className="news-card-timestamp">
                      ▶ {formatDuration(item.timestamp_seconds / 60)}
                    </span>
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
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
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
          </div>
              )
            })}
          </div>
        ))}
      </div>

      {/* Loading / infinite scroll sentinel */}
      {loading && pullPhase !== 'refreshing' && (
        <div className="news-page-loading">Loading...</div>
      )}
      <div ref={sentinelRef} style={{ height: 1 }} />

      {showLyraProfile && (
        <Suspense fallback={null}>
          <LyraProfileModal onClose={() => setShowLyraProfile(false)} />
        </Suspense>
      )}

      {selectedSite && (
        <SitePopupOverlay site={selectedSite} onClose={() => setSelectedSite(null)} />
      )}
    </div>
  )
}
