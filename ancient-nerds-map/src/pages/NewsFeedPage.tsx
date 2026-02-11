/**
 * NewsFeedPage - Dedicated full-page news feed with grid layout.
 * Accessed via /news.html (separate Vite entry point).
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { getCategoryColor, getPeriodColor } from '../data/sites'
import { DataStore } from '../data/DataStore'
import type { SiteData } from '../data/sites'
import type { NewsItemData, NewsStats, NewsFilters, ActiveFilters } from '../types/news'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { SitePopupOverlay } from '../components/SitePopupOverlay'
import NewsCard from '../components/news/NewsCard'
import { getNewsCategoryLabel, getSpeculativeTagLabel } from '../components/news/significance'
import '../components/news/news-cards.css'

const LyraProfileModal = lazy(() => import('../components/LyraProfileModal'))

export default function NewsFeedPage() {
  const [items, setItems] = useState<NewsItemData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [totalCount, setTotalCount] = useState(0)
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

  // Live updates
  const [online, setOnline] = useState(true)

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
    min_significance: null, news_category: null, speculative_tag: null, sort: null,
  })
  const [filtersExpanded, setFiltersExpanded] = useState(false)
  const [showSpeculative, setShowSpeculative] = useState(true)


  const PAGE_SIZE = 50

  const fetchPage = useCallback(async (pageNum: number, append: boolean) => {
    try {
      setLoading(true)
      setError(null)
      const params = new URLSearchParams()
      params.set('page', String(pageNum))
      params.set('page_size', String(PAGE_SIZE))
      params.set('include_speculative', String(showSpeculative))
      if (activeFilters.channel) params.set('channel_id', activeFilters.channel)
      if (activeFilters.site) params.set('site_id', activeFilters.site)
      if (activeFilters.category) params.set('category', activeFilters.category)
      if (activeFilters.period) params.set('period', activeFilters.period)
      if (activeFilters.country) params.set('country', activeFilters.country)
      if (activeFilters.min_significance != null) params.set('min_significance', String(activeFilters.min_significance))
      if (activeFilters.news_category) params.set('news_category', activeFilters.news_category)
      if (activeFilters.speculative_tag) params.set('speculative_tag', activeFilters.speculative_tag)
      if (activeFilters.sort) params.set('sort', activeFilters.sort)
      const resp = await fetch(`${config.api.baseUrl}/news/feed?${params}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: { items: NewsItemData[]; has_more: boolean; total_count: number; page: number } = await resp.json()
      setItems(prev => append ? [...prev, ...data.items] : data.items)
      setHasMore(data.has_more)
      setTotalCount(data.total_count)
      setPage(data.page)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [activeFilters, showSpeculative])

  const PULL_THRESHOLD = 70

  const doRefresh = useCallback(async () => {
    window.clearTimeout(doneTimer.current)
    setPullPhase('refreshing')
    refreshingRef.current = true
    const t0 = Date.now()
    await fetchPage(1, false)
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
  }, [fetchPage])

  const doRefreshRef = useRef(doRefresh)
  doRefreshRef.current = doRefresh

  // Fetch page 1 on mount and whenever filters/sort change
  useEffect(() => {
    fetchPage(1, false)
  }, [fetchPage])

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

  // Infinite scroll — fetch next page from server when sentinel enters viewport
  useEffect(() => {
    if (!sentinelRef.current || !hasMore || loading) return
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting) {
          fetchPage(page + 1, true)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchPage])

  // Pull-to-refresh: touch (mobile) + wheel/trackpad (desktop)
  useEffect(() => {
    const el = pageRef.current
    if (!el) return

    // --- Touch (mobile) ---
    let startY = 0
    let pulling = false
    let currentPull = 0

    const onTouchStart = (e: TouchEvent) => {
      // Don't start pull-to-refresh when touching inside scrollable filter body
      if ((e.target as HTMLElement).closest('.news-page-filters-body')) return
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


  const handleFilterToggle = (dimension: keyof ActiveFilters, value: string | number | null) => {
    setActiveFilters(prev => ({
      ...prev,
      [dimension]: prev[dimension] === value ? null : value,
    }))
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
        <div className={`news-page-live${online ? '' : ' offline'}`} title={online ? 'Lyra is online — monitoring YouTube archaeology channels and extracting discoveries' : 'Lyra is offline — pipeline not currently running'}>
          <span className="news-page-live-dot" />
          <span className="news-page-live-text">{online ? 'LIVE' : 'OFFLINE'}</span>
        </div>
      </header>

      {/* Multi-dimension filter section */}
      {filters && (
        <div className="news-page-filters">
          <div className="news-page-filters-bar">
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
            {!loading && totalCount > 0 && (
              <span className="news-page-result-count">{totalCount} result{totalCount !== 1 ? 's' : ''}</span>
            )}
            <div className="news-page-filters-bar-actions">
              <button
                className={`news-page-chip${activeFilters.sort == null ? ' active' : ''}`}
                onClick={() => handleFilterToggle('sort', null)}
              >
                Latest
              </button>
              <button
                className={`news-page-chip${activeFilters.sort === 'significance' ? ' active' : ''}`}
                onClick={() => handleFilterToggle('sort', 'significance')}
              >
                Top Rated
              </button>
              <button
                className={`news-page-chip${showSpeculative ? ' active' : ''}`}
                onClick={() => setShowSpeculative(prev => !prev)}
                title="Toggle speculative content — alternative theories not supported by mainstream archaeology"
              >
                Speculative
              </button>
            </div>
          </div>

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
                    { label: 'New Research 6+', value: 6 },
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

              {/* Speculative tags row — only visible when speculative toggle is on */}
              {showSpeculative && filters.speculative_tags && filters.speculative_tags.length > 0 && (
                <div className="news-page-filter-row">
                  <span className="news-page-filter-label">Speculative</span>
                  <div className="news-page-chips">
                    {filters.speculative_tags.map(tag => (
                      <button
                        key={tag}
                        className={`news-page-chip speculative-tag${activeFilters.speculative_tag === tag ? ' active' : ''}`}
                        onClick={() => handleFilterToggle('speculative_tag', tag)}
                      >
                        {getSpeculativeTagLabel(tag)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

            </div>
          )}
        </div>
      )}

      {/* AI disclosure */}
      <div className="news-page-ai-notice">
        Content is AI-generated from YouTube video content. Always verify with original sources.
      </div>

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
          <button onClick={() => fetchPage(1, false)}>Retry</button>
        </div>
      )}

      {/* Empty state */}
      {!error && !loading && items.length === 0 && (
        <div className="news-page-empty">
          {Object.values(activeFilters).some(Boolean) || !showSpeculative
            ? 'No items match the current filters.'
            : 'No news items yet. Check back soon.'}
        </div>
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
                <div key={item.id} className="news-page-card">
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
                      onSiteLoaded={setSelectedSite}
                    />
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
