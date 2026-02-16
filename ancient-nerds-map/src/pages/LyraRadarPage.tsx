/**
 * LyraRadarPage - Sites Lyra found in YouTube videos that aren't in our DB yet.
 * Accessed via /radar.html (separate Vite entry point).
 *
 * Shows candidates for addition: enriched, pending, added (promoted),
 * and rejected items. Matched items are excluded (already in DB).
 */

import { useState, useEffect, useCallback, useMemo, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { formatCoord, timeAgo } from '../utils/formatters'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { SiteBadges, CountryFlag, CopyButton } from '../components/metadata'
import { SOURCE_CONFIG } from '../constants/colors'
import { SitePopupOverlay } from '../components/SitePopupOverlay'
import LazyImage from '../components/LazyImage'
import type { SiteData } from '../data/sites'
import './LyraRadarPage.css'

const LyraProfileModal = lazy(() => import('../components/LyraProfileModal'))
const RadarMap = lazy(() => import('../components/RadarMap'))

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
  source_id?: string
  source_name?: string
}

interface ExternalSource {
  source_id: string
  site_id: string
  name: string
  source_url: string | null
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
  period_start: number | null
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
  external_sources: ExternalSource[]
  confidence: string | null
  data_sources: string[]
  commons_url: string | null
  nearby_an_site: { name: string; distance_km: number } | null
  source: string | null
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
type SourceFilter = 'all' | 'lyra' | 'user'

function formatTimestamp(seconds: number): string {
  if (!seconds || seconds <= 0) return ''
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function StatusPill({ status }: { status: string }) {
  let label: string
  let cls: string
  let hint: string
  switch (status) {
    case 'promoted':
      label = 'Added'
      cls = 'lyra-status-added'
      hint = 'Promoted to the main sites database'
      break
    case 'enriched':
      label = 'Enriched'
      cls = 'lyra-status-enriched'
      hint = 'Enriched with Wikipedia/Wikidata metadata'
      break
    case 'rejected':
      label = 'Rejected'
      cls = 'lyra-status-rejected'
      hint = 'Rejected — does not meet quality criteria'
      break
    default:
      label = 'Processing'
      cls = 'lyra-status-pending'
      hint = 'Waiting for enrichment'
  }
  return <span className={`lyra-status-pill ${cls}`} title={hint}>{label}</span>
}

function ConfidenceBadge({ level }: { level: string }) {
  let cls: string
  switch (level) {
    case 'high':
      cls = 'lyra-confidence-high'
      break
    case 'medium':
      cls = 'lyra-confidence-medium'
      break
    case 'low':
      cls = 'lyra-confidence-low'
      break
    default:
      return null
  }
  return <span className={`lyra-status-pill ${cls}`} title={`AI confidence: ${level}`}>{level}</span>
}

const DATA_SOURCE_LABELS: Record<string, { abbr: string; title: string }> = {
  wikidata: { abbr: 'W', title: 'Wikidata' },
  wikipedia: { abbr: 'WP', title: 'Wikipedia' },
  ai_research: { abbr: 'AI', title: 'AI Research' },
  db_match: { abbr: 'DB', title: 'Database Match' },
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
      <div className="lyra-score-header" title={`Data completeness: ${earned}/100 points. Higher scores mean more metadata (coordinates, period, category, description, images) was found for this site.`}>
        <span className="lyra-discovery-percentage" style={{ color: scoreColor(pct) }}>{pct}%</span>
        <span className="lyra-score-badges">
          <StatusPill status={item.enrichment_status} />
          {item.confidence && <ConfidenceBadge level={item.confidence} />}
          {item.mention_count > 1 && (
            <span className="lyra-discovery-mentions" title={`Mentioned in ${item.mention_count} news items`}>
              {item.mention_count}x
            </span>
          )}
        </span>
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
      <div className="lyra-score-sources">
        <span className="lyra-score-sources-label">Sources:</span>
        {item.data_sources.length > 0 ? (
          item.data_sources.map(src => {
            const info = DATA_SOURCE_LABELS[src]
            if (!info) return null
            return <span key={src} className="lyra-source-tag" title={info.title}>{info.abbr}</span>
          })
        ) : (
          <span className="lyra-source-empty">&mdash;</span>
        )}
      </div>
    </div>
  )
}

function radarItemToSiteData(item: RadarItem): SiteData {
  return {
    id: item.best_match?.site_id || item.id,
    title: item.display_name || 'Unknown Site',
    coordinates: [item.lon ?? NaN, item.lat ?? NaN],
    category: item.site_type || 'Unknown',
    period: item.period_name || 'Unknown',
    periodStart: item.period_start,
    location: item.country || '',
    description: item.description || '',
    sourceId: 'lyra',
    sourceUrl: item.wikipedia_url || undefined,
  }
}

function suggestionToSiteData(suggestion: SuggestionMatch, itemName: string): SiteData {
  return {
    id: suggestion.site_id,
    title: suggestion.name || itemName,
    coordinates: [NaN, NaN],
    category: 'Unknown',
    period: 'Unknown',
    location: suggestion.country || '',
    description: '',
    sourceId: suggestion.source_id || 'unknown',
    sourceUrl: suggestion.wikipedia_url || undefined,
    image: suggestion.thumbnail_url || undefined,
  }
}

function DbSourceBadge({ source }: { source: string | null }) {
  const key = source === 'user' ? 'ancient_nerds_community' : 'lyra'
  const cfg = SOURCE_CONFIG[key]
  if (!cfg) return null
  return (
    <span
      className="lyra-db-badge"
      style={{ background: cfg.color + '25', color: cfg.color, borderColor: cfg.color + '55' }}
    >
      {cfg.abbr}
    </span>
  )
}

function RadarCard({ item, onViewSite }: { item: RadarItem; onViewSite?: (site: SiteData) => void }) {
  const [factsExpanded, setFactsExpanded] = useState(false)
  const [videosExpanded, setVideosExpanded] = useState(false)
  const [sourcesExpanded, setSourcesExpanded] = useState(false)

  return (
    <div className="lyra-discovery-card">
      {/* Last seen — lower right corner */}
      {item.last_mentioned && (
        <span className="lyra-last-seen-corner" title={`Last mentioned ${new Date(item.last_mentioned).toLocaleString()}`}>{timeAgo(item.last_mentioned)}</span>
      )}

      {/* 1. Name — full width */}
      <div className="lyra-discovery-name-block">
        <h3 className="lyra-discovery-name">
          {item.display_name}
          <CopyButton text={item.display_name} title="Copy site name" size={14} />
          <DbSourceBadge source={item.source} />
        </h3>
        {item.original_name && (
          <span className="lyra-discovery-original-name">
            Corrected from "{item.original_name}"
          </span>
        )}
      </div>

      {/* Rejection reason */}
      {item.rejection_reason && (
        <div className="lyra-discovery-rejection">
          {item.rejection_reason}
        </div>
      )}

      {/* Nearby AN site proximity warning */}
      {item.nearby_an_site && (
        <div className="lyra-discovery-nearby-an">
          Near AN site: {item.nearby_an_site.name} ({item.nearby_an_site.distance_km} km)
        </div>
      )}

      {/* 3. Country + coordinates row */}
      {(item.country || (item.lat != null && item.lon != null)) && (
        <div className="lyra-discovery-country-row">
          {item.country && <CountryFlag country={item.country} size="md" showName />}
          {item.lat != null && item.lon != null && (
            <span className="lyra-discovery-coords">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="2" y1="12" x2="22" y2="12"></line>
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
              </svg>
              {formatCoord(item.lat!, true)}, {formatCoord(item.lon!, false)}
              <CopyButton text={`${formatCoord(item.lat!, true)}, ${formatCoord(item.lon!, false)}`} title="Copy coordinates" />
            </span>
          )}
        </div>
      )}

      {/* 4. Metadata tags (type + period) */}
      <SiteBadges category={item.site_type} period={item.period_name} periodStart={item.period_start} size="md" />

      {/* 5. Thumbnail — click opens SitePopup */}
      {item.thumbnail_url && (
        <div
          className="lyra-discovery-image-wrap lyra-image-clickable"
          key={item.thumbnail_url}
          onClick={() => onViewSite?.(radarItemToSiteData(item))}
        >
          <LazyImage
            src={item.thumbnail_url}
            alt=""
            className="lyra-discovery-image"
          />
          <div className="lyra-image-hover-overlay">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            <span>Site Details</span>
          </div>
        </div>
      )}

      {/* 6. Description */}
      {item.description && (
        <div className="lyra-discovery-description-section">
          <p className="lyra-discovery-description lyra-description-clamped">
            {item.description}
          </p>
        </div>
      )}

      {/* 7. External links row */}
      {(item.wikipedia_url || item.wikidata_id || item.commons_url) && (
        <div className="lyra-wiki-links-row">
          {item.wikipedia_url && (
            <a
              href={item.wikipedia_url}
              target="_blank"
              rel="noopener noreferrer"
              className="lyra-wiki-link"
            >
              <img src="https://www.google.com/s2/favicons?domain=wikipedia.org&sz=32" alt="" className="lyra-link-favicon" />
              Wikipedia
            </a>
          )}
          {item.wikidata_id && (
            <a
              href={`https://www.wikidata.org/wiki/${item.wikidata_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="lyra-wiki-link lyra-wikidata-link"
            >
              <img src="https://www.google.com/s2/favicons?domain=wikidata.org&sz=32" alt="" className="lyra-link-favicon" />
              Wikidata
            </a>
          )}
          {item.commons_url && (
            <a
              href={item.commons_url}
              target="_blank"
              rel="noopener noreferrer"
              className="lyra-wiki-link lyra-wikidata-link"
            >
              <img src="https://www.google.com/s2/favicons?domain=commons.wikimedia.org&sz=32" alt="" className="lyra-link-favicon" />
              Commons
            </a>
          )}
        </div>
      )}

      {/* 8. Score breakdown */}
      <ScoreBreakdown item={item} />

      {/* 8.5. External sources — collapsed by default */}
      {item.external_sources && item.external_sources.length > 0 && (
        <div className="lyra-collapsible">
          <button
            className="lyra-collapsible-header"
            onClick={() => setSourcesExpanded(!sourcesExpanded)}
          >
            <span className="lyra-collapsible-arrow">{sourcesExpanded ? '\u25BE' : '\u25B8'}</span>
            Sources ({item.external_sources.length})
          </button>
          {sourcesExpanded && (
            <div className="lyra-discovery-sources">
              {item.external_sources.map((src) => (
                <span key={`${src.source_id}-${src.site_id}`} className="lyra-source-chip">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5" />
                    <path d="M2 12l10 5 10-5" />
                  </svg>
                  <span className="lyra-source-name">{src.name}</span>
                  {src.source_url && (
                    <a
                      href={src.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="lyra-source-link"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                        <polyline points="15 3 21 3 21 9" />
                        <line x1="10" y1="14" x2="21" y2="3" />
                      </svg>
                    </a>
                  )}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

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

      {/* 11. Best match (high-confidence) */}
      {item.best_match && (
        <div className="lyra-discovery-best-match">
          <span className="lyra-best-match-label">Strong match:</span>
          <button
            className="lyra-suggestion-chip lyra-best-match-chip"
            title={`${Math.round(item.best_match.similarity * 100)}% match`}
            onClick={() => onViewSite?.(suggestionToSiteData(item.best_match!, item.display_name))}
          >
            {item.best_match.name}
            <span className="lyra-best-match-pct">{Math.round(item.best_match.similarity * 100)}%</span>
            {item.best_match.country && (
              <img
                src={getCountryFlatFlagUrl(item.best_match.country) || ''}
                alt=""
                className="lyra-suggestion-flag"
              />
            )}
          </button>
        </div>
      )}

      {/* 12. Other suggestions (only for pending items) */}
      {item.suggestions.filter(s => s.site_id !== item.best_match?.site_id).length > 0 && (
        <div className="lyra-discovery-suggestions">
          <span className="lyra-suggestions-label">Similar sites:</span>
          {item.suggestions.filter(s => s.site_id !== item.best_match?.site_id).slice(0, 3).map((s) => (
            <button
              key={s.site_id}
              className="lyra-suggestion-chip"
              title={`${Math.round(s.similarity * 100)}% match`}
              onClick={() => onViewSite?.(suggestionToSiteData(s, item.display_name))}
            >
              {s.name}
              {s.country && (
                <img
                  src={getCountryFlatFlagUrl(s.country) || ''}
                  alt=""
                  className="lyra-suggestion-flag"
                />
              )}
            </button>
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
  const [selectedSite, setSelectedSite] = useState<SiteData | null>(null)
  const [stats, setStats] = useState<RadarStats | null>(null)
  const [minMentions, setMinMentions] = useState(1)
  const [sortBy, setSortBy] = useState<'score' | 'mentions' | 'recency'>('score')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const sentinelRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const [columnCount, setColumnCount] = useState(3)
  const [showScrollTop, setShowScrollTop] = useState(false)
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [showMap, setShowMap] = useState(false)
  const [mapHoveredId, setMapHoveredId] = useState<string | null>(null)
  const [mapPinnedId, setMapPinnedId] = useState<string | null>(null)
  const hoverTimeoutRef = useRef<number>(0)

  const itemsById = useMemo(() => {
    const map = new Map<string, RadarItem>()
    for (const item of items) map.set(item.id, item)
    return map
  }, [items])

  // Hovered item takes priority (preview), pinned is fallback
  const mapActiveItem = useMemo(() => {
    const id = mapHoveredId || mapPinnedId
    return id ? itemsById.get(id) || null : null
  }, [mapHoveredId, mapPinnedId, itemsById])

  const handleMapHover = useCallback((id: string | null) => {
    clearTimeout(hoverTimeoutRef.current)
    if (id) {
      setMapHoveredId(id)
    } else {
      // 300ms grace period so user can reach the card overlay
      hoverTimeoutRef.current = window.setTimeout(() => setMapHoveredId(null), 300)
    }
  }, [])

  const handleMapPin = useCallback((id: string | null) => {
    if (id && id === mapPinnedId) {
      setMapPinnedId(null)  // toggle off
    } else {
      setMapPinnedId(id)
    }
  }, [mapPinnedId])

  const handleCardEnter = useCallback(() => {
    clearTimeout(hoverTimeoutRef.current)
  }, [])

  const handleCardLeave = useCallback(() => {
    if (!mapPinnedId) {
      hoverTimeoutRef.current = window.setTimeout(() => setMapHoveredId(null), 300)
    }
  }, [mapPinnedId])

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
      const cols = Math.max(1, Math.floor(w / 300))
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
    statusParam: string = statusFilter,
    srcParam: string = sourceFilter
  ) => {
    try {
      setLoading(true)
      setError(null)
      const url = `${config.api.baseUrl}/radar/list?page=${pageNum}&page_size=24&min_mentions=${mentions}&sort_by=${sort}&status=${statusParam}&source_filter=${srcParam}`
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
  }, [minMentions, sortBy, statusFilter, sourceFilter])

  // Initial load & filter changes
  useEffect(() => {
    fetchRadar(1, false, minMentions, sortBy, statusFilter, sourceFilter)
  }, [minMentions, sortBy, statusFilter, sourceFilter])

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
          fetchRadar(page + 1, true, minMentions, sortBy, statusFilter, sourceFilter)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchRadar, minMentions, sortBy, statusFilter, sourceFilter])

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

  const handleSourceChange = (value: SourceFilter) => {
    setSourceFilter(value)
    setItems([])
    setPage(1)
    setHasMore(false)
  }

  return (
    <div className="lyra-discoveries-page">
      {/* Header */}
      <header className="news-page-header">
        <a href="/globe.html" className="news-page-brand">
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
          <span className="lyra-discoveries-filter-label">Database:</span>
          <div className="lyra-discoveries-filter-chips">
            {([['all', 'All'], ['lyra', 'Radar'], ['user', 'Community']] as const).map(([val, label]) => (
              <button
                key={val}
                className={`news-page-chip${sourceFilter === val ? ' active' : ''}`}
                onClick={() => handleSourceChange(val)}
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
        <div className="lyra-filter-group">
          <button
            className={`news-page-chip${showMap ? ' active' : ''}`}
            onClick={() => setShowMap(v => !v)}
          >
            Map
          </button>
        </div>
      </div>

      {/* AI disclosure */}
      <div className="news-page-ai-notice">
        Content is AI-generated from YouTube video content. Always verify with original sources.
      </div>

      {/* Map */}
      {showMap && (
        <div className="radar-map-wrapper">
          <Suspense fallback={<div style={{ height: 'calc(100vh - 180px)' }} />}>
            <RadarMap items={items} onHoverItem={handleMapHover} onPinItem={handleMapPin}>
              {mapActiveItem && (
                <div
                  className={`radar-map-card-overlay${mapPinnedId ? ' pinned' : ''}`}
                  onMouseEnter={handleCardEnter}
                  onMouseLeave={handleCardLeave}
                >
                  {mapPinnedId && (
                    <button className="radar-map-card-close" onClick={() => setMapPinnedId(null)} aria-label="Close">×</button>
                  )}
                  <RadarCard item={mapActiveItem} onViewSite={setSelectedSite} />
                </div>
              )}
            </RadarMap>
          </Suspense>
        </div>
      )}

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
            {/* Radar cards */}
            {items.filter((_, i) => i % columnCount === colIdx).map(item => (
              <div key={item.id} data-radar-id={item.id}>
                <RadarCard item={item} onViewSite={setSelectedSite} />
              </div>
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

      {selectedSite && (
        <SitePopupOverlay site={selectedSite} onClose={() => setSelectedSite(null)} />
      )}
    </div>
  )
}
