/**
 * LyraRadarPage - Sites Lyra found in YouTube videos that aren't in our DB yet.
 * Accessed via /radar.html (separate Vite entry point).
 *
 * Shows candidates for addition: enriched, pending, added (promoted),
 * and rejected items. Matched items are excluded (already in DB).
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

interface RadarItem {
  id: string
  display_name: string
  original_name: string | null
  enrichment_status: string
  enrichment_score: number
  rejection_reason: string | null
  country: string | null
  site_type: string | null
  period_name: string | null
  thumbnail_url: string | null
  wikipedia_url: string | null
  lat: number | null
  lon: number | null
  description: string | null
  wikidata_id: string | null
  mention_count: number
  facts: string[]
  videos: VideoReference[]
  unique_videos: number
  unique_channels: number
  last_mentioned: string | null
  suggestions: SuggestionMatch[]
  best_match: SuggestionMatch | null
}

interface RadarResponse {
  items: RadarItem[]
  total_count: number
  page: number
  page_size: number
  has_more: boolean
}

interface RadarStats {
  total_radar: number
  enriched_count: number
  pending_count: number
  added_count: number
  total_sites_known: number
}

type StatusFilter = 'all' | 'enriched' | 'pending' | 'added' | 'rejected'

function formatTimestamp(seconds: number): string {
  if (!seconds || seconds <= 0) return ''
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function StatusPill({ status }: { status: string }) {
  let label: string
  let cls: string
  switch (status) {
    case 'promoted':
      label = 'Added'
      cls = 'lyra-status-added'
      break
    case 'enriched':
      label = 'Enriched'
      cls = 'lyra-status-enriched'
      break
    case 'rejected':
      label = 'Rejected'
      cls = 'lyra-status-rejected'
      break
    default:
      label = 'Processing'
      cls = 'lyra-status-pending'
  }
  return <span className={`lyra-status-pill ${cls}`}>{label}</span>
}

const SCORE_WEIGHTS = [
  { key: 'name', label: 'Name', points: 25, check: () => true },
  { key: 'coords', label: 'Coords', points: 20, check: (d: RadarItem) => d.lat != null && d.lon != null },
  { key: 'country', label: 'Country', points: 10, check: (d: RadarItem) => !!d.country },
  { key: 'category', label: 'Category', points: 10, check: (d: RadarItem) => !!d.site_type },
  { key: 'period', label: 'Period', points: 10, check: (d: RadarItem) => !!d.period_name },
  { key: 'desc', label: 'Desc', points: 10, check: (d: RadarItem) => !!d.description && d.description.length >= 50 },
  { key: 'wiki', label: 'Wiki URL', points: 5, check: (d: RadarItem) => !!d.wikipedia_url },
  { key: 'thumb', label: 'Thumb', points: 5, check: (d: RadarItem) => !!d.thumbnail_url },
  { key: 'wikidata', label: 'Wikidata', points: 5, check: (d: RadarItem) => !!d.wikidata_id },
] as const

function formatCoord(value: number, pos: string, neg: string): string {
  const dir = value >= 0 ? pos : neg
  return `${Math.abs(value).toFixed(4)}\u00B0 ${dir}`
}

function scoreColor(pct: number): string {
  // 0% = red (hsl 0), 100% = green (hsl 120)
  const hue = Math.round((pct / 100) * 120)
  return `hsl(${hue}, 72%, 55%)`
}

function ScoreBreakdown({ item }: { item: RadarItem }) {
  let earned = 0
  for (const w of SCORE_WEIGHTS) {
    if (w.check(item)) earned += w.points
  }
  const pct = Math.round((earned / 100) * 100)

  return (
    <div className="lyra-score-section">
      <div className="lyra-score-header">
        <span className="lyra-discovery-percentage" style={{ color: scoreColor(pct) }}>{pct}%</span>
        <span className="lyra-score-sublabel">enrichment score</span>
      </div>
      <div className="lyra-score-breakdown">
        {SCORE_WEIGHTS.map(w => {
          const filled = w.check(item)
          return (
            <div key={w.key} className={`lyra-score-bar ${filled ? 'lyra-score-bar-filled' : ''}`}>
              <span className="lyra-score-label">{w.label}</span>
              <span className="lyra-score-points">{w.points}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function RadarCard({ item }: { item: RadarItem }) {
  const [factsExpanded, setFactsExpanded] = useState(false)
  const [videosExpanded, setVideosExpanded] = useState(false)
  const [descExpanded, setDescExpanded] = useState(false)

  return (
    <div className="lyra-discovery-card">
      {/* 1. Name + status/mentions header */}
      <div className="lyra-discovery-header">
        <div className="lyra-discovery-name-block">
          <h3 className="lyra-discovery-name">
            {item.display_name}
          </h3>
          {item.original_name && (
            <span className="lyra-discovery-original-name">
              Corrected from "{item.original_name}"
            </span>
          )}
        </div>
        <div className="lyra-discovery-header-badges">
          <StatusPill status={item.enrichment_status} />
          {item.mention_count > 1 && (
            <span className="lyra-discovery-mentions">
              {item.mention_count}x
            </span>
          )}
        </div>
      </div>

      {/* Rejection reason */}
      {item.rejection_reason && (
        <div className="lyra-discovery-rejection">
          {item.rejection_reason}
        </div>
      )}

      {/* 2. Country with flag */}
      {item.country && (
        <div className="lyra-discovery-country-row">
          {(() => {
            const flagUrl = getCountryFlatFlagUrl(item.country)
            return flagUrl ? (
              <img src={flagUrl} alt="" className="lyra-discovery-flag" />
            ) : null
          })()}
          <span>{item.country}</span>
        </div>
      )}

      {/* 4. Coordinates */}
      {item.lat != null && item.lon != null && (
        <div className="lyra-discovery-coords">
          {formatCoord(item.lat, 'N', 'S')}, {formatCoord(item.lon, 'E', 'W')}
        </div>
      )}

      {/* 5. Description */}
      {item.description && (
        <div className="lyra-discovery-description-section">
          <p className={`lyra-discovery-description ${!descExpanded ? 'lyra-description-clamped' : ''}`}>
            {item.description}
          </p>
          {item.description.length > 180 && (
            <button
              className="lyra-discovery-expand"
              onClick={() => setDescExpanded(!descExpanded)}
            >
              {descExpanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}

      {/* 6. Wikipedia link */}
      {item.wikipedia_url && (
        <a
          href={item.wikipedia_url}
          target="_blank"
          rel="noopener noreferrer"
          className="lyra-wiki-link"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12.09 13.119c-.936 1.932-2.217 4.548-2.853 5.728-.616 1.074-1.127.931-1.532.029-1.406-3.321-4.293-9.144-5.651-12.409-.251-.604-.96-1.467-1.554-1.467H.5c-.273 0-.5-.224-.5-.5s.227-.5.5-.5h3.662c.996 0 1.903.856 2.174 1.498 1.254 2.981 3.375 7.58 4.524 10.399.345-.655 1.159-2.271 1.824-3.633.305-.624.405-1.08.141-1.691-.684-1.575-1.883-4.082-2.561-5.567-.259-.565-.888-1.006-1.488-1.006H8.316c-.273 0-.5-.224-.5-.5s.227-.5.5-.5h3.266c.876 0 1.699.826 1.959 1.441.487 1.153 1.423 3.235 1.925 4.416.483-.883 1.248-2.366 1.733-3.347.279-.562.372-1.026.105-1.627-.509-1.146-.884-1.923-1.197-2.605a.567.567 0 0 1 .088-.555.54.54 0 0 1 .516-.186h3.273c.804 0 1.519.884 1.799 1.484.496 1.062 1.476 3.192 2.01 4.385l1.734-3.468c.232-.462.381-.998.111-1.58-.248-.536-.477-1.034-.677-1.467-.099-.215.018-.474.249-.548.231-.073.503.039.601.254.199.433.427.929.676 1.465.384.824.171 1.559-.121 2.142-.522 1.044-1.803 3.593-2.387 4.741-.191.375-.549.399-.747.022-.526-1.001-1.563-3.392-2.112-4.59-.453.862-1.271 2.479-1.715 3.377-.196.396-.561.419-.747.015-.568-1.239-1.536-3.482-2.047-4.619-.476.897-1.172 2.281-1.671 3.289z"/>
          </svg>
          Wikipedia
        </a>
      )}

      {/* 7. Thumbnail — full card width */}
      {item.thumbnail_url && (
        <div className="lyra-discovery-image-wrap">
          <img
            src={item.thumbnail_url}
            alt=""
            className="lyra-discovery-image"
            loading="lazy"
          />
        </div>
      )}

      {/* 8. Score breakdown */}
      <ScoreBreakdown item={item} />

      {/* 9. Facts — collapsed by default */}
      {item.facts.length > 0 && (
        <div className="lyra-collapsible">
          <button
            className="lyra-collapsible-header"
            onClick={() => setFactsExpanded(!factsExpanded)}
          >
            <span className="lyra-collapsible-arrow">{factsExpanded ? '\u25BE' : '\u25B8'}</span>
            Facts ({item.facts.length})
          </button>
          {factsExpanded && (
            <div className="lyra-discovery-facts">
              {item.facts.map((fact, i) => (
                <div key={i} className="lyra-discovery-fact">{fact}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 10. Videos — collapsed by default */}
      {item.videos.length > 0 && (
        <div className="lyra-collapsible">
          <button
            className="lyra-collapsible-header"
            onClick={() => setVideosExpanded(!videosExpanded)}
          >
            <span className="lyra-collapsible-arrow">{videosExpanded ? '\u25BE' : '\u25B8'}</span>
            Videos ({item.unique_videos} from {item.unique_channels} channel{item.unique_channels !== 1 ? 's' : ''})
          </button>
          {videosExpanded && (
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
        </div>
      )}

      {/* 11. Suggestions (only for pending items) */}
      {item.suggestions.length > 0 && (
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
    </div>
  )
}

export default function LyraRadarPage() {
  const [items, setItems] = useState<RadarItem[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const [stats, setStats] = useState<RadarStats | null>(null)
  const [minMentions, setMinMentions] = useState(1)
  const [sortBy, setSortBy] = useState<'score' | 'mentions' | 'recency'>('score')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const sentinelRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const [columnCount, setColumnCount] = useState(3)
  const [showScrollTop, setShowScrollTop] = useState(false)

  useEffect(() => {
    const onScroll = () => setShowScrollTop(window.scrollY > 400)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

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

  const fetchRadar = useCallback(async (
    pageNum: number,
    append: boolean = false,
    mentions: number = minMentions,
    sort: string = sortBy,
    statusParam: string = statusFilter
  ) => {
    try {
      setLoading(true)
      setError(null)
      const url = `${config.api.baseUrl}/radar/list?page=${pageNum}&page_size=24&min_mentions=${mentions}&sort_by=${sort}&status=${statusParam}`
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: RadarResponse = await resp.json()
      setItems(prev => append ? [...prev, ...data.items] : data.items)
      setHasMore(data.has_more)
      setPage(pageNum)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [minMentions, sortBy, statusFilter])

  // Initial load & filter changes
  useEffect(() => {
    fetchRadar(1, false, minMentions, sortBy, statusFilter)
  }, [minMentions, sortBy, statusFilter])

  // Fetch stats
  useEffect(() => {
    fetch(`${config.api.baseUrl}/radar/stats`)
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
          fetchRadar(page + 1, true, minMentions, sortBy, statusFilter)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchRadar, minMentions, sortBy, statusFilter])

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

  const handleStatusChange = (value: StatusFilter) => {
    setStatusFilter(value)
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
          <span className="news-page-lyra-name" style={{ cursor: 'pointer' }} onClick={() => setShowLyraProfile(true)}>Radar</span>
          {stats && (
            <div className="news-page-stats">
              <span className="news-page-stats-item"><strong>{stats.enriched_count}</strong> enriched</span>
              <span className="news-page-stats-sep">&middot;</span>
              <span className="news-page-stats-item"><strong>{stats.pending_count}</strong> pending</span>
              <span className="news-page-stats-sep">&middot;</span>
              <span className="news-page-stats-item"><strong>{stats.added_count}</strong> added</span>
              <span className="news-page-stats-sep">&middot;</span>
              <span className="news-page-stats-item"><strong>{stats.total_sites_known.toLocaleString()}</strong> known sites</span>
            </div>
          )}
        </div>
      </header>

      {/* Filter bar */}
      <div className="lyra-discoveries-filters">
        <div className="lyra-filter-group">
          <span className="lyra-discoveries-filter-label">Status:</span>
          <div className="lyra-discoveries-filter-chips">
            {([['all', 'All'], ['enriched', 'Enriched'], ['pending', 'Pending'], ['added', 'Added'], ['rejected', 'Rejected']] as const).map(([val, label]) => (
              <button
                key={val}
                className={`news-page-chip${statusFilter === val ? ' active' : ''}`}
                onClick={() => handleStatusChange(val)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="lyra-filter-group">
          <span className="lyra-discoveries-filter-label">Min. mentions:</span>
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
          <button onClick={() => fetchRadar(1)}>Retry</button>
        </div>
      )}

      {/* Empty state */}
      {!error && items.length === 0 && !loading && (
        <div className="news-page-empty">No radar items yet. Lyra is still watching...</div>
      )}

      {/* Grid */}
      <div className="lyra-discoveries-grid" ref={gridRef}>
        {Array.from({ length: columnCount }, (_, colIdx) => (
          <div key={colIdx} className="lyra-discoveries-column">
            {items.filter((_, i) => i % columnCount === colIdx).map(item => (
              <RadarCard key={item.id} item={item} />
            ))}
          </div>
        ))}
      </div>

      {/* Loading / infinite scroll sentinel */}
      {loading && (
        <div className="news-page-loading">Loading...</div>
      )}
      <div ref={sentinelRef} style={{ height: 1 }} />

      {/* Scroll to top button */}
      {showScrollTop && (
        <button
          className="lyra-scroll-top"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          aria-label="Scroll to top"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      )}

      {showLyraProfile && (
        <Suspense fallback={null}>
          <LyraProfileModal onClose={() => setShowLyraProfile(false)} />
        </Suspense>
      )}
    </div>
  )
}
