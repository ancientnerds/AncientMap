/**
 * LyraDiscoveriesPage - Full curation overview of all Lyra-extracted sites.
 * Accessed via /discoveries.html (separate Vite entry point).
 *
 * Shows every site Lyra extracts from YouTube videos that is NOT in the
 * manually-curated ancient_nerds source — matched, enriched, and pending.
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
  id: string
  display_name: string
  enrichment_status: string
  enrichment_score: number
  matched_site_id: string | null
  matched_site_name: string | null
  matched_source: string | null
  country: string | null
  site_type: string | null
  period_name: string | null
  thumbnail_url: string | null
  wikipedia_url: string | null
  mention_count: number
  facts: string[]
  videos: VideoReference[]
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
  matched_count: number
  enriched_count: number
  pending_count: number
  total_sites_known: number
}

type StatusFilter = 'all' | 'matched' | 'enriched' | 'pending'

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
    case 'matched':
      label = 'Matched'
      cls = 'lyra-status-matched'
      break
    case 'enriched':
    case 'promoted':
      label = 'Enriched'
      cls = 'lyra-status-enriched'
      break
    default:
      label = 'Processing'
      cls = 'lyra-status-pending'
  }
  return <span className={`lyra-status-pill ${cls}`}>{label}</span>
}

function DiscoveryCard({ item }: { item: AggregatedDiscovery }) {
  const [factsExpanded, setFactsExpanded] = useState(false)
  const VISIBLE_FACTS = 2

  const visibleFacts = factsExpanded ? item.facts : item.facts.slice(0, VISIBLE_FACTS)
  const hiddenCount = item.facts.length - VISIBLE_FACTS

  // Hero: matched site with thumbnail, or enrichment thumbnail, or best_match fallback
  const showMatchedHero = item.matched_site_id && item.thumbnail_url
  const showBestMatchHero = !item.matched_site_id && item.best_match?.thumbnail_url

  return (
    <div className="lyra-discovery-card">
      {/* Hero: matched site */}
      {showMatchedHero && (
        <div className="lyra-discovery-hero">
          <img
            src={item.thumbnail_url!}
            alt=""
            className="lyra-hero-thumb"
            loading="lazy"
          />
          <div className="lyra-hero-info">
            <span className="lyra-hero-label">Matched site:</span>
            <a
              href={`/?site=${item.matched_site_id}`}
              className="lyra-hero-name"
              target="_blank"
              rel="noopener noreferrer"
            >
              {item.matched_site_name || item.display_name}
            </a>
            {item.matched_source && (
              <span className="lyra-hero-source">via {item.matched_source}</span>
            )}
          </div>
        </div>
      )}

      {/* Hero: enrichment thumbnail (no matched site) */}
      {!showMatchedHero && !showBestMatchHero && item.thumbnail_url && !item.matched_site_id && (
        <div className="lyra-discovery-hero">
          <img
            src={item.thumbnail_url}
            alt=""
            className="lyra-hero-thumb"
            loading="lazy"
          />
        </div>
      )}

      {/* Hero: best_match fallback for pending items */}
      {showBestMatchHero && (
        <div className="lyra-discovery-hero">
          <img
            src={item.best_match!.thumbnail_url!}
            alt=""
            className="lyra-hero-thumb"
            loading="lazy"
          />
          <div className="lyra-hero-info">
            <span className="lyra-hero-label">Possible match:</span>
            <a
              href={`/?site=${item.best_match!.site_id}`}
              className="lyra-hero-name"
              target="_blank"
              rel="noopener noreferrer"
            >
              {item.best_match!.name}
            </a>
            {item.best_match!.wikipedia_url && (
              <a
                href={item.best_match!.wikipedia_url}
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

      {/* Header with name, score, status pill, and mentions */}
      <div className="lyra-discovery-header">
        <h3 className="lyra-discovery-name">{item.display_name}</h3>
        <div className="lyra-discovery-header-badges">
          <StatusPill status={item.enrichment_status} />
          <span className="lyra-discovery-score" title="Enrichment score">
            {item.enrichment_score}
          </span>
          {item.mention_count > 1 && (
            <span className="lyra-discovery-mentions">
              {item.mention_count}x
            </span>
          )}
        </div>
      </div>

      {/* Metadata row: country, site type, period */}
      {(item.country || item.site_type || item.period_name) && (
        <div className="lyra-metadata-row">
          {item.country && (
            <span className="lyra-metadata-chip">
              {(() => {
                const flagUrl = getCountryFlatFlagUrl(item.country)
                return flagUrl ? (
                  <img src={flagUrl} alt="" className="lyra-discovery-flag" />
                ) : null
              })()}
              {item.country}
            </span>
          )}
          {item.site_type && (
            <span className="lyra-metadata-chip">{item.site_type}</span>
          )}
          {item.period_name && (
            <span className="lyra-metadata-chip">{item.period_name}</span>
          )}
        </div>
      )}

      {/* Wikipedia link */}
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

      {/* Suggestions (only for items without a matched site) */}
      {!item.matched_site_id && !item.best_match && item.suggestions.length > 0 && (
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
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showLyraProfile, setShowLyraProfile] = useState(false)
  const [stats, setStats] = useState<LyraStats | null>(null)
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

  const fetchDiscoveries = useCallback(async (
    pageNum: number,
    append: boolean = false,
    mentions: number = minMentions,
    sort: string = sortBy,
    statusParam: string = statusFilter
  ) => {
    try {
      setLoading(true)
      setError(null)
      const url = `${config.api.baseUrl}/discoveries/list?page=${pageNum}&page_size=24&min_mentions=${mentions}&sort_by=${sort}&status=${statusParam}`
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: DiscoveryResponse = await resp.json()
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
    fetchDiscoveries(1, false, minMentions, sortBy, statusFilter)
  }, [minMentions, sortBy, statusFilter])

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
          fetchDiscoveries(page + 1, true, minMentions, sortBy, statusFilter)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchDiscoveries, minMentions, sortBy, statusFilter])

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
          <span className="news-page-lyra-name" style={{ cursor: 'pointer' }} onClick={() => setShowLyraProfile(true)}>Discoveries</span>
          {stats && (
            <div className="news-page-stats">
              <span className="news-page-stats-item"><strong>{stats.matched_count}</strong> matched</span>
              <span className="news-page-stats-sep">·</span>
              <span className="news-page-stats-item"><strong>{stats.enriched_count}</strong> enriched</span>
              <span className="news-page-stats-sep">·</span>
              <span className="news-page-stats-item"><strong>{stats.pending_count}</strong> pending</span>
              <span className="news-page-stats-sep">·</span>
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
            {([['all', 'All'], ['matched', 'Matched'], ['enriched', 'Enriched'], ['pending', 'Pending']] as const).map(([val, label]) => (
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
              <DiscoveryCard key={item.id} item={item} />
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
