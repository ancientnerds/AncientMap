/**
 * LyraDiscoveriesPage - Dedicated page showing sites discovered by Lyra.
 * Accessed via /lyra-discoveries.html (separate Vite entry point).
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { getCategoryColor } from '../data/sites'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'

const LyraProfileModal = lazy(() => import('../components/LyraProfileModal'))

interface DiscoveryItem {
  id: string
  name: string
  description: string | null
  country: string | null
  site_type: string | null
  source_url: string | null
  mention_count: number
  created_at: string | null
}

interface DiscoveryResponse {
  items: DiscoveryItem[]
  total_count: number
  page: number
  page_size: number
  has_more: boolean
}

interface LyraStats {
  total_discoveries: number
  total_sites_known: number
  total_name_variants: number
}

export default function LyraDiscoveriesPage() {
  const [items, setItems] = useState<DiscoveryItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const [stats, setStats] = useState<LyraStats | null>(null)
  const [minMentions, setMinMentions] = useState(1)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const [columnCount, setColumnCount] = useState(3)

  useEffect(() => {
    const el = gridRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      const w = entry.contentRect.width
      const cols = Math.max(1, Math.floor(w / 320))
      setColumnCount(cols)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const fetchDiscoveries = useCallback(async (pageNum: number, append: boolean = false, mentions: number = minMentions) => {
    try {
      setLoading(true)
      setError(null)
      const url = `${config.api.baseUrl}/contributions/lyra/list?page=${pageNum}&page_size=24&min_mentions=${mentions}`
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: DiscoveryResponse = await resp.json()
      setItems(prev => append ? [...prev, ...data.items] : data.items)
      setTotalCount(data.total_count)
      setHasMore(data.has_more)
      setPage(pageNum)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [minMentions])

  // Initial load
  useEffect(() => {
    fetchDiscoveries(1)
  }, [fetchDiscoveries])

  // Fetch stats
  useEffect(() => {
    fetch(`${config.api.baseUrl}/contributions/lyra/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStats(d) })
      .catch(() => {})
  }, [])

  // Infinite scroll
  useEffect(() => {
    if (!sentinelRef.current || !hasMore || loading) return
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          fetchDiscoveries(page + 1, true, minMentions)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchDiscoveries, minMentions])

  const handleMinMentionsChange = (value: number) => {
    setMinMentions(value)
    setItems([])
    setPage(1)
    setHasMore(false)
    fetchDiscoveries(1, false, value)
  }

  // Extract YouTube video ID from URL
  const getYouTubeId = (url: string | null): string | null => {
    if (!url) return null
    const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&?/]+)/)
    return match ? match[1] : null
  }

  return (
    <div className="lyra-discoveries-page">
      {/* Header */}
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
          <span className="news-page-lyra-name" style={{ cursor: 'pointer' }} onClick={() => setShowLyraProfile(true)}>Lyra's Discoveries</span>
          {stats && (
            <div className="news-page-stats">
              <span className="news-page-stats-item"><strong>{totalCount}</strong> sites discovered</span>
              <span className="news-page-stats-sep">from</span>
              <span className="news-page-stats-item"><strong>{stats.total_sites_known.toLocaleString()}</strong> known sites</span>
            </div>
          )}
        </div>
      </header>

      {/* Filter bar */}
      <div className="lyra-discoveries-filters">
        <span className="lyra-discoveries-filter-label">Minimum mentions:</span>
        <div className="lyra-discoveries-filter-chips">
          {[1, 2, 3, 5, 10].map(n => (
            <button
              key={n}
              className={`news-page-chip${minMentions === n ? ' active' : ''}`}
              onClick={() => handleMinMentionsChange(n)}
            >
              {n}+
            </button>
          ))}
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="news-page-error">
          {error}
          <button onClick={() => fetchDiscoveries(1)}>Retry</button>
        </div>
      )}

      {/* Empty state */}
      {!error && items.length === 0 && !loading && (
        <div className="news-page-empty">No discoveries yet. Lyra is still watching...</div>
      )}

      {/* Grid */}
      <div className="lyra-discoveries-grid" ref={gridRef}>
        {Array.from({ length: columnCount }, (_, colIdx) => (
          <div key={colIdx} className="lyra-discoveries-column">
            {items.filter((_, i) => i % columnCount === colIdx).map(item => {
              const flagUrl = item.country ? getCountryFlatFlagUrl(item.country) : null
              const categoryColor = item.site_type ? getCategoryColor(item.site_type) : null
              const youtubeId = getYouTubeId(item.source_url)

              return (
                <div key={item.id} className="lyra-discovery-card">
                  <div className="lyra-discovery-header">
                    <h3 className="lyra-discovery-name">{item.name}</h3>
                    {item.mention_count > 1 && (
                      <span className="lyra-discovery-mentions">
                        {item.mention_count}x
                      </span>
                    )}
                  </div>

                  {item.description && (
                    <p className="lyra-discovery-description">{item.description}</p>
                  )}

                  <div className="lyra-discovery-meta">
                    {flagUrl && (
                      <span className="lyra-discovery-country">
                        <img src={flagUrl} alt="" className="lyra-discovery-flag" />
                        {item.country}
                      </span>
                    )}
                    {categoryColor && (
                      <span className="lyra-discovery-badge" style={{ borderColor: categoryColor, color: categoryColor }}>
                        {item.site_type}
                      </span>
                    )}
                  </div>

                  {youtubeId && (
                    <a
                      className="lyra-discovery-youtube"
                      href={item.source_url!}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                      </svg>
                      Watch on YouTube
                    </a>
                  )}
                </div>
              )
            })}
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
