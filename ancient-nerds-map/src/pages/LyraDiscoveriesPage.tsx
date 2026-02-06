/**
 * LyraDiscoveriesPage - Sophisticated curation page showing sites discovered by Lyra.
 * Accessed via /discoveries.html (separate Vite entry point).
 *
 * Features:
 * - Deduplicated discoveries (grouped by normalized name)
 * - All facts from all mentions (expandable)
 * - Multiple video links with timestamps
 * - Importance scoring
 * - Fuzzy match suggestions to known sites
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'

const LyraProfileModal = lazy(() => import('../components/LyraProfileModal'))

interface VideoReference {
  video_id: string
  channel_name: string
  timestamp_seconds: number
  deep_url: string
}

interface SuggestionMatch {
  site_id: string
  name: string
  similarity: number
  thumbnail_url: string | null
  wikipedia_url: string | null
  country: string | null
}

interface AggregatedDiscovery {
  name_normalized: string
  display_name: string
  facts: string[]
  videos: VideoReference[]
  score: number
  mention_count: number
  unique_videos: number
  unique_channels: number
  last_mentioned: string | null
  suggestions: SuggestionMatch[]
  best_match: SuggestionMatch | null
}

interface DiscoveryResponse {
  items: AggregatedDiscovery[]
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

function formatTimestamp(seconds: number): string {
  if (!seconds || seconds <= 0) return ''
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function DiscoveryCard({ item }: { item: AggregatedDiscovery }) {
  const [factsExpanded, setFactsExpanded] = useState(false)
  const VISIBLE_FACTS = 2

  const visibleFacts = factsExpanded ? item.facts : item.facts.slice(0, VISIBLE_FACTS)
  const hiddenCount = item.facts.length - VISIBLE_FACTS
  const scorePercent = Math.round(item.score * 100)

  return (
    <div className="lyra-discovery-card">
      {/* Hero image for high-confidence matches */}
      {item.best_match && item.best_match.thumbnail_url && (
        <div className="lyra-discovery-hero">
          <img
            src={item.best_match.thumbnail_url}
            alt=""
            className="lyra-hero-thumb"
            loading="lazy"
          />
          <div className="lyra-hero-info">
            <span className="lyra-hero-label">Possible match:</span>
            <a
              href={`/?site=${item.best_match.site_id}`}
              className="lyra-hero-name"
              target="_blank"
              rel="noopener noreferrer"
            >
              {item.best_match.name}
            </a>
            {item.best_match.wikipedia_url && (
              <a
                href={item.best_match.wikipedia_url}
                target="_blank"
                rel="noopener noreferrer"
                className="lyra-hero-wiki"
              >
                Wikipedia
              </a>
            )}
          </div>
        </div>
      )}

      {/* Header with name, score, and mentions */}
      <div className="lyra-discovery-header">
        <h3 className="lyra-discovery-name">{item.display_name}</h3>
        <div className="lyra-discovery-header-badges">
          <span className="lyra-discovery-score" title="Importance score">
            {scorePercent}
          </span>
          {item.mention_count > 1 && (
            <span className="lyra-discovery-mentions">
              {item.mention_count}x
            </span>
          )}
        </div>
      </div>

      {/* Facts list */}
      {item.facts.length > 0 && (
        <div className="lyra-discovery-facts">
          {visibleFacts.map((fact, i) => (
            <div key={i} className="lyra-discovery-fact">{fact}</div>
          ))}
          {!factsExpanded && hiddenCount > 0 && (
            <button
              className="lyra-discovery-expand"
              onClick={() => setFactsExpanded(true)}
            >
              Show {hiddenCount} more
            </button>
          )}
          {factsExpanded && item.facts.length > VISIBLE_FACTS && (
            <button
              className="lyra-discovery-expand"
              onClick={() => setFactsExpanded(false)}
            >
              Show less
            </button>
          )}
        </div>
      )}

      {/* Video links */}
      {item.videos.length > 0 && (
        <div className="lyra-discovery-videos">
          {item.videos.map((v) => (
            <a
              key={v.video_id}
              href={v.deep_url}
              target="_blank"
              rel="noopener noreferrer"
              className="lyra-discovery-video-chip"
              title={v.channel_name}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
              </svg>
              <span className="lyra-video-channel">{v.channel_name}</span>
              {v.timestamp_seconds > 0 && (
                <span className="lyra-video-timestamp">{formatTimestamp(v.timestamp_seconds)}</span>
              )}
            </a>
          ))}
        </div>
      )}

      {/* Suggestions (only show if no best_match already displayed) */}
      {!item.best_match && item.suggestions.length > 0 && (
        <div className="lyra-discovery-suggestions">
          <span className="lyra-suggestions-label">Similar sites:</span>
          {item.suggestions.slice(0, 3).map((s) => (
            <a
              key={s.site_id}
              href={`/?site=${s.site_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="lyra-suggestion-chip"
              title={`${Math.round(s.similarity * 100)}% match`}
            >
              {s.name}
              {s.country && (
                <img
                  src={getCountryFlatFlagUrl(s.country) || ''}
                  alt=""
                  className="lyra-suggestion-flag"
                />
              )}
            </a>
          ))}
        </div>
      )}

      {/* Stats row */}
      <div className="lyra-discovery-stats">
        <span>{item.unique_videos} video{item.unique_videos !== 1 ? 's' : ''}</span>
        <span className="lyra-stats-sep">·</span>
        <span>{item.unique_channels} channel{item.unique_channels !== 1 ? 's' : ''}</span>
      </div>
    </div>
  )
}

export default function LyraDiscoveriesPage() {
  const [items, setItems] = useState<AggregatedDiscovery[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const [stats, setStats] = useState<LyraStats | null>(null)
  const [minMentions, setMinMentions] = useState(1)
  const [sortBy, setSortBy] = useState<'score' | 'mentions' | 'recency'>('score')
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

  const fetchDiscoveries = useCallback(async (
    pageNum: number,
    append: boolean = false,
    mentions: number = minMentions,
    sort: string = sortBy
  ) => {
    try {
      setLoading(true)
      setError(null)
      const url = `${config.api.baseUrl}/discoveries/list?page=${pageNum}&page_size=24&min_mentions=${mentions}&sort_by=${sort}`
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
  }, [minMentions, sortBy])

  // Initial load
  useEffect(() => {
    fetchDiscoveries(1, false, minMentions, sortBy)
  }, [minMentions, sortBy])

  // Fetch stats
  useEffect(() => {
    fetch(`${config.api.baseUrl}/discoveries/stats`)
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
          fetchDiscoveries(page + 1, true, minMentions, sortBy)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchDiscoveries, minMentions, sortBy])

  const handleMinMentionsChange = (value: number) => {
    setMinMentions(value)
    setItems([])
    setPage(1)
    setHasMore(false)
  }

  const handleSortChange = (value: 'score' | 'mentions' | 'recency') => {
    setSortBy(value)
    setItems([])
    setPage(1)
    setHasMore(false)
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
              <span className="news-page-stats-item"><strong>{totalCount}</strong> new sites found</span>
              <span className="news-page-stats-sep">·</span>
              <span className="news-page-stats-item">not yet in <strong>{stats.total_sites_known.toLocaleString()}</strong> site database</span>
            </div>
          )}
        </div>
      </header>

      {/* Filter bar */}
      <div className="lyra-discoveries-filters">
        <div className="lyra-filter-group">
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
        <div className="lyra-filter-group">
          <span className="lyra-discoveries-filter-label">Sort by:</span>
          <div className="lyra-discoveries-filter-chips">
            <button
              className={`news-page-chip${sortBy === 'score' ? ' active' : ''}`}
              onClick={() => handleSortChange('score')}
            >
              Score
            </button>
            <button
              className={`news-page-chip${sortBy === 'mentions' ? ' active' : ''}`}
              onClick={() => handleSortChange('mentions')}
            >
              Mentions
            </button>
            <button
              className={`news-page-chip${sortBy === 'recency' ? ' active' : ''}`}
              onClick={() => handleSortChange('recency')}
            >
              Recent
            </button>
          </div>
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
            {items.filter((_, i) => i % columnCount === colIdx).map(item => (
              <DiscoveryCard key={item.name_normalized} item={item} />
            ))}
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
