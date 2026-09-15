/**
 * LyraRadarPage — site candidates for the curated set, awaiting a decision.
 * Accessed via /radar.html (separate Vite entry point).
 *
 * A candidate is a place named in our own content that is not in the curated
 * ancient_nerds set. Most of them DO exist under one of the bulk external
 * sources; that is enrichment (coordinates, metadata), not a duplicate, and
 * the "Sources" chips on each card say which. Items already resolved to a
 * curated site (`matched`) and non-sites are excluded entirely.
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { formatCoord, timeAgo } from '../utils/formatters'
import { SiteBadges, CountryFlag, CopyButton } from '../components/metadata'
import { SOURCE_CONFIG } from '../constants/colors'
import { SitePopupOverlay } from '../components/SitePopupOverlay'
import PageHeader from '../components/layout/PageHeader'
import PageStatsBar from '../components/layout/PageStatsBar'
import type { StatItem } from '../components/layout/PageStatsBar'
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import { useAuth } from '../contexts/AuthContext'
import LazyImage from '../components/LazyImage'
import type { SiteData } from '../data/sites'
import './LyraRadarPage.css'

const LyraProfileModal = lazy(() => import('../components/LyraProfileModal'))
const RadarMap = lazy(() => import('../components/RadarMap'))
const ProposalsReview = lazy(() => import('../components/ProposalsReview'))
import type { RadarMapItem } from '../components/RadarMap'
import { ApproveModal, MergeModal } from '../components/RadarReviewModals'

interface VideoReference {
  video_id: string
  channel_name: string
  timestamp_seconds: number
  deep_url: string
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
  period_end: number | null
  thumbnail_url: string | null
  screenshot_url: string | null
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
  external_sources: ExternalSource[]
  confidence: string | null
  data_sources: string[]
  commons_url: string | null
  nearby_an_site: { site_id: string; name: string; distance_km: number } | null
  source: string | null
  avg_significance: number | null
  top_news_category: string | null
  is_speculative: boolean
  speculative_tag: string | null
  ai_reasoning: string | null
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
  rejected_count: number
  added_count: number
  curated_sites: number
}

type StatusFilter = 'all' | 'enriched' | 'added' | 'rejected'

/** Narrowest a review card may get. Drives both the column count and the CSS
 *  min-width, so the two can never disagree (they did: the grid divided by 300
 *  while nothing stopped a column from rendering at 34px). */
const MIN_COLUMN_PX = 320
/** How far the card pane must scroll before the globe collapses. */
const GLOBE_HIDE_SCROLL_PX = 80

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
    case 'dismissed':
      label = 'Dismissed'
      cls = 'lyra-status-rejected'
      hint = 'Dismissed by founder review'
      break
    case 'matched':
      label = 'Matched'
      cls = 'lyra-status-added'
      hint = 'Merged into an existing database site'
      break
    default:
      label = 'Processing'
      cls = 'lyra-status-pending'
      hint = 'Waiting for enrichment'
  }
  return <span className={`lyra-status-pill ${cls}`} title={hint}>{label}</span>
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
  // Power curve so 75% = yellow, 85% = yellow-green, 95%+ = green
  const hue = Math.round(Math.pow(pct / 100, 2.5) * 120)
  return `hsl(${hue}, 72%, 55%)`
}

const CATEGORY_GROUPS: Record<string, string> = {
  excavation: 'fieldwork', survey: 'fieldwork', underwater: 'fieldwork',
  artifact: 'analysis', dating: 'analysis', bioarchaeology: 'analysis', epigraphy: 'analysis',
  remote_sensing: 'tech', technology: 'tech', archaeoastronomy: 'tech',
  conservation: 'heritage', heritage: 'heritage', art: 'heritage', architecture: 'heritage',
  theory: 'other', general: 'other', speculative: 'other',
}

function getCategoryGroup(category: string): string {
  return CATEGORY_GROUPS[category] || 'other'
}

function ScoreBreakdown({ item }: { item: RadarItem }) {
  // The percentage comes from the API (_score_sql in api/routes/radar.py), the
  // same number the list was sorted by. SCORE_WEIGHTS only labels the chips —
  // recomputing the total here is how the two drifted apart on 167 cards.
  const pct = item.enrichment_score

  return (
    <div className="lyra-score-section">
      <div className="lyra-score-header" title={`Data completeness: ${pct}/100 points. Higher scores mean more metadata (coordinates, period, category, description, images) was found for this site.`}>
        <span className="lyra-discovery-percentage" style={{ color: scoreColor(pct) }}>{pct}%</span>
        <span className="lyra-score-badges">
          <StatusPill status={item.enrichment_status} />
          {item.confidence && (
            <div className="radar-confidence-wrapper">
              <span className={`lyra-status-pill lyra-confidence-${item.confidence}`} title={`AI confidence: ${item.confidence}`}>
                {item.confidence}
              </span>
              {item.ai_reasoning && (
                <div className="radar-ai-tooltip">{item.ai_reasoning}</div>
              )}
            </div>
          )}
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
      {item.avg_significance != null && (
        <div className="radar-significance">
          <span>Story importance</span>
          <div className="radar-significance-bar">
            <div className="radar-significance-fill"
                 style={{ width: `${(item.avg_significance / 10) * 100}%` }} />
          </div>
          <span>{item.avg_significance}/10</span>
        </div>
      )}
    </div>
  )
}

function radarItemToSiteData(item: RadarItem): SiteData {
  return {
    id: item.id,
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

function RadarCard({ item, onViewSite, onApprove, onDismiss, onMerge }: {
  item: RadarItem
  onViewSite?: (site: SiteData) => void
  onApprove?: (id: string, overrides: Record<string, unknown>) => Promise<string | null>
  onDismiss?: (id: string) => void
  onMerge?: (id: string, siteId: string) => Promise<string | null>
}) {
  const [factsExpanded, setFactsExpanded] = useState(false)
  const [videosExpanded, setVideosExpanded] = useState(false)
  const [sourcesExpanded, setSourcesExpanded] = useState(false)
  const [showApprove, setShowApprove] = useState(false)
  const [showMerge, setShowMerge] = useState(false)
  const [confirmDismiss, setConfirmDismiss] = useState(false)

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

      {item.is_speculative && item.speculative_tag && (
        <span className="radar-speculative-badge">
          &#9888; Speculative: {item.speculative_tag.replace(/_/g, ' ')}
        </span>
      )}

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
      {item.top_news_category && item.top_news_category !== 'general' && (
        <span className={`radar-category-chip radar-category-chip--${getCategoryGroup(item.top_news_category)}`}>
          {item.top_news_category.replace(/_/g, ' ')}
        </span>
      )}

      {/* 5. Thumbnail — click opens SitePopup (fallback to story screenshot) */}
      {(item.thumbnail_url || item.screenshot_url) && (
        <div
          className="lyra-discovery-image-wrap lyra-image-clickable"
          key={item.thumbnail_url || item.screenshot_url}
          onClick={() => onViewSite?.(radarItemToSiteData(item))}
        >
          <LazyImage
            src={(item.thumbnail_url || item.screenshot_url)!}
            fallbackSrc={item.thumbnail_url && item.screenshot_url ? item.screenshot_url : undefined}
            alt={item.display_name || ''}
            className="lyra-discovery-image"
            onError={(e) => {
              // Hide entire image wrapper if all sources fail
              const wrap = (e.target as HTMLElement).closest('.lyra-discovery-image-wrap')
              if (wrap) (wrap as HTMLElement).style.display = 'none'
            }}
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
              <img src="https://www.google.com/s2/favicons?domain=wikipedia.org&sz=32" alt="" className="lyra-link-favicon" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
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
              <img src="https://www.google.com/s2/favicons?domain=wikidata.org&sz=32" alt="" className="lyra-link-favicon" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
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
              <img src="https://www.google.com/s2/favicons?domain=commons.wikimedia.org&sz=32" alt="" className="lyra-link-favicon" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              Commons
            </a>
          )}
        </div>
      )}

      {/* 8. Score breakdown */}
      <ScoreBreakdown item={item} />

      {/* 8a. Founder review actions — any enriched item */}
      {item.enrichment_status === 'enriched' && onApprove && onDismiss && onMerge && (
        <div className="radar-review-actions">
          <button className="lyra-promote-btn" onClick={() => setShowApprove(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            Approve
          </button>
          <button className="radar-merge-btn" onClick={() => setShowMerge(true)}>
            Merge
          </button>
          {confirmDismiss ? (
            <button
              className="radar-dismiss-btn radar-dismiss-confirm"
              onClick={() => { setConfirmDismiss(false); onDismiss(item.id) }}
              onBlur={() => setConfirmDismiss(false)}
            >
              Confirm reject?
            </button>
          ) : (
            <button className="radar-dismiss-btn" onClick={() => setConfirmDismiss(true)}>
              Reject
            </button>
          )}
        </div>
      )}
      {showApprove && onApprove && (
        <ApproveModal
          item={item}
          onSubmit={(overrides) => onApprove(item.id, overrides)}
          onClose={() => setShowApprove(false)}
        />
      )}
      {showMerge && onMerge && (
        <MergeModal
          itemName={item.display_name}
          nearbyAnSite={item.nearby_an_site}
          onMerge={(siteId) => onMerge(item.id, siteId)}
          onClose={() => setShowMerge(false)}
        />
      )}

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
  const [minMentions, setMinMentions] = useState(0)
  const [sortBy, setSortBy] = useState<'score' | 'mentions' | 'recency'>('score')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('enriched')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [hideSpeculative, setHideSpeculative] = useState(false)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const cardsPaneRef = useRef<HTMLDivElement>(null)
  const [showScrollTop, setShowScrollTop] = useState(false)
  const [globeHiddenByScroll, setGlobeHiddenByScroll] = useState(false)
  const [globePinned, setGlobePinned] = useState(false)
  const showGlobe = globePinned || !globeHiddenByScroll
  // 'radar' = the YouTube-fed queue; 'proposals' = the prospector's queue
  // (papers/stories, dedup-adjudicated). Founder-only on the API side.
  // Founders land on the proposals queue (one queue since the radar backlog
  // was absorbed into it); #radar opens the map-and-history view.
  const [requestedView, setView] = useState<'radar' | 'proposals'>(
    () => (window.location.hash === '#radar' ? 'radar' : 'proposals')
  )
  const [filtersExpanded, setFiltersExpanded] = useState(false)
  const [columnCount, setColumnCount] = useState(1)
  const [allRadarMapItems, setAllRadarMapItems] = useState<RadarItem[]>([])
  const [highlightedCardId, setHighlightedCardId] = useState<string | null>(null)
  const [pinnedItem, setPinnedItem] = useState<RadarItem | null>(null)
  const radarMapFetched = useRef(false)

  // Auth (founder role check)
  const { user, token } = useAuth()
  const isFounder = !!user?.is_founder
  // A visitor who lands on #proposals is not a founder: show them the radar,
  // not an "access required" message where the list used to be.
  const view = requestedView === 'proposals' && isFounder ? 'proposals' : 'radar'
  const hoverTimeoutRef = useRef<number>(0)

  const handleMapHover = useCallback((id: string | null) => {
    clearTimeout(hoverTimeoutRef.current)
    if (id) {
      setHighlightedCardId(id)
    } else {
      hoverTimeoutRef.current = window.setTimeout(() => setHighlightedCardId(null), 300)
    }
  }, [])

  // The map holds every candidate with coordinates; the list holds one page.
  // Scrolling to the card only works when it happens to be loaded, so fall
  // back to fetching the item — otherwise the click is a silent no-op, which
  // it was for 412 of 436 dots on first load.
  const handleMapPin = useCallback((id: string | null) => {
    if (!id) {
      setPinnedItem(null)
      return
    }
    const cardEl = document.querySelector(`[data-radar-id="${CSS.escape(id)}"]`)
    if (cardEl) {
      setPinnedItem(null)
      cardEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setHighlightedCardId(id)
      return
    }
    fetch(`${config.api.baseUrl}/radar/item/${id}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => setPinnedItem(d))
      .catch(() => setPinnedItem(null))
  }, [])

  // Mirror EVERY list filter, not just status — otherwise the panes show
  // different populations and a dot can exist with no reachable card.
  const mapFilterFn = useCallback((item: RadarMapItem) => {
    if (item.mention_count < minMentions) return false
    if (statusFilter === 'all') return true
    if (statusFilter === 'rejected') {
      return item.enrichment_status === 'rejected' || item.enrichment_status === 'dismissed'
    }
    const mapped = statusFilter === 'added' ? 'promoted' : statusFilter
    return item.enrichment_status === mapped
  }, [statusFilter, minMentions])

  const authPost = useCallback(async (path: string, body?: unknown): Promise<Response> => {
    return fetch(`${config.api.baseUrl}${path}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
  }, [token])

  const refreshStats = useCallback(() => {
    fetch(`${config.api.baseUrl}/radar/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStats(d) })
      .catch(() => {})
  }, [])

  const handleApprove = useCallback(async (itemId: string, overrides: Record<string, unknown>): Promise<string | null> => {
    if (!token) return 'Not authenticated'
    try {
      const resp = await authPost(`/radar/${itemId}/promote`, Object.keys(overrides).length ? overrides : undefined)
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
        const detail = data.detail
        return typeof detail === 'object' && detail?.message ? detail.message : String(detail || resp.statusText)
      }
      setItems(prev => prev.map(it =>
        it.id === itemId ? { ...it, enrichment_status: 'promoted' } : it
      ))
      refreshStats()
      return null
    } catch (e) {
      return e instanceof Error ? e.message : 'Network error'
    }
  }, [token, authPost, refreshStats])

  const handleDismiss = useCallback(async (itemId: string) => {
    if (!token) return
    try {
      const resp = await authPost(`/radar/${itemId}/dismiss`)
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
        alert(`Dismiss failed: ${data.detail || resp.statusText}`)
        return
      }
      setItems(prev => prev.map(it =>
        it.id === itemId ? { ...it, enrichment_status: 'dismissed' } : it
      ))
      refreshStats()
    } catch (e) {
      alert(`Dismiss failed: ${e instanceof Error ? e.message : 'Network error'}`)
    }
  }, [token, authPost, refreshStats])

  const handleMerge = useCallback(async (itemId: string, siteId: string): Promise<string | null> => {
    if (!token) return 'Not authenticated'
    try {
      const resp = await authPost(`/radar/${itemId}/merge`, { site_id: siteId })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
        return String(data.detail || resp.statusText)
      }
      setItems(prev => prev.map(it =>
        it.id === itemId ? { ...it, enrichment_status: 'matched' } : it
      ))
      refreshStats()
      return null
    } catch (e) {
      return e instanceof Error ? e.message : 'Network error'
    }
  }, [token, authPost, refreshStats])

  // The page root is height:100vh/overflow:hidden, so `window` never scrolls —
  // the card pane is the only scroller. Both the scroll-to-top button and the
  // globe collapse hang off it.
  useEffect(() => {
    const pane = cardsPaneRef.current
    if (!pane) return
    const onScroll = () => {
      setShowScrollTop(pane.scrollTop > 400)
      setGlobeHiddenByScroll(pane.scrollTop > GLOBE_HIDE_SCROLL_PX)
    }
    pane.addEventListener('scroll', onScroll, { passive: true })
    return () => pane.removeEventListener('scroll', onScroll)
  }, [])

  const fetchRadar = useCallback(async (
    pageNum: number,
    append: boolean = false,
    mentions: number = minMentions,
    sort: string = sortBy,
    statusParam: string = statusFilter,
    catParam: string = categoryFilter,
    specParam: boolean = hideSpeculative
  ) => {
    try {
      setLoading(true)
      setError(null)
      // page_size=100 (the API max): the review queue is ~420 items, and each
      // page costs one rate-limited request.
      const url = `${config.api.baseUrl}/radar/list?page=${pageNum}&page_size=100&min_mentions=${mentions}&sort_by=${sort}&status=${statusParam}&news_category=${catParam}&hide_speculative=${specParam}`
      const resp = await fetch(url)
      if (!resp.ok) {
        throw new Error(resp.status === 429
          ? 'Too many requests — the list refreshes in under a minute.'
          : `HTTP ${resp.status}`)
      }
      const data: RadarResponse = await resp.json()
      setItems(prev => append ? [...prev, ...data.items] : data.items)
      setHasMore(data.has_more)
      setPage(pageNum)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [minMentions, sortBy, statusFilter, categoryFilter, hideSpeculative])

  // Initial load & filter changes
  useEffect(() => {
    fetchRadar(1, false, minMentions, sortBy, statusFilter, categoryFilter, hideSpeculative)
  }, [minMentions, sortBy, statusFilter, categoryFilter, hideSpeculative])

  // Fetch stats
  useEffect(() => {
    fetch(`${config.api.baseUrl}/radar/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStats(d) })
      .catch(() => {})
  }, [])

  // Fetch all radar items for map (once on mount)
  useEffect(() => {
    if (radarMapFetched.current) return
    radarMapFetched.current = true
    fetch(`${config.api.baseUrl}/radar/map`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (Array.isArray(data)) setAllRadarMapItems(data.map((d: Partial<RadarItem>) => ({
          id: d.id ?? '',
          source: d.source ?? null,
          display_name: d.display_name ?? '',
          enrichment_status: d.enrichment_status ?? 'pending',
          enrichment_score: d.enrichment_score ?? 0,
          country: d.country ?? null,
          site_type: d.site_type ?? null,
          period_name: d.period_name ?? null,
          period_start: d.period_start ?? null,
          period_end: d.period_end ?? null,
          lat: d.lat ?? null,
          lon: d.lon ?? null,
          mention_count: d.mention_count ?? 0,
          description: d.description ?? null,
          wikipedia_url: d.wikipedia_url ?? null,
          thumbnail_url: d.thumbnail_url ?? null,
          screenshot_url: d.screenshot_url ?? null,
          wikidata_id: d.wikidata_id ?? null,
          original_name: null,
          rejection_reason: null,
          facts: [],
          videos: [],
          external_sources: [],
          unique_videos: 0,
          unique_channels: 0,
          last_mentioned: null,
          confidence: null,
          data_sources: [],
          commons_url: null,
          nearby_an_site: null,
          avg_significance: null,
          top_news_category: null,
          is_speculative: false,
          speculative_tag: null,
          ai_reasoning: null,
        })))
      })
      .catch(() => {})
  }, [])

  // Infinite scroll
  useEffect(() => {
    if (!sentinelRef.current || !hasMore || loading) return
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          fetchRadar(page + 1, true, minMentions, sortBy, statusFilter, categoryFilter, hideSpeculative)
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, page, fetchRadar, minMentions, sortBy, statusFilter, categoryFilter, hideSpeculative])

  // Auto-detect column count for card grid. The map pane's width is pure CSS
  // now — deriving it from the container height used to starve this grid.
  useEffect(() => {
    const el = gridRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      const w = entry.contentRect.width
      setColumnCount(Math.max(1, Math.floor(w / MIN_COLUMN_PX)))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

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
      <PageHeader
        speechBubble="Places named in our own content that aren't in the curated site database yet"
        onAvatarClick={() => setShowLyraProfile(true)}
        currentPage="radar"
      >
        <span className="page-header-title">Radar</span>
      </PageHeader>



      {/* Filter bar — collapsed by default */}
      <div className="lyra-discoveries-filters">
        <button className="radar-filter-toggle" onClick={() => setFiltersExpanded(v => !v)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
          Filters
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ transform: filtersExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}><path d="M6 9l6 6 6-6"/></svg>
        </button>
        {filtersExpanded && <>
            <div className="lyra-filter-group">
              <span className="lyra-discoveries-filter-label">Status:</span>
              <div className="lyra-discoveries-filter-chips">
                {/* No 'Pending' chip: match and identify run in the same hourly
                    cycle, so no contribution is ever read in that state. */}
                {([['enriched', 'To review'], ['added', 'Added'], ['rejected', 'Rejected'], ['all', 'All']] as const).map(([val, label]) => (
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
                {[0, 2, 3, 5, 10].map(n => (
                  <button
                    key={n}
                    className={`news-page-chip${minMentions === n ? ' active' : ''}`}
                    onClick={() => handleMinMentionsChange(n)}
                  >
                    {n === 0 ? 'Any' : `${n}+`}
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
              <span className="lyra-discoveries-filter-label">Category:</span>
              <div className="lyra-discoveries-filter-chips">
                {(['all', 'excavation', 'artifact', 'dating', 'remote_sensing', 'architecture'] as const).map(val => (
                  <button key={val}
                    className={`news-page-chip${categoryFilter === val ? ' active' : ''}`}
                    onClick={() => { setCategoryFilter(val); setItems([]); setPage(1); setHasMore(false) }}>
                    {val === 'all' ? 'All' : val.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            </div>
            <div className="lyra-filter-group">
              <button
                className={`news-page-chip${hideSpeculative ? ' active' : ''}`}
                onClick={() => { setHideSpeculative(v => !v); setItems([]); setPage(1); setHasMore(false) }}>
                Hide speculative
              </button>
            </div>
        </>}
      </div>

      {/* Stats bar */}
      {stats && (
        <PageStatsBar items={[
          { value: stats.enriched_count, label: 'to review' } as StatItem,
          { value: stats.added_count, label: 'added', sep: '·' } as StatItem,
          { value: stats.rejected_count, label: 'rejected', sep: '·' } as StatItem,
          { value: stats.curated_sites, label: 'curated sites', sep: '·' } as StatItem,
        ]} />
      )}

      <div className={`radar-split-view${showGlobe ? '' : ' globe-collapsed'}`}>
        {/* LEFT: Map pane. Unmounted when collapsed so RadarMap's cleanup runs
            and its requestAnimationFrame sweep stops burning a CPU core. */}
        <div className="radar-split-map">
          {showGlobe && (
            <Suspense fallback={<div style={{ width: '100%', height: '100%' }} />}>
              <RadarMap items={allRadarMapItems} highlightId={highlightedCardId}
                        filterFn={mapFilterFn}
                        onHoverItem={handleMapHover} onPinItem={handleMapPin}>
                {pinnedItem && (
                  <div className="radar-map-card-overlay pinned">
                    <button
                      className="radar-map-card-close"
                      onClick={() => setPinnedItem(null)}
                      aria-label="Close"
                    >
                      &times;
                    </button>
                    <RadarCard item={pinnedItem} onViewSite={setSelectedSite}
                               onApprove={isFounder ? handleApprove : undefined}
                               onDismiss={isFounder ? handleDismiss : undefined}
                               onMerge={isFounder ? handleMerge : undefined} />
                  </div>
                )}
              </RadarMap>
            </Suspense>
          )}
        </div>

        {/* RIGHT: Card list */}
        <div
          className="radar-split-cards"
          ref={cardsPaneRef}
          style={{ ['--radar-column-width' as string]: `${MIN_COLUMN_PX}px` }}
        >
          <button
            className="radar-globe-toggle"
            onClick={() => {
              const next = !showGlobe
              setGlobePinned(next)
              setGlobeHiddenByScroll(!next)
            }}
            title={showGlobe ? 'Hide the globe and widen the review list' : 'Show the globe'}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="2" y1="12" x2="22" y2="12" />
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
            {showGlobe ? 'Hide globe' : 'Show globe'}
          </button>
          {isFounder && (
            <span className="radar-view-toggle">
              {([['radar', 'Radar'], ['proposals', 'Proposals']] as const).map(([val, label]) => (
                <button key={val} className={`news-page-chip${view === val ? ' active' : ''}`}
                        onClick={() => { setView(val); window.location.hash = val === 'radar' ? '#radar' : '#proposals' }}>
                  {label}
                </button>
              ))}
            </span>
          )}

          <AiNoticeBanner />

          {view === 'proposals' && (
            <Suspense fallback={<div className="news-page-loading">Loading…</div>}>
              <ProposalsReview token={token} isFounder={isFounder} onViewSite={setSelectedSite} columnCount={columnCount} />
            </Suspense>
          )}
          {view === 'radar' && (<>
          {error && (
            <div className="news-page-error">
              {error}
              <button onClick={() => fetchRadar(1)}>Retry</button>
            </div>
          )}

          {!error && items.length === 0 && !loading && (
            <div className="news-page-empty">No radar items yet. Lyra is still watching...</div>
          )}

          <div className="lyra-discoveries-grid" ref={gridRef}>
            {Array.from({ length: columnCount }, (_, colIdx) => (
              <div key={colIdx} className="lyra-discoveries-column">
                {items.filter((_, i) => i % columnCount === colIdx).map(item => (
                  <div key={item.id} data-radar-id={item.id}
                       onMouseEnter={() => setHighlightedCardId(item.id)}
                       onMouseLeave={() => setHighlightedCardId(null)}>
                    <RadarCard item={item} onViewSite={setSelectedSite}
                               onApprove={isFounder ? handleApprove : undefined}
                               onDismiss={isFounder ? handleDismiss : undefined}
                               onMerge={isFounder ? handleMerge : undefined} />
                  </div>
                ))}
              </div>
            ))}
          </div>

          {loading && <div className="news-page-loading">Loading...</div>}
          <div ref={sentinelRef} style={{ height: 1 }} />
          </>)}
        </div>
      </div>

      {/* Scroll to top button */}
      {showScrollTop && (
        <button
          className="lyra-scroll-top"
          onClick={() => cardsPaneRef.current?.scrollTo({ top: 0, behavior: 'smooth' })}
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
