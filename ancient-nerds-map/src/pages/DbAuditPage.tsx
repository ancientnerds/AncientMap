import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { config } from '../config'
import { CATEGORY_COLORS, PERIOD_ORDER, SORTED_PERIODS, getCategoryColor, getPeriodColor, SOURCE_CONFIG } from '../constants/colors'
import { useAuth } from '../contexts/AuthContext'
import { resolvePeriod } from '../data/sites'
import type { SiteData } from '../data/sites'
import { SitePopupOverlay } from '../components/SitePopupOverlay'
import PageHeader from '../components/layout/PageHeader'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { exportCSV, exportJSON, exportGeoJSON, parseCSV, parseJSON, parseGeoJSON } from '../utils/exportFormats'
import type { ParsedSite } from '../utils/exportFormats'
import { MetadataBadge } from '../components/metadata/MetadataBadge'
import { CopyButton } from '../components/metadata/CopyButton'
import { viewOnGlobe } from '../components/SiteCard'
import SiteForm from '../components/SiteForm'
import type { SiteFormValues } from '../components/SiteForm'
import '../styles/db-audit.css'

declare const __BUILD_HASH__: string
const CACHE_BUSTER = `_v=${__BUILD_HASH__}`

interface AuditSite {
  id: string
  n: string        // name
  la: number       // lat
  lo: number       // lon
  s: string        // source_id
  t?: string       // site_type
  p?: number       // period_start
  pn?: string      // period_name
  d?: string       // description
  cd?: string      // card_description
  c?: string       // country
  u?: string       // source_url
  i?: string       // thumbnail_url
  eb?: string      // edited_by
  ea?: string      // edited_at (ISO timestamp)
  aud?: string     // last_audited (ISO timestamp)
}

type IssueFilter = 'all' | 'no_period' | 'no_type' | 'no_country' | 'suspect_modern' | 'no_desc' | 'no_source' | 'no_image' | 'no_coords'
type SortColumn = 'name' | 'type' | 'period' | 'country' | 'edited_at' | 'audited'
type SortDir = 'asc' | 'desc'

const CATEGORY_OPTIONS = Object.keys(CATEGORY_COLORS)
const ROWS_PER_PAGE = 500

interface SnapshotEntry {
  date: string
  file: string
  sites: number
  by_source?: Record<string, number>
}

interface FieldChange { from: string; to: string }
interface ChangedSite { id: string; n: string; fields: Record<string, FieldChange> }
interface DiffSummary {
  added: number; removed: number; changed: number
  fields: Record<string, number>
}
interface DiffResponse {
  from_date: string; to_date: string
  from_count: number; to_count: number
  summary: DiffSummary
  added: AuditSite[]
  removed: AuditSite[]
  changed: ChangedSite[]
}

interface PendingEdit {
  siteId: string
  siteName: string
  changes: Record<string, { old: string; new: string }>
  fullUpdate: {
    id: string; title: string; description?: string; category: string
    period: string; coordinates: [number, number]; sourceUrl?: string; country?: string
  }
}

function hasPeriodIssue(s: AuditSite) { return !s.pn && s.p == null }
function hasTypeIssue(s: AuditSite) { return !s.t }
function hasCountryIssue(s: AuditSite) { return !s.c }
function isSuspectModern(s: AuditSite) { return s.p != null && s.p > 1500 }
function hasDescIssue(s: AuditSite) { return !s.d }
function hasSourceIssue(s: AuditSite) { return !s.u }
function hasImageIssue(s: AuditSite) { return !s.i }
function hasCoordsIssue(s: AuditSite) { return s.la === 0 && s.lo === 0 }

function formatRelativeDate(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDays = Math.floor(diffHr / 24)
  if (diffDays < 30) return `${diffDays}d ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: d.getFullYear() !== now.getFullYear() ? 'numeric' : undefined })
}

// ─── Multi-select dropdown ───────────────────────────────────────────────────
function MultiSelect({ label, options, selected, onChange, colorFn }: {
  label: string
  options: string[]
  selected: Set<string>
  onChange: (s: Set<string>) => void
  colorFn?: (v: string) => string | undefined
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const filtered = search
    ? options.filter(o => o.toLowerCase().includes(search.toLowerCase()))
    : options

  const allSelected = selected.size === 0
  const count = selected.size

  const toggle = (val: string) => {
    const next = new Set(selected)
    if (next.has(val)) next.delete(val)
    else next.add(val)
    onChange(next)
  }

  return (
    <div className="db-multiselect" ref={ref}>
      <button
        className={`db-multiselect-trigger ${count > 0 ? 'has-selection' : ''}`}
        onClick={() => setOpen(!open)}
      >
        <span className="db-multiselect-label">{label}:</span>
        <span className="db-multiselect-value">
          {allSelected ? 'All' : count === 1 ? [...selected][0] : `${count} selected`}
        </span>
        <span className="db-multiselect-arrow">{open ? '\u25B4' : '\u25BE'}</span>
      </button>
      {open && (
        <div className="db-multiselect-panel">
          {options.length > 6 && (
            <input
              className="db-multiselect-search"
              placeholder="Search..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              autoFocus
            />
          )}
          <div className="db-multiselect-actions">
            <button onClick={() => onChange(new Set())}>All</button>
            <button onClick={() => onChange(new Set(options))}>Select All</button>
            {count > 0 && <button onClick={() => onChange(new Set())}>Clear</button>}
          </div>
          <div className="db-multiselect-list">
            {filtered.map(opt => {
              const color = colorFn?.(opt)
              return (
                <label key={opt} className="db-multiselect-item">
                  <input
                    type="checkbox"
                    checked={selected.has(opt)}
                    onChange={() => toggle(opt)}
                  />
                  {color && <span className="db-multiselect-dot" style={{ background: color }} />}
                  <span>{opt}</span>
                </label>
              )
            })}
            {filtered.length === 0 && <div className="db-multiselect-empty">No matches</div>}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function DbAuditPage() {
  const { user, token } = useAuth()
  const isFounder = !!user?.is_founder

  const [sites, setSites] = useState<AuditSite[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Hero image status
  const [heroStatus, setHeroStatus] = useState<Record<string, { path: string; original_url: string; attribution_url: string }>>({})
  const [heroPopup, setHeroPopup] = useState<{ siteId: string; rect: DOMRect } | null>(null)
  const [heroImageUrl, setHeroImageUrl] = useState('')
  const [heroAttrUrl, setHeroAttrUrl] = useState('')
  const [heroSaving, setHeroSaving] = useState(false)
  const [heroError, setHeroError] = useState('')
  const heroPopoverRef = useRef<HTMLDivElement>(null)
  // Filters & sort
  const [searchQuery, setSearchQuery] = useState('')
  const [activeIssue, setActiveIssue] = useState<IssueFilter>('all')
  const [typeFilters, setTypeFilters] = useState<Set<string>>(new Set())
  const [countryFilters, setCountryFilters] = useState<Set<string>>(new Set())
  const [periodFilters, setPeriodFilters] = useState<Set<string>>(new Set())
  const [editedByFilters, setEditedByFilters] = useState<Set<string>>(new Set())
  const [sortColumn, setSortColumn] = useState<SortColumn>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  // Pagination
  const [visibleRows, setVisibleRows] = useState(ROWS_PER_PAGE)

  // Inline editing
  const [editingCell, setEditingCell] = useState<{ id: string; field: 'type' | 'period' | 'country' } | null>(null)
  const [editValue, setEditValue] = useState('')

  // Modal editing
  const [editModalSite, setEditModalSite] = useState<AuditSite | null>(null)
  const [modalFormValues, setModalFormValues] = useState<SiteFormValues | null>(null)
  // Expanded descriptions
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  // Site popup
  const [popupSite, setPopupSite] = useState<SiteData | null>(null)

  // Source filter
  const [sourceFilter, setSourceFilter] = useState('all')

  // Version snapshots (per-source)
  const [snapshots, setSnapshots] = useState<SnapshotEntry[]>([])
  const [sourceVersions, setSourceVersions] = useState<Record<string, string>>({
    ancient_nerds: 'latest', lyra: 'latest', ancient_nerds_community: 'latest',
  })
  const [activePins, setActivePins] = useState<Record<string, string | null>>({})
  const [pinLoading, setPinLoading] = useState<string | null>(null)

  // DB Snapshots (from API)
  const [dbSnapshots, setDbSnapshots] = useState<{ id: string; created_at: string; created_by: string; description: string; snapshot_type: string; row_count: number; source_id: string | null; site_names: string[] }[]>([])

  // Snapshot preview (undo diff)
  interface SnapshotFieldDiff { field: string; current: string | null; restore_to: string | null }
  interface SnapshotSitePreview { site_id: string; name: string; status: 'changed' | 'unchanged' | 'deleted'; fields: SnapshotFieldDiff[] }
  interface SnapshotPreview { snapshot_id: string; created_at: string; created_by: string; description: string; snapshot_type: string; row_count: number; sites: SnapshotSitePreview[]; changed_count: number; unchanged_count: number; deleted_count: number }
  const [snapshotPreview, setSnapshotPreview] = useState<SnapshotPreview | null>(null)
  const [snapshotPreviewLoading, setSnapshotPreviewLoading] = useState(false)

  // Pending edits (edit session)
  const [pendingEdits, setPendingEdits] = useState<Map<string, PendingEdit>>(new Map())
  const [showReviewModal, setShowReviewModal] = useState(false)
  const [committing, setCommitting] = useState(false)

  // Site edit history
  interface HistoryChange { field: string; before: string | null; after: string | null }
  interface HistoryEntry { date: string; by: string; description: string; type: string; changes: HistoryChange[] }
  const [historyModal, setHistoryModal] = useState<{ siteId: string; siteName: string; history: HistoryEntry[] } | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)

  // Upload
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadParsed, setUploadParsed] = useState<ParsedSite[]>([])
  const [uploadFileName, setUploadFileName] = useState('')
  const [uploadTarget, setUploadTarget] = useState('ancient_nerds')
  const [uploading, setUploading] = useState(false)
  const [uploadMarkAudited, setUploadMarkAudited] = useState(false)
  const [uploadCreateSnapshot, setUploadCreateSnapshot] = useState(true)

  // Qdrant sync
  interface QdrantCollection { pg_count: number; qdrant_count: number; delta: number | null; note?: string }
  interface QdrantReindex { running: boolean; started_at: string | null; collection: string | null; last_completed_at: string | null; last_duration_seconds: number | null; last_result: string | null }
  interface QdrantEmpires { empire_count: number; boundary_count: number }
  interface QdrantStatus { qdrant_available: boolean; collections: { sites: QdrantCollection; news: QdrantCollection; transcripts: QdrantCollection; articles: QdrantCollection; empires: QdrantCollection }; empires: QdrantEmpires; reindex: QdrantReindex }
  const [qdrantStatus, setQdrantStatus] = useState<QdrantStatus | null>(null)
  const [qdrantOpen, setQdrantOpen] = useState(false)
  const qdrantRef = useRef<HTMLDivElement>(null)

  // Diff viewer
  const [showDiffModal, setShowDiffModal] = useState(false)
  const [diffData, setDiffData] = useState<DiffResponse | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffError, setDiffError] = useState('')
  const [diffFrom, setDiffFrom] = useState('')
  const [diffTo, setDiffTo] = useState('')
  const [expandedDiffRows, setExpandedDiffRows] = useState<Set<string>>(new Set())
  const [diffAddedExpanded, setDiffAddedExpanded] = useState(false)
  const [diffRemovedExpanded, setDiffRemovedExpanded] = useState(false)

  // Fetch snapshot manifest + active pins on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${config.api.baseUrl}/snapshots/?${CACHE_BUSTER}`)
        if (res.ok) {
          const data = await res.json()
          setSnapshots(data.snapshots || [])
        }
      } catch {
        // Snapshots are optional
      }
      try {
        const res = await fetch(`${config.api.baseUrl}/snapshots/pins?${CACHE_BUSTER}`)
        if (res.ok) {
          const data = await res.json()
          const pins: Record<string, string | null> = {}
          for (const [sid, info] of Object.entries(data.pins || {})) {
            pins[sid] = (info as { snapshot_date: string }).snapshot_date
          }
          setActivePins(pins)
        }
      } catch {
        // Pins are optional
      }
    })()
  }, [])

  // Fetch DB snapshots (undo history)
  const refreshDbSnapshots = useCallback(async () => {
    try {
      const url = sourceFilter !== 'all'
        ? `${config.api.baseUrl}/sites/snapshots?source_id=${sourceFilter}&${CACHE_BUSTER}`
        : `${config.api.baseUrl}/sites/snapshots?${CACHE_BUSTER}`
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        setDbSnapshots(data.snapshots || [])
      }
    } catch { /* optional */ }
  }, [sourceFilter])

  useEffect(() => { refreshDbSnapshots() }, [refreshDbSnapshots])

  // Fetch hero image status
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${config.api.baseUrl}/wiki-images/hero-status?${CACHE_BUSTER}`)
        if (res.ok) setHeroStatus(await res.json())
      } catch { /* hero status is optional */ }
    })()
  }, [])

  // Close hero popover on outside click
  useEffect(() => {
    if (!heroPopup) return
    const handler = (e: MouseEvent) => {
      if (heroPopoverRef.current && !heroPopoverRef.current.contains(e.target as Node)) {
        setHeroPopup(null)
        setHeroError('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [heroPopup])

  // Fetch sites (per-source: live or from snapshot)
  const hasFetched = useRef(false)
  useEffect(() => {
    (async () => {
      // Only show full-page spinner on initial load, not on snapshot switches
      if (!hasFetched.current) setLoading(true)
      setError('')
      try {
        const allSites: AuditSite[] = []

        // Group sources by their selected version to avoid duplicate snapshot fetches
        const byVersion: Record<string, string[]> = {}
        for (const [sid, ver] of Object.entries(sourceVersions)) {
          if (!byVersion[ver]) byVersion[ver] = []
          byVersion[ver].push(sid)
        }

        for (const [ver, sources] of Object.entries(byVersion)) {
          if (ver === 'latest') {
            // Fetch live from API
            const params = sources.map(s => `source=${s}`).join('&')
            const res = await fetch(`${config.api.baseUrl}/sites/all?${params}&limit=100000&${CACHE_BUSTER}`)
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const data = await res.json()
            allSites.push(...(data.sites || []))
          } else {
            // Fetch from snapshot, filter by source
            const res = await fetch(`${config.api.baseUrl}/snapshots/${ver}.json`)
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const data = await res.json()
            const snapSites = (data.sites || []) as AuditSite[]
            const sourceSet = new Set(sources)
            allSites.push(...snapSites.filter(s => sourceSet.has(s.s)))
          }
        }

        setSites(allSites)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load sites')
      } finally {
        if (!hasFetched.current) setLoading(false)
        hasFetched.current = true
      }
    })()
  }, [sourceVersions])

  // Poll for live updates every 30s (only sources set to 'latest')
  useEffect(() => {
    const liveSources = Object.entries(sourceVersions)
      .filter(([, ver]) => ver === 'latest')
      .map(([sid]) => sid)
    if (liveSources.length === 0) return

    const interval = setInterval(async () => {
      try {
        const params = liveSources.map(s => `source=${s}`).join('&')
        const res = await fetch(`${config.api.baseUrl}/sites/all?${params}&limit=100000&${CACHE_BUSTER}`)
        if (!res.ok) return
        const data = await res.json()
        const freshLive: AuditSite[] = data.sites || []
        // Replace only live-source sites, keep snapshot-sourced sites intact
        const liveSet = new Set(liveSources)
        setSites(prev => {
          const snapshotSites = prev.filter(s => !liveSet.has(s.s))
          const merged = [...snapshotSites, ...freshLive]
          // Check if anything actually changed
          if (merged.length !== prev.length) return merged
          const maxEa = (arr: AuditSite[]) => arr.reduce((max, s) => s.ea && s.ea > max ? s.ea : max, '')
          if (maxEa(freshLive) !== maxEa(prev.filter(s => liveSet.has(s.s)))) return merged
          return prev
        })
      } catch { /* silent — next poll will retry */ }
    }, 30_000)
    return () => clearInterval(interval)
  }, [sourceVersions])

  // ─── Qdrant sync widget ─────────────────────────────────────────────────────
  const refreshQdrantStatus = useCallback(async () => {
    try {
      const res = await fetch(`${config.api.baseUrl}/vector-sync/status`)
      if (res.ok) setQdrantStatus(await res.json())
    } catch { /* Qdrant status is optional */ }
  }, [])

  useEffect(() => {
    refreshQdrantStatus()
    const interval = setInterval(refreshQdrantStatus, qdrantStatus?.reindex.running ? 5_000 : 30_000)
    return () => clearInterval(interval)
  }, [refreshQdrantStatus, qdrantStatus?.reindex.running])

  // Close dropdown on outside click
  useEffect(() => {
    if (!qdrantOpen) return
    const handler = (e: MouseEvent) => {
      if (qdrantRef.current && !qdrantRef.current.contains(e.target as Node)) setQdrantOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [qdrantOpen])

  const handleReindex = async (collection?: string, rebuild?: boolean) => {
    if (!confirm(`Reindex ${collection || 'all'} vectors${rebuild ? ' (full rebuild)' : ''}?`)) return
    try {
      const res = await fetch(`${config.api.baseUrl}/vector-sync/reindex`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ collection: collection || null, rebuild: rebuild || false }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        alert(err.detail || 'Reindex failed')
        return
      }
      refreshQdrantStatus()
    } catch { alert('Failed to start reindex') }
  }

  // Compute stats (respect source filter)
  const stats = useMemo(() => {
    const base = sourceFilter !== 'all' ? sites.filter(s => s.s === sourceFilter) : sites
    const total = base.length
    const no_period = base.filter(hasPeriodIssue).length
    const no_type = base.filter(hasTypeIssue).length
    const no_country = base.filter(hasCountryIssue).length
    const suspect_modern = base.filter(isSuspectModern).length
    const no_desc = base.filter(hasDescIssue).length
    const no_source = base.filter(hasSourceIssue).length
    const no_image = base.filter(hasImageIssue).length
    const no_coords = base.filter(hasCoordsIssue).length
    return { total, no_period, no_type, no_country, suspect_modern, no_desc, no_source, no_image, no_coords }
  }, [sites, sourceFilter])

  // Unique filter values
  const uniqueTypes = useMemo(() =>
    Array.from(new Set(sites.map(s => s.t).filter(Boolean) as string[])).sort()
  , [sites])

  const uniqueCountries = useMemo(() =>
    Array.from(new Set(sites.map(s => s.c).filter(Boolean) as string[])).sort()
  , [sites])

  const uniquePeriods = useMemo(() =>
    Array.from(new Set(sites.map(s => resolvePeriod(s.pn, s.p)).filter(v => v && v !== 'Unknown')))
      .sort((a, b) => (PERIOD_ORDER[a] ?? 99) - (PERIOD_ORDER[b] ?? 99))
  , [sites])

  const uniqueEditedBy = useMemo(() =>
    Array.from(new Set(sites.map(s => s.eb || 'initial'))).sort()
  , [sites])

  // Are any filters active?
  const hasActiveFilters = activeIssue !== 'all' || typeFilters.size > 0 || countryFilters.size > 0 ||
    periodFilters.size > 0 || editedByFilters.size > 0 || searchQuery !== '' || sourceFilter !== 'all'

  const clearAllFilters = useCallback(() => {
    setActiveIssue('all')
    setTypeFilters(new Set())
    setCountryFilters(new Set())
    setPeriodFilters(new Set())
    setEditedByFilters(new Set())
    setSearchQuery('')
    setSourceFilter('all')
  }, [])

  // Filtered & sorted sites
  const filteredSites = useMemo(() => {
    let result = sites

    // Source filter
    if (sourceFilter !== 'all') result = result.filter(s => s.s === sourceFilter)

    // Issue filter
    if (activeIssue === 'no_period') result = result.filter(hasPeriodIssue)
    else if (activeIssue === 'no_type') result = result.filter(hasTypeIssue)
    else if (activeIssue === 'no_country') result = result.filter(hasCountryIssue)
    else if (activeIssue === 'suspect_modern') result = result.filter(isSuspectModern)
    else if (activeIssue === 'no_desc') result = result.filter(hasDescIssue)
    else if (activeIssue === 'no_source') result = result.filter(hasSourceIssue)
    else if (activeIssue === 'no_image') result = result.filter(hasImageIssue)
    else if (activeIssue === 'no_coords') result = result.filter(hasCoordsIssue)

    // Multi-select dropdown filters
    if (typeFilters.size > 0) result = result.filter(s => typeFilters.has(s.t || ''))
    if (countryFilters.size > 0) result = result.filter(s => countryFilters.has(s.c || ''))
    if (periodFilters.size > 0) result = result.filter(s => periodFilters.has(resolvePeriod(s.pn, s.p)))
    if (editedByFilters.size > 0) result = result.filter(s => editedByFilters.has(s.eb || 'initial'))

    // Search
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter(s => s.n.toLowerCase().includes(q))
    }

    // Sort
    result = [...result].sort((a, b) => {
      let cmp = 0
      switch (sortColumn) {
        case 'name': cmp = a.n.localeCompare(b.n); break
        case 'type': cmp = (a.t || '').localeCompare(b.t || ''); break
        case 'period': cmp = (PERIOD_ORDER[resolvePeriod(a.pn, a.p)] ?? 99) - (PERIOD_ORDER[resolvePeriod(b.pn, b.p)] ?? 99); break
        case 'country': cmp = (a.c || '').localeCompare(b.c || ''); break
        case 'edited_at': {
          const ta = a.ea ? new Date(a.ea).getTime() : 0
          const tb = b.ea ? new Date(b.ea).getTime() : 0
          cmp = ta - tb
          break
        }
        case 'audited': {
          const aa = a.aud ? new Date(a.aud).getTime() : 0
          const ab = b.aud ? new Date(b.aud).getTime() : 0
          cmp = aa - ab
          break
        }
      }
      return sortDir === 'asc' ? cmp : -cmp
    })

    return result
  }, [sites, sourceFilter, activeIssue, typeFilters, countryFilters, periodFilters, editedByFilters, searchQuery, sortColumn, sortDir])

  // Reset pagination when filters change
  useEffect(() => { setVisibleRows(ROWS_PER_PAGE) }, [filteredSites])

  const displayedSites = useMemo(() => filteredSites.slice(0, visibleRows), [filteredSites, visibleRows])
  const hasMore = visibleRows < filteredSites.length

  // Inline edit handlers
  const startInlineEdit = useCallback((site: AuditSite, field: 'type' | 'period' | 'country') => {
    setEditingCell({ id: site.id, field })
    if (field === 'type') setEditValue(site.t || '')
    else if (field === 'period') setEditValue(resolvePeriod(site.pn, site.p))
    else setEditValue(site.c || '')
  }, [])

  const commitInlineEdit = useCallback(() => {
    if (!editingCell) return
    const site = sites.find(s => s.id === editingCell.id)
    if (!site) return

    const { field } = editingCell
    const newType = field === 'type' ? editValue : (site.t || 'Unknown')
    const newPeriod = field === 'period' ? editValue : resolvePeriod(site.pn, site.p)

    // Build change record
    const changes: Record<string, { old: string; new: string }> = {}
    if (field === 'type') changes['Type'] = { old: site.t || 'Unknown', new: editValue }
    else if (field === 'period') changes['Period'] = { old: resolvePeriod(site.pn, site.p), new: editValue }
    else changes['Country'] = { old: site.c || '', new: editValue }

    // Merge with existing pending edit for this site
    const existing = pendingEdits.get(site.id)
    const merged = existing ? { ...existing.changes, ...changes } : changes

    const newCountry = field === 'country' ? editValue : (site.c || '')

    const edit: PendingEdit = {
      siteId: site.id,
      siteName: site.n,
      changes: merged,
      fullUpdate: {
        id: site.id,
        title: site.n,
        description: site.d,
        category: newType,
        period: newPeriod,
        coordinates: [site.lo, site.la],
        sourceUrl: site.u,
        country: newCountry,
      },
    }

    setPendingEdits(prev => new Map(prev).set(site.id, edit))

    // Update local state optimistically
    setSites(prev => prev.map(s => {
      if (s.id !== site.id) return s
      const updated = { ...s }
      if (field === 'type') updated.t = editValue
      else if (field === 'period') updated.pn = editValue
      else updated.c = editValue
      return updated
    }))
    setEditingCell(null)
  }, [editingCell, editValue, sites, pendingEdits])

  const cancelInlineEdit = useCallback(() => setEditingCell(null), [])

  // Modal edit handlers
  const openEditModal = useCallback((site: AuditSite) => {
    setEditModalSite(site)
    setModalFormValues(null)
  }, [])

  const saveModal = useCallback(() => {
    if (!editModalSite || !modalFormValues) return
    const coords = modalFormValues.validCoords
    const lat = coords ? coords[1] : editModalSite.la
    const lon = coords ? coords[0] : editModalSite.lo

    // Build change record
    const changes: Record<string, { old: string; new: string }> = {}
    if (modalFormValues.name !== editModalSite.n) changes['Name'] = { old: editModalSite.n, new: modalFormValues.name }
    if (modalFormValues.category !== (editModalSite.t || '')) changes['Type'] = { old: editModalSite.t || '', new: modalFormValues.category }
    if (modalFormValues.period !== resolvePeriod(editModalSite.pn, editModalSite.p)) changes['Period'] = { old: resolvePeriod(editModalSite.pn, editModalSite.p), new: modalFormValues.period }
    if (modalFormValues.description !== (editModalSite.d || '')) changes['Description'] = { old: (editModalSite.d || '').slice(0, 50), new: modalFormValues.description.slice(0, 50) }
    if (lat !== editModalSite.la || lon !== editModalSite.lo) changes['Coords'] = { old: `${editModalSite.la}, ${editModalSite.lo}`, new: `${lat}, ${lon}` }
    if (modalFormValues.sourceUrl !== (editModalSite.u || '')) changes['Source URL'] = { old: editModalSite.u || '', new: modalFormValues.sourceUrl }
    if (modalFormValues.country !== (editModalSite.c || '')) changes['Country'] = { old: editModalSite.c || '', new: modalFormValues.country }

    if (Object.keys(changes).length === 0) { setEditModalSite(null); return }

    const edit: PendingEdit = {
      siteId: editModalSite.id,
      siteName: modalFormValues.name,
      changes,
      fullUpdate: {
        id: editModalSite.id,
        title: modalFormValues.name,
        description: modalFormValues.description,
        category: modalFormValues.category,
        period: modalFormValues.period,
        coordinates: [lon, lat],
        sourceUrl: modalFormValues.sourceUrl,
        country: modalFormValues.country,
      },
    }

    setPendingEdits(prev => new Map(prev).set(editModalSite.id, edit))

    // Update local state optimistically
    setSites(prev => prev.map(s => {
      if (s.id !== editModalSite.id) return s
      return {
        ...s,
        n: modalFormValues.name,
        d: modalFormValues.description || undefined,
        la: lat,
        lo: lon,
        t: modalFormValues.category || undefined,
        pn: modalFormValues.period,
        c: modalFormValues.country || undefined,
        u: modalFormValues.sourceUrl || undefined,
      }
    }))
    setEditModalSite(null)
  }, [editModalSite, modalFormValues])

  // Sort handler
  const handleSort = useCallback((col: SortColumn) => {
    if (sortColumn === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortColumn(col); setSortDir(col === 'edited_at' || col === 'audited' ? 'desc' : 'asc') }
  }, [sortColumn])

  const sortArrow = (col: SortColumn) =>
    sortColumn === col ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : ''

  // Toggle expanded description
  const toggleExpand = useCallback((id: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // Export handlers
  const handleExportCSV = useCallback(() => exportCSV(filteredSites), [filteredSites])
  const handleExportJSON = useCallback(() => exportJSON(filteredSites), [filteredSites])
  const handleExportGeoJSON = useCallback(() => exportGeoJSON(filteredSites), [filteredSites])

  // Discard all pending edits — reload from server
  const discardAllEdits = useCallback(() => {
    if (!confirm(`Discard ${pendingEdits.size} pending change${pendingEdits.size !== 1 ? 's' : ''}? This cannot be undone.`)) return
    setPendingEdits(new Map())
    // Force re-fetch by toggling sourceVersions identity
    setSourceVersions(v => ({ ...v }))
  }, [pendingEdits.size])

  // Pin/unpin a source to a snapshot version
  const handleSetPin = useCallback(async (sourceId: string, snapDate: string | null) => {
    if (!token) return
    const action = snapDate ? `Pin ${sourceId} to ${snapDate}?` : `Unpin ${sourceId} to live?`
    if (!confirm(`${action}\n\nThis affects the public globe — all visitors will see this version.`)) return
    setPinLoading(sourceId)
    try {
      const res = await fetch(`${config.api.baseUrl}/snapshots/pins/${sourceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ snapshot_date: snapDate }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      // Update local pins state
      setActivePins(prev => {
        const next = { ...prev }
        if (snapDate) next[sourceId] = snapDate
        else delete next[sourceId]
        return next
      })
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Pin failed')
    } finally {
      setPinLoading(null)
    }
  }, [token])

  // Commit all pending edits via batch-update
  const commitAllEdits = useCallback(async () => {
    if (!token || pendingEdits.size === 0) return
    setCommitting(true)
    try {
      const updates = Array.from(pendingEdits.values()).map(e => e.fullUpdate)
      const res = await fetch(`${config.api.baseUrl}/sites/batch-update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(updates),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const result = await res.json()
      const now = new Date().toISOString()
      // Mark committed sites with edit tracking
      setSites(prev => prev.map(s => {
        if (!pendingEdits.has(s.id)) return s
        return { ...s, eb: 'audit', ea: now }
      }))
      setPendingEdits(new Map())
      setShowReviewModal(false)
      refreshDbSnapshots()
      alert(`Committed ${result.updated} edits. Snapshot: ${result.snapshot_id?.slice(0, 8)}`)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Commit failed')
    } finally {
      setCommitting(false)
    }
  }, [token, pendingEdits, refreshDbSnapshots])

  // Upload file handler
  // Shared file processing for both input and drag & drop
  const processUploadFile = useCallback((file: File) => {
    setUploadFileName(file.name)
    const reader = new FileReader()
    reader.onload = () => {
      const text = reader.result as string
      let parsed: ParsedSite[] = []
      if (file.name.endsWith('.csv')) parsed = parseCSV(text)
      else if (file.name.endsWith('.geojson')) parsed = parseGeoJSON(text)
      else parsed = parseJSON(text)

      // Match against existing sites by name, store current data for diff
      const nameIndex = new Map(sites.map(s => [s.n.toLowerCase(), s]))
      for (const p of parsed) {
        const existing = nameIndex.get(p.name.toLowerCase())
        if (existing) {
          p._status = 'update'
          p._matchedId = existing.id
          p._currentData = {
            name: existing.n,
            site_type: existing.t,
            period_name: existing.pn,
            period_start: existing.p,
            country: existing.c,
            description: existing.d,
            source_url: existing.u,
          }
          // Compute which fields actually changed
          const changed: string[] = []
          if ((p.site_type || '') !== (existing.t || '')) changed.push('site_type')
          if ((p.period_name || '') !== (existing.pn || '')) changed.push('period_name')
          if ((p.period_start ?? null) !== (existing.p ?? null)) changed.push('period_start')
          if ((p.country || '') !== (existing.c || '')) changed.push('country')
          if ((p.description || '') !== (existing.d || '')) changed.push('description')
          if ((p.source_url || '') !== (existing.u || '')) changed.push('source_url')
          p._changedFields = changed
        } else if (!p._status) {
          p._status = 'insert'
        }
      }
      setUploadParsed(parsed)
    }
    reader.readAsText(file)
  }, [sites])

  const handleUploadFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    processUploadFile(file)
  }, [processUploadFile])

  const [uploadDragOver, setUploadDragOver] = useState(false)
  const handleUploadDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setUploadDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (!['csv', 'json', 'geojson'].includes(ext || '')) return
    processUploadFile(file)
  }, [processUploadFile])

  // Commit upload
  const commitUpload = useCallback(async () => {
    if (!token || uploadParsed.length === 0) return
    setUploading(true)
    try {
      const payload = uploadParsed
        .filter(p => p._status !== 'error')
        .map(p => ({
          name: p.name, lat: p.lat, lon: p.lon,
          site_type: p.site_type || null,
          period_name: p.period_name || null,
          period_start: p.period_start ?? null,
          country: p.country || null,
          description: p.description || null,
          source_url: p.source_url || null,
          thumbnail_url: p.thumbnail_url || null,
          existing_id: p._matchedId || null,
        }))
      const res = await fetch(`${config.api.baseUrl}/sites/batch-upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ sites: payload, target_source: uploadTarget, create_snapshot: uploadCreateSnapshot }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const result = await res.json()

      // Mark all sites in this source as audited if checkbox was checked
      let auditedCount = 0
      if (uploadMarkAudited) {
        const auditRes = await fetch(`${config.api.baseUrl}/sites/mark-audited`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ source_id: uploadTarget }),
        })
        if (auditRes.ok) {
          const auditResult = await auditRes.json()
          auditedCount = auditResult.marked
        }
      }

      setShowUploadModal(false)
      setUploadParsed([])
      setUploadFileName('')
      setUploadMarkAudited(false)
      setUploadCreateSnapshot(true)
      refreshDbSnapshots()
      const msg = `Upload complete: ${result.inserted} inserted, ${result.updated} updated` +
        (auditedCount > 0 ? `\n${auditedCount} sites marked as audited` : '')
      alert(msg)
      // Re-fetch sites
      discardAllEdits()
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [token, uploadParsed, uploadTarget, uploadMarkAudited, refreshDbSnapshots, discardAllEdits])

  // Fetch edit history for a site
  const fetchSiteHistory = useCallback(async (siteId: string, siteName: string) => {
    setHistoryLoading(true)
    try {
      const res = await fetch(`${config.api.baseUrl}/sites/${siteId}/history?${CACHE_BUSTER}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setHistoryModal({ siteId, siteName, history: data.history || [] })
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to load history')
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const previewDbSnapshot = useCallback(async (snapshotId: string) => {
    setSnapshotPreviewLoading(true)
    try {
      const res = await fetch(`${config.api.baseUrl}/sites/snapshots/${snapshotId}/preview?${CACHE_BUSTER}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setSnapshotPreview(data)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Preview failed')
    } finally {
      setSnapshotPreviewLoading(false)
    }
  }, [])

  // Restore a DB snapshot (called from preview modal only)
  const restoreDbSnapshot = useCallback(async (snapshotId: string) => {
    if (!token) return
    try {
      const res = await fetch(`${config.api.baseUrl}/sites/snapshots/${snapshotId}/restore`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      setSnapshotPreview(null)
      discardAllEdits()
      refreshDbSnapshots()
    } catch (e: unknown) {
      setSnapshotPreview(null)
      alert(e instanceof Error ? e.message : 'Restore failed')
    }
  }, [token, discardAllEdits, refreshDbSnapshots])

  // Diff: open compare modal with defaults
  const openDiffModal = useCallback(() => {
    if (snapshots.length < 2) return
    setDiffFrom(snapshots[1].date) // second most recent
    setDiffTo(snapshots[0].date)   // most recent
    setDiffData(null)
    setDiffError('')
    setExpandedDiffRows(new Set())
    setDiffAddedExpanded(false)
    setDiffRemovedExpanded(false)
    setShowDiffModal(true)
  }, [snapshots])

  // Diff: fetch comparison data
  const fetchDiff = useCallback(async () => {
    if (!diffFrom || !diffTo) return
    setDiffLoading(true)
    setDiffError('')
    try {
      const res = await fetch(`${config.api.baseUrl}/snapshots/diff?from=${diffFrom}&to=${diffTo}`)
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const data: DiffResponse = await res.json()
      setDiffData(data)
      setExpandedDiffRows(new Set())
      setDiffAddedExpanded(false)
      setDiffRemovedExpanded(false)
    } catch (e: unknown) {
      setDiffError(e instanceof Error ? e.message : 'Failed to load diff')
    } finally {
      setDiffLoading(false)
    }
  }, [diffFrom, diffTo])

  // Toggle a changed row's expansion
  const toggleDiffRow = useCallback((id: string) => {
    setExpandedDiffRows(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // Open site popup
  const openPopup = useCallback((s: AuditSite) => {
    setPopupSite({
      id: s.id,
      title: s.n,
      location: s.c || '',
      category: s.t || '',
      period: s.pn || '',
      periodStart: s.p ?? null,
      description: s.d || '',
      image: s.i || undefined,
      sourceUrl: s.u || undefined,
      sourceId: s.s,
      coordinates: [s.lo, s.la],
    })
  }, [])

  // Set hero image handler
  const handleSetHero = useCallback(async () => {
    if (!heroPopup || !token || !heroImageUrl) return
    setHeroSaving(true)
    setHeroError('')
    try {
      const res = await fetch(`${config.api.baseUrl}/wiki-images/${heroPopup.siteId}/set-hero`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ image_url: heroImageUrl, attribution_url: heroAttrUrl }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      const sid = heroPopup.siteId
      setHeroStatus(prev => ({ ...prev, [sid]: { path: data.path, original_url: heroImageUrl, attribution_url: heroAttrUrl } }))
      setHeroPopup(null)
      setHeroImageUrl('')
      setHeroAttrUrl('')
      setHeroError('')
    } catch (e: unknown) {
      setHeroError(e instanceof Error ? e.message : 'Failed to set hero')
    } finally {
      setHeroSaving(false)
    }
  }, [heroPopup, token, heroImageUrl, heroAttrUrl])

  const openHeroPopup = useCallback((siteId: string, e: React.MouseEvent<HTMLTableCellElement>) => {
    if (!isFounder) return
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setHeroPopup({ siteId, rect })
    const existing = heroStatus[siteId]
    setHeroImageUrl(existing?.original_url || '')
    setHeroAttrUrl(existing?.attribution_url || '')
    setHeroError('')
  }, [isFounder, heroStatus])

  if (loading) {
    return (
      <div className="db-page">
        <div className="db-loading">Loading sites...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="db-page">
        <div className="db-error">{error}</div>
      </div>
    )
  }

  return (
    <div className="db-page">
      {/* Header */}
      <PageHeader
        hideLyra
        currentPage="db"
        rightSection={
        <>
          {/* Qdrant sync widget */}
          {qdrantStatus && (
            <div className="db-qdrant-widget" ref={qdrantRef}>
              <button
                className={`db-qdrant-pill ${
                  qdrantStatus.reindex.running ? 'db-qdrant-indexing' :
                  !qdrantStatus.qdrant_available ? 'db-qdrant-offline' :
                  (qdrantStatus.collections.sites.delta !== 0 || qdrantStatus.collections.news.delta !== 0 || (qdrantStatus.collections.empires.delta != null && qdrantStatus.collections.empires.delta !== 0) || (qdrantStatus.collections.transcripts.qdrant_count === 0 && qdrantStatus.collections.transcripts.pg_count > 0) || (qdrantStatus.collections.articles.qdrant_count === 0 && qdrantStatus.collections.articles.pg_count > 0)) ? 'db-qdrant-stale' :
                  'db-qdrant-ok'
                }`}
                onClick={() => setQdrantOpen(o => !o)}
              >
                {qdrantStatus.reindex.running
                  ? <span className="db-qdrant-spinner" />
                  : <span className="db-qdrant-dot" />}
                <span>Qdrant: {
                  qdrantStatus.reindex.running ? 'indexing...' :
                  !qdrantStatus.qdrant_available ? 'offline' :
                  (() => {
                    const chunkedDelta = (['transcripts', 'articles'] as const).reduce((sum, col) => {
                      const cc = qdrantStatus.collections[col]
                      return sum + (cc.qdrant_count === 0 && cc.pg_count > 0 ? cc.pg_count : 0)
                    }, 0)
                    const comparableDeltas = [qdrantStatus.collections.sites.delta, qdrantStatus.collections.news.delta, qdrantStatus.collections.empires.delta].filter((d): d is number => d != null)
                    const totalDelta = comparableDeltas.reduce((a, b) => a + b, 0) + chunkedDelta
                    return totalDelta === 0 ? 'OK' : `${totalDelta > 0 ? '-' : '+'}${Math.abs(totalDelta)}`
                  })()
                }</span>
              </button>
              {qdrantOpen && (
                <div className="db-qdrant-dropdown">
                  <div className="db-qdrant-section-title">Collection Counts</div>
                  {(['sites', 'news', 'transcripts', 'articles', 'empires'] as const).map(col => {
                    const c = qdrantStatus.collections[col]
                    const isChunked = !!c.note
                    const chunkedDelta = c.qdrant_count === 0 && c.pg_count > 0 ? c.pg_count : 0
                    return (
                      <div key={col} className="db-qdrant-row">
                        <span className="db-qdrant-col-name">{col}</span>
                        {isChunked ? (
                          <>
                            <span className="db-qdrant-counts">
                              <span title="Sources">{c.pg_count.toLocaleString()}</span>
                            </span>
                            {c.qdrant_count > 0 ? (
                              <span className="db-qdrant-note" title={c.note!}>{c.qdrant_count.toLocaleString()} chunks</span>
                            ) : chunkedDelta > 0 ? (
                              <span className="db-qdrant-delta stale">-{chunkedDelta.toLocaleString()}</span>
                            ) : null}
                          </>
                        ) : (
                          <>
                            <span className="db-qdrant-counts">
                              <span title="Qdrant">{c.qdrant_count.toLocaleString()}</span>
                              <span className="db-qdrant-sep">/</span>
                              <span title="PostgreSQL">{c.pg_count.toLocaleString()}</span>
                            </span>
                            {c.delta != null && c.delta !== 0 && (
                              <span className={`db-qdrant-delta ${c.delta > 0 ? 'stale' : 'over'}`}>
                                {c.delta > 0 ? `-${c.delta.toLocaleString()}` : `+${Math.abs(c.delta).toLocaleString()}`}
                              </span>
                            )}
                          </>
                        )}
                      </div>
                    )
                  })}
                  {qdrantStatus.empires && qdrantStatus.empires.empire_count > 0 && (
                    <div className="db-qdrant-row">
                      <span className="db-qdrant-col-name">empires</span>
                      <span className="db-qdrant-counts">
                        <span title="Empires">{qdrantStatus.empires.empire_count}</span>
                        <span className="db-qdrant-sep">/</span>
                        <span title="Boundary snapshots">{qdrantStatus.empires.boundary_count.toLocaleString()}</span>
                      </span>
                    </div>
                  )}
                  {qdrantStatus.reindex.last_completed_at && (
                    <div className="db-qdrant-meta">
                      Last indexed {formatRelativeDate(qdrantStatus.reindex.last_completed_at)}
                      {qdrantStatus.reindex.last_duration_seconds != null && ` (${qdrantStatus.reindex.last_duration_seconds}s)`}
                      {qdrantStatus.reindex.last_result && qdrantStatus.reindex.last_result !== 'success' && (
                        <span className="db-qdrant-fail"> — {qdrantStatus.reindex.last_result}</span>
                      )}
                    </div>
                  )}
                  {qdrantStatus.reindex.running && (
                    <div className="db-qdrant-meta">
                      Indexing {qdrantStatus.reindex.collection}
                      {qdrantStatus.reindex.started_at && ` — started ${formatRelativeDate(qdrantStatus.reindex.started_at)}`}
                    </div>
                  )}
                  {isFounder && !qdrantStatus.reindex.running && (
                    <div className="db-qdrant-actions">
                      <button onClick={() => handleReindex()}>Reindex All</button>
                      <button onClick={() => handleReindex('sites')}>Sites</button>
                      <button onClick={() => handleReindex('news')}>News</button>
                      <button onClick={() => handleReindex('transcripts')}>Transcripts</button>
                      <button onClick={() => handleReindex('articles')}>Articles</button>
                      <button onClick={() => handleReindex('empires')}>Empires</button>
                      <button onClick={() => handleReindex(undefined, true)}>Rebuild All</button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {isFounder && (
            <button className="db-upload-btn" onClick={() => setShowUploadModal(true)}>
              Upload
            </button>
          )}
          {isFounder ? (
            <span className="db-auth-badge db-auth-unlocked">Founder</span>
          ) : user ? (
            <span className="db-auth-badge">View Only</span>
          ) : (
            <a className="db-unlock-btn" href={`${config.api.baseUrl}/auth/discord?return_to=${encodeURIComponent(window.location.pathname + window.location.search)}`}>
              Sign in
            </a>
          )}
        </>
      }>
        <span className="page-header-title">Database Audit</span>
        <div className="db-source-badge" style={sourceFilter !== 'all' ? {
          borderColor: SOURCE_CONFIG[sourceFilter]?.color,
          background: SOURCE_CONFIG[sourceFilter]?.color + '15',
        } : undefined}>
          <span className="db-source-dot" style={{
            background: sourceFilter !== 'all' ? SOURCE_CONFIG[sourceFilter]?.color : 'var(--text-secondary)'
          }} />
          <select value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}>
            <option value="all">All Databases</option>
            {Object.entries(SOURCE_CONFIG).map(([id, cfg]) => (
              <option key={id} value={id}>{cfg.name}</option>
            ))}
          </select>
        </div>
        {snapshots.length >= 2 && (
          <button className="db-compare-btn" onClick={openDiffModal}>Compare</button>
        )}
      </PageHeader>

      {/* Snapshot version panel — only when a specific source is selected */}
      {snapshots.length > 0 && sourceFilter !== 'all' && (
        <div className="db-version-panel">
          <div className="db-version-panel-header">
            <span className="db-version-panel-label">Database Snapshots</span>
            <span className="db-version-panel-count">{snapshots.length} snapshot{snapshots.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="db-version-cards">
            {/* Live card */}
            <div
              className={`db-version-card ${Object.values(sourceVersions).every(v => v === 'latest') ? 'active' : ''}`}
              onClick={() => setSourceVersions({ ancient_nerds: 'latest', lyra: 'latest', ancient_nerds_community: 'latest' })}
            >
              <div className="db-version-card-top">
                <span className="db-version-card-badge db-version-live">LIVE</span>
                <span className="db-version-card-title">Latest (live database)</span>
              </div>
              <div className="db-version-card-meta">Real-time data from PostgreSQL</div>
            </div>
            {/* Snapshot cards */}
            {snapshots.map(s => {
              const parts = s.date.split('_')
              const d = new Date(parts[0] + 'T' + (parts[1] ? `${parts[1].slice(0,2)}:${parts[1].slice(2,4)}:${parts[1].slice(4,6)}Z` : '00:00:00Z'))
              const dateStr = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
              const timeStr = parts[1] ? d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : ''
              const isActive = Object.values(sourceVersions).some(v => v === s.date)
              const isPinned = Object.values(activePins).some(p => p === s.date)
              const sourceSummary = Object.entries(s.by_source || {})
                .filter(([, count]) => count > 0)
                .map(([sid, count]) => `${SOURCE_CONFIG[sid]?.abbr || sid}: ${count.toLocaleString()}`)
                .join(' / ')

              return (
                <div
                  key={s.date}
                  className={`db-version-card ${isActive ? 'active' : ''}`}
                  onClick={() => setSourceVersions({ ancient_nerds: s.date, lyra: s.date, ancient_nerds_community: s.date })}
                  title={`Snapshot from ${d.toISOString()}`}
                >
                  <div className="db-version-card-top">
                    {isPinned && <span className="db-version-card-badge db-version-pinned">PUBLIC</span>}
                    <span className="db-version-card-title">{dateStr} {timeStr}</span>
                    <span className="db-version-card-ago">{formatRelativeDate(d.toISOString())}</span>
                  </div>
                  <div className="db-version-card-meta">
                    {s.sites.toLocaleString()} sites{sourceSummary ? ` (${sourceSummary})` : ''}
                  </div>
                  {isActive && isFounder && (
                    <div className="db-version-card-actions" onClick={e => e.stopPropagation()}>
                      {isPinned ? (
                        <button className="db-pin-btn db-pin-btn-active" onClick={() => { for (const sid of Object.keys(SOURCE_CONFIG)) handleSetPin(sid, null) }} disabled={pinLoading != null}>
                          {pinLoading ? '...' : 'Unpin'}
                        </button>
                      ) : (
                        <button className="db-pin-btn" onClick={() => { for (const sid of Object.keys(SOURCE_CONFIG)) handleSetPin(sid, s.date) }} disabled={pinLoading != null}>
                          {pinLoading ? '...' : 'Set as Public'}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="db-stats">
        <button
          className={`db-stat-card ${activeIssue === 'all' ? 'active' : ''}`}
          onClick={() => setActiveIssue('all')}
        >
          <span className="db-stat-value">{stats.total}</span>
          <span className="db-stat-label">Total</span>
        </button>
        <button
          className={`db-stat-card issue ${activeIssue === 'no_period' ? 'active' : ''}`}
          onClick={() => setActiveIssue(activeIssue === 'no_period' ? 'all' : 'no_period')}
        >
          <span className="db-stat-value">{stats.no_period}</span>
          <span className="db-stat-label">No Period</span>
        </button>
        <button
          className={`db-stat-card issue ${activeIssue === 'no_type' ? 'active' : ''}`}
          onClick={() => setActiveIssue(activeIssue === 'no_type' ? 'all' : 'no_type')}
        >
          <span className="db-stat-value">{stats.no_type}</span>
          <span className="db-stat-label">No Type</span>
        </button>
        <button
          className={`db-stat-card issue ${activeIssue === 'no_country' ? 'active' : ''}`}
          onClick={() => setActiveIssue(activeIssue === 'no_country' ? 'all' : 'no_country')}
        >
          <span className="db-stat-value">{stats.no_country}</span>
          <span className="db-stat-label">No Country</span>
        </button>
        <button
          className={`db-stat-card issue ${activeIssue === 'suspect_modern' ? 'active' : ''}`}
          onClick={() => setActiveIssue(activeIssue === 'suspect_modern' ? 'all' : 'suspect_modern')}
        >
          <span className="db-stat-value">{stats.suspect_modern}</span>
          <span className="db-stat-label">Suspect Modern</span>
        </button>
        <button
          className={`db-stat-card issue ${activeIssue === 'no_desc' ? 'active' : ''}`}
          onClick={() => setActiveIssue(activeIssue === 'no_desc' ? 'all' : 'no_desc')}
        >
          <span className="db-stat-value">{stats.no_desc}</span>
          <span className="db-stat-label">No Desc</span>
        </button>
        <button
          className={`db-stat-card issue ${activeIssue === 'no_source' ? 'active' : ''}`}
          onClick={() => setActiveIssue(activeIssue === 'no_source' ? 'all' : 'no_source')}
        >
          <span className="db-stat-value">{stats.no_source}</span>
          <span className="db-stat-label">No Source URL</span>
        </button>
        <button
          className={`db-stat-card issue ${activeIssue === 'no_image' ? 'active' : ''}`}
          onClick={() => setActiveIssue(activeIssue === 'no_image' ? 'all' : 'no_image')}
        >
          <span className="db-stat-value">{stats.no_image}</span>
          <span className="db-stat-label">No Image</span>
        </button>
        <button
          className={`db-stat-card issue ${activeIssue === 'no_coords' ? 'active' : ''}`}
          onClick={() => setActiveIssue(activeIssue === 'no_coords' ? 'all' : 'no_coords')}
        >
          <span className="db-stat-value">{stats.no_coords}</span>
          <span className="db-stat-label">No Coords</span>
        </button>
      </div>

      {/* Filters */}
      <div className="db-filters">
        <MultiSelect
          label="Type"
          options={uniqueTypes}
          selected={typeFilters}
          onChange={setTypeFilters}
          colorFn={v => getCategoryColor(v)}
        />
        <MultiSelect
          label="Country"
          options={uniqueCountries}
          selected={countryFilters}
          onChange={setCountryFilters}
        />
        <MultiSelect
          label="Period"
          options={uniquePeriods}
          selected={periodFilters}
          onChange={setPeriodFilters}
          colorFn={v => getPeriodColor(v)}
        />
        <MultiSelect
          label="Edited By"
          options={uniqueEditedBy}
          selected={editedByFilters}
          onChange={setEditedByFilters}
        />
        <div className="db-filter-group">
          <div className="db-search-wrap">
            <input
              type="text"
              placeholder="Search by name..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="db-search-clear" onClick={() => setSearchQuery('')}>&times;</button>
            )}
          </div>
        </div>
        <div className="db-filter-right">
          <div className="db-export-group">
            <button className="db-export-btn" onClick={handleExportCSV}>CSV</button>
            <button className="db-export-btn" onClick={handleExportJSON}>JSON</button>
            <button className="db-export-btn" onClick={handleExportGeoJSON}>GeoJSON</button>
          </div>
          {hasActiveFilters && (
            <button className="db-clear-filters" onClick={clearAllFilters}>
              Clear All
            </button>
          )}
          <span className="db-filter-count">{filteredSites.length} sites</span>
        </div>
      </div>

      {/* Table */}
      <div className="db-table-wrap">
        <table className="db-table">
          <thead>
            <tr>
              <th className="db-th" onClick={() => handleSort('name')}>Name{sortArrow('name')}</th>
              <th className="db-th db-th-nosort">Coords</th>
              <th className="db-th" onClick={() => handleSort('type')}>Category{sortArrow('type')}</th>
              <th className="db-th" onClick={() => handleSort('period')}>Period{sortArrow('period')}</th>
              <th className="db-th" onClick={() => handleSort('country')}>Country{sortArrow('country')}</th>
              <th className="db-th db-th-nosort" title="Game card description (200 chars)">Card</th>
              <th className="db-th db-th-nosort" title="Full Wikipedia description">Desc</th>
              <th className="db-th db-th-nosort" title="Source URL (Wikipedia, etc.)">URL</th>
              <th className="db-th db-th-nosort db-th-hero" title="Hero image status">H</th>
              <th className="db-th db-th-nosort" title="Last edited by (user or initial import)">User</th>
              <th className="db-th db-th-nosort db-th-db" title="Source database">DB</th>
              <th className="db-th" onClick={() => handleSort('audited')} title="Audit status — green check means audited">Aud{sortArrow('audited')}</th>
              <th className="db-th" onClick={() => handleSort('edited_at')}>Last Edited{sortArrow('edited_at')}</th>
              <th className="db-th db-th-nosort db-th-id" title="Site UUID — click to copy">ID</th>
              {isFounder && <th className="db-th db-th-edit">Edit</th>}
            </tr>
          </thead>
          <tbody>
            {displayedSites.map(site => {
              const period = resolvePeriod(site.pn, site.p)
              const isEditingType = editingCell?.id === site.id && editingCell.field === 'type'
              const isEditingPeriod = editingCell?.id === site.id && editingCell.field === 'period'
              const isEditingCountry = editingCell?.id === site.id && editingCell.field === 'country'
              const flagUrl = site.c ? getCountryFlatFlagUrl(site.c) : null

              const isPending = pendingEdits.has(site.id)
              const srcCfg = SOURCE_CONFIG[site.s]

              return (
                <tr key={site.id} className={`db-row ${isPending ? 'db-row-pending' : ''}`}>
                  {/* Name */}
                  <td className="db-td db-td-name">
                    <div className="db-td-flex">
                      <span className="db-name-link" onClick={() => openPopup(site)} title="Show popup">{site.n}</span>
                      <CopyButton text={site.n} title="Copy name" size={11} />
                    </div>
                  </td>

                  {/* Coordinates */}
                  <td className="db-td db-td-coords">
                    <div className="db-td-flex">
                      <span className="db-coords-link" onClick={() => viewOnGlobe(site.id)} title="View on globe">{site.la.toFixed(4)}, {site.lo.toFixed(4)}</span>
                      <CopyButton text={`${site.la.toFixed(4)}, ${site.lo.toFixed(4)}`} title="Copy coordinates" size={11} />
                    </div>
                  </td>

                  {/* Type cell */}
                  <td
                    className={`db-td db-td-editable ${isEditingType ? 'editing' : ''}`}
                    onClick={() => !isEditingType && isFounder && startInlineEdit(site, 'type')}
                  >
                    {isEditingType ? (
                      <select
                        className="db-inline-select"
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        onBlur={commitInlineEdit}
                        onKeyDown={e => { if (e.key === 'Escape') cancelInlineEdit(); if (e.key === 'Enter') commitInlineEdit() }}
                        autoFocus
                      >
                        <option value="">-- none --</option>
                        {CATEGORY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    ) : site.t ? (
                      <MetadataBadge label={site.t} color={getCategoryColor(site.t)} size="sm" />
                    ) : (
                      <span className="db-badge missing">MISSING</span>
                    )}
                  </td>

                  {/* Period cell */}
                  <td
                    className={`db-td db-td-editable ${isEditingPeriod ? 'editing' : ''}`}
                    onClick={() => !isEditingPeriod && isFounder && startInlineEdit(site, 'period')}
                  >
                    {isEditingPeriod ? (
                      <select
                        className="db-inline-select"
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        onBlur={commitInlineEdit}
                        onKeyDown={e => { if (e.key === 'Escape') cancelInlineEdit(); if (e.key === 'Enter') commitInlineEdit() }}
                        autoFocus
                      >
                        <option value="Unknown">Unknown</option>
                        {SORTED_PERIODS.filter(p => p !== 'Unknown').map(p => <option key={p} value={p}>{p}</option>)}
                      </select>
                    ) : !hasPeriodIssue(site) ? (
                      <MetadataBadge label={period} color={getPeriodColor(period)} size="sm" />
                    ) : (
                      <span className="db-badge missing">{period}</span>
                    )}
                  </td>

                  {/* Country cell */}
                  <td
                    className={`db-td db-td-country db-td-editable ${isEditingCountry ? 'editing' : ''}`}
                    onClick={() => !isEditingCountry && isFounder && startInlineEdit(site, 'country')}
                  >
                    {isEditingCountry ? (
                      <input
                        className="db-inline-input"
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        onBlur={commitInlineEdit}
                        onKeyDown={e => { if (e.key === 'Escape') cancelInlineEdit(); if (e.key === 'Enter') commitInlineEdit() }}
                        autoFocus
                      />
                    ) : site.c ? (
                      <>
                        {flagUrl && <img src={flagUrl} className="db-flag" alt="" />}
                        <span>{site.c}</span>
                      </>
                    ) : (
                      <span className="db-missing">MISSING</span>
                    )}
                  </td>

                  {/* Card Description */}
                  <td className="db-td db-td-card-desc">
                    {site.cd ? (
                      expandedRows.has('cd-' + site.id) ? (
                        <span className="db-desc-full" onClick={() => toggleExpand('cd-' + site.id)}>{site.cd}</span>
                      ) : (
                        <span className="db-desc-truncated db-card-desc-text" onClick={() => toggleExpand('cd-' + site.id)}>
                          {site.cd.length > 40 ? site.cd.slice(0, 40) + '\u2026' : site.cd}
                        </span>
                      )
                    ) : <span className="db-missing">&mdash;</span>}
                  </td>

                  {/* Description */}
                  <td className="db-td db-td-desc">
                    {site.d ? (
                      expandedRows.has(site.id) ? (
                        <span className="db-desc-full" onClick={() => toggleExpand(site.id)}>{site.d}</span>
                      ) : (
                        <span className="db-desc-truncated" onClick={() => toggleExpand(site.id)}>
                          {site.d.length > 40 ? site.d.slice(0, 40) + '\u2026' : site.d}
                        </span>
                      )
                    ) : <span className="db-missing">&mdash;</span>}
                  </td>

                  {/* URL */}
                  <td className="db-td db-td-url">
                    {site.u ? (
                      <a href={site.u} target="_blank" rel="noopener noreferrer" className="db-link-icon" title={site.u}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </a>
                    ) : <span className="db-missing">&mdash;</span>}
                  </td>

                  {/* Hero status */}
                  <td
                    className={`db-td db-td-hero ${isFounder ? 'db-td-hero-clickable' : ''}`}
                    onClick={e => openHeroPopup(site.id, e)}
                  >
                    {heroStatus[site.id]
                      ? <span className="db-hero-yes" title={heroStatus[site.id].path}>&#10003;</span>
                      : <span className="db-hero-no" title="No hero image">&#10007;</span>}
                  </td>

                  {/* User (edited by) */}
                  <td className={`db-td db-td-edited db-edited-${site.eb || 'initial'}`}>
                    {site.eb || 'initial'}
                  </td>

                  {/* DB source badge */}
                  <td className="db-td db-td-db">
                    {srcCfg && (
                      <span className="db-source-abbr" style={{ background: srcCfg.color + '25', color: srcCfg.color, borderColor: srcCfg.color + '55' }}>
                        {srcCfg.abbr}
                      </span>
                    )}
                  </td>

                  {/* Audited */}
                  <td className="db-td db-td-audited" title={site.aud || ''}>
                    {site.aud
                      ? <span className="db-audited-yes" title={formatRelativeDate(site.aud)}>&#10003;</span>
                      : <span className="db-audited-no">&mdash;</span>}
                  </td>

                  {/* Last edited (timestamp) — click for history */}
                  <td
                    className={`db-td db-td-timestamp ${site.ea ? 'db-td-clickable' : ''}`}
                    title={site.ea ? 'Click to view edit history' : ''}
                    onClick={() => site.ea && fetchSiteHistory(site.id, site.n)}
                  >
                    {site.ea ? formatRelativeDate(site.ea) : <span className="db-muted">&mdash;</span>}
                  </td>

                  {/* Site ID */}
                  <td className="db-td db-td-id">
                    <div className="db-td-flex">
                      <CopyButton text={site.id} title="Copy site ID" size={11} />
                      <span className="db-id-text" title={site.id}>{site.id.slice(0, 8)}</span>
                    </div>
                  </td>

                  {/* Edit button */}
                  {isFounder && (
                    <td className="db-td db-td-edit">
                      <button className="db-edit-btn" onClick={() => openEditModal(site)} title="Edit all fields">
                        &#9998;
                      </button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
        {hasMore && (
          <div className="db-load-more">
            <button onClick={() => setVisibleRows(v => v + ROWS_PER_PAGE)}>
              Load more ({filteredSites.length - visibleRows} remaining)
            </button>
          </div>
        )}
      </div>

      {/* Hero popover */}
      {heroPopup && (
        <div
          className="db-hero-popover"
          ref={heroPopoverRef}
          style={{
            top: heroPopup.rect.bottom + 4,
            left: Math.min(heroPopup.rect.left, window.innerWidth - 320),
          }}
        >
          <div className="db-hero-popover-title">Set Hero Image</div>
          <input
            className="db-hero-input"
            placeholder="Image URL"
            value={heroImageUrl}
            onChange={e => setHeroImageUrl(e.target.value)}
            autoFocus
          />
          <input
            className="db-hero-input"
            placeholder="Attribution URL"
            value={heroAttrUrl}
            onChange={e => setHeroAttrUrl(e.target.value)}
          />
          {heroError && <div className="db-hero-error">{heroError}</div>}
          <button
            className="db-hero-submit"
            onClick={handleSetHero}
            disabled={heroSaving || !heroImageUrl}
          >
            {heroSaving ? 'Saving...' : 'Set Hero'}
          </button>
        </div>
      )}

      {/* Footer */}
      <div className="db-footer">
        Showing {displayedSites.length} of {filteredSites.length} sites
        {filteredSites.length < sites.length && ` (${sites.length} total)`}
        {sourceFilter !== 'all' && ` \u2014 source: ${SOURCE_CONFIG[sourceFilter]?.name}`}
      </div>

      {/* Site Popup Overlay */}
      {popupSite && <SitePopupOverlay site={popupSite} onClose={() => setPopupSite(null)} />}

      {/* Pending changes bar */}
      {pendingEdits.size > 0 && (
        <div className="db-pending-bar">
          <span className="db-pending-count">{pendingEdits.size} pending change{pendingEdits.size !== 1 ? 's' : ''}</span>
          <button className="db-btn db-btn-discard" onClick={discardAllEdits}>Discard All</button>
          <button className="db-btn db-btn-commit" onClick={() => setShowReviewModal(true)}>
            Review &amp; Commit
          </button>
        </div>
      )}

      {/* Review modal */}
      {showReviewModal && (
        <div className="db-modal-overlay" onClick={() => !committing && setShowReviewModal(false)}>
          <div className="db-modal db-modal-review" onClick={e => e.stopPropagation()}>
            <div className="db-modal-header">
              <h2>Review Changes ({pendingEdits.size} edit{pendingEdits.size !== 1 ? 's' : ''})</h2>
              <button className="db-modal-close" onClick={() => !committing && setShowReviewModal(false)}>&times;</button>
            </div>
            <div className="db-modal-body db-review-list">
              {Array.from(pendingEdits.values()).map(edit => (
                <div key={edit.siteId} className="db-review-item">
                  <div className="db-review-name">{edit.siteName}</div>
                  {Object.entries(edit.changes).map(([field, { old: oldVal, new: newVal }]) => (
                    <div key={field} className="db-review-change">
                      <span className="db-review-field">{field}:</span>
                      <span className="db-review-old">{oldVal || '(empty)'}</span>
                      <span className="db-review-arrow">&rarr;</span>
                      <span className="db-review-new">{newVal || '(empty)'}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div className="db-modal-footer">
              <button className="db-btn db-btn-cancel" onClick={() => setShowReviewModal(false)} disabled={committing}>Cancel</button>
              <button className="db-btn db-btn-commit" onClick={commitAllEdits} disabled={committing}>
                {committing ? 'Committing...' : 'Commit All'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Upload modal */}
      {showUploadModal && (
        <div className="db-modal-overlay" onClick={() => !uploading && setShowUploadModal(false)}>
          <div className="db-modal db-modal-upload" onClick={e => e.stopPropagation()}>
            <div className="db-modal-header">
              <h2>Upload Sites</h2>
              <button className="db-modal-close" onClick={() => !uploading && setShowUploadModal(false)}>&times;</button>
            </div>
            <div className="db-modal-body">
              <div className="db-upload-controls">
                <div className="db-upload-target-row">
                  <span className="db-upload-target-label">Target</span>
                  <div className="db-upload-target-pills">
                    {Object.entries(SOURCE_CONFIG).map(([id, cfg]) => (
                      <button
                        key={id}
                        className={`db-source-pill ${uploadTarget === id ? 'active' : ''}`}
                        style={{
                          borderColor: uploadTarget === id ? cfg.color : undefined,
                          background: uploadTarget === id ? cfg.color + '18' : undefined,
                          color: uploadTarget === id ? cfg.color : undefined,
                        }}
                        onClick={() => !uploadFileName && setUploadTarget(id)}
                        disabled={!!uploadFileName}
                        title={uploadFileName ? 'Clear the file first to change target' : `Upload to ${cfg.name}`}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
                        {cfg.name}
                      </button>
                    ))}
                  </div>
                </div>

                {!uploadFileName && (
                  <div
                    className={`db-upload-dropzone ${uploadDragOver ? 'dragover' : ''}`}
                    onDragOver={e => { e.preventDefault(); setUploadDragOver(true) }}
                    onDragLeave={() => setUploadDragOver(false)}
                    onDrop={handleUploadDrop}
                    onClick={() => document.getElementById('upload-file-input')?.click()}
                  >
                    <input id="upload-file-input" type="file" accept=".csv,.json,.geojson" onChange={handleUploadFile} style={{ display: 'none' }} />
                    <div className="db-dropzone-icon">+</div>
                    <div className="db-dropzone-text">Drop file here or click to browse</div>
                    <div className="db-dropzone-hint">CSV, JSON, or GeoJSON</div>
                  </div>
                )}
              </div>

              {uploadParsed.length > 0 && (
                <>
                  <div className="db-upload-summary">
                    <span className="db-upload-file">{uploadFileName}</span>
                    <span className="db-upload-stat db-upload-unchanged">{uploadParsed.filter(p => p._status === 'update' && (!p._changedFields || p._changedFields.length === 0)).length} unchanged</span>
                    <span className="db-upload-stat db-upload-update">{uploadParsed.filter(p => p._status === 'update' && p._changedFields && p._changedFields.length > 0).length} changed</span>
                    <span className="db-upload-stat db-upload-insert">{uploadParsed.filter(p => p._status === 'insert').length} new</span>
                    {uploadParsed.filter(p => p._status === 'error').length > 0 && (
                      <span className="db-upload-stat db-upload-error">{uploadParsed.filter(p => p._status === 'error').length} errors</span>
                    )}
                  </div>

                  {/* Diff view — only show sites with actual changes or inserts */}
                  <div className="db-upload-diff">
                    {uploadParsed
                      .filter(p => p._status === 'insert' || (p._status === 'update' && p._changedFields && p._changedFields.length > 0))
                      .slice(0, 100)
                      .map((p, i) => (
                        <div key={i} className={`db-diff-item db-diff-${p._status}`}>
                          <div className="db-diff-header">
                            <span className={`db-upload-status-pill db-upload-status-${p._status}`}>
                              {p._status === 'insert' ? 'NEW' : 'CHANGED'}
                            </span>
                            <span className="db-diff-name">{p.name}</span>
                            {p._changedFields && (
                              <span className="db-diff-count">{p._changedFields.length} field{p._changedFields.length !== 1 ? 's' : ''}</span>
                            )}
                          </div>
                          {p._status === 'update' && p._changedFields && p._currentData && (
                            <div className="db-diff-fields">
                              {p._changedFields.map(field => {
                                const oldVal = String((p._currentData as Record<string, unknown>)?.[field] ?? '')
                                const newVal = String((p as unknown as Record<string, unknown>)[field] ?? '')
                                const label = field.replace(/_/g, ' ')
                                return (
                                  <div key={field} className="db-diff-row">
                                    <span className="db-diff-field">{label}</span>
                                    <span className="db-diff-old">{oldVal || '(empty)'}</span>
                                    <span className="db-diff-arrow">&rarr;</span>
                                    <span className="db-diff-new">{newVal || '(empty)'}</span>
                                  </div>
                                )
                              })}
                            </div>
                          )}
                          {p._status === 'insert' && (
                            <div className="db-diff-fields">
                              <div className="db-diff-row"><span className="db-diff-field">type</span><span className="db-diff-new">{p.site_type || '(none)'}</span></div>
                              <div className="db-diff-row"><span className="db-diff-field">period</span><span className="db-diff-new">{p.period_name || '(none)'}</span></div>
                              <div className="db-diff-row"><span className="db-diff-field">country</span><span className="db-diff-new">{p.country || '(none)'}</span></div>
                            </div>
                          )}
                        </div>
                      ))}
                    {uploadParsed.filter(p => p._status === 'insert' || (p._status === 'update' && p._changedFields && p._changedFields.length > 0)).length === 0 && (
                      <div className="db-diff-empty">No changes detected &mdash; all uploaded sites match the current database.</div>
                    )}
                  </div>
                </>
              )}
            </div>
            <div className="db-modal-footer">
              <div className="db-modal-footer-toggles">
                <button
                  className={`db-upload-audited-toggle ${uploadCreateSnapshot ? 'active' : ''}`}
                  onClick={() => setUploadCreateSnapshot(!uploadCreateSnapshot)}
                  title="Create a snapshot of the current database state before applying changes. This allows you to roll back."
                >
                  <span className={`db-toggle-check ${uploadCreateSnapshot ? 'checked' : ''}`} />
                  Create snapshot
                </button>
                <button
                  className={`db-upload-audited-toggle ${uploadMarkAudited ? 'active' : ''} ${!uploadMarkAudited && uploadParsed.length > 0 ? 'db-audited-remind' : ''}`}
                  onClick={() => setUploadMarkAudited(!uploadMarkAudited)}
                  title="Mark all sites in this source as audited after upload. Enable this if you've reviewed the full database, not just the uploaded sites."
                >
                  <span className={`db-toggle-check ${uploadMarkAudited ? 'checked' : ''}`} />
                  Mark all as audited
                </button>
              </div>
              <div className="db-modal-footer-buttons">
                <button className="db-btn db-btn-cancel" onClick={() => { setShowUploadModal(false); setUploadParsed([]); setUploadFileName(''); setUploadMarkAudited(false); setUploadCreateSnapshot(true) }} disabled={uploading}>Cancel</button>
                <button className="db-btn db-btn-commit" onClick={commitUpload} disabled={uploading || uploadParsed.filter(p => p._status !== 'error').length === 0} title={uploadCreateSnapshot ? 'Creates a snapshot of current state, then applies all changes' : 'Applies changes without creating a snapshot'}>
                  {uploading ? 'Applying...' : uploadCreateSnapshot ? 'Snapshot & Apply' : 'Apply Changes'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Undo history — shows when there are snapshots to restore */}
      {isFounder && dbSnapshots.length > 0 && (
        <details className="db-snapshots-panel" open>
          <summary className="db-snapshots-summary">Undo History ({dbSnapshots.length} snapshot{dbSnapshots.length !== 1 ? 's' : ''})</summary>
          <div className="db-snapshots-list">
            {dbSnapshots.map(snap => {
              const dt = new Date(snap.created_at)
              const dateStr = dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
              const timeStr = dt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
              return (
                <div key={snap.id} className="db-snapshot-card">
                  <div className="db-snapshot-row-top">
                    <span className={`db-snapshot-type db-snapshot-type-${snap.snapshot_type || 'edit'}`}>{snap.snapshot_type === 'upload' ? 'UPLOAD' : 'EDIT'}</span>
                    <span className="db-snapshot-desc">{snap.description}</span>
                    <span className="db-snapshot-actions">
                      <button className="db-btn db-btn-preview" onClick={() => previewDbSnapshot(snap.id)} disabled={snapshotPreviewLoading} title="Preview what restoring this snapshot would change">Preview</button>
                      <button className="db-btn db-btn-restore" onClick={() => restoreDbSnapshot(snap.id)} title="Revert affected sites to their pre-change state">Restore</button>
                    </span>
                  </div>
                  <div className="db-snapshot-row-detail">
                    <span className="db-snapshot-detail-item" title={dt.toISOString()}>
                      <span className="db-snapshot-detail-label">When</span>
                      {dateStr} {timeStr} ({formatRelativeDate(snap.created_at)})
                    </span>
                    <span className="db-snapshot-detail-item">
                      <span className="db-snapshot-detail-label">By</span>
                      {snap.created_by || 'system'}
                    </span>
                    <span className="db-snapshot-detail-item">
                      <span className="db-snapshot-detail-label">Sites</span>
                      {snap.row_count} site{snap.row_count !== 1 ? 's' : ''}
                    </span>
                  </div>
                  {snap.site_names.length > 0 && (
                    <div className="db-snapshot-sites">
                      {snap.site_names.slice(0, 10).map((name, i) => (
                        <span key={i} className="db-snapshot-site-tag">{name}</span>
                      ))}
                      {snap.site_names.length > 10 && (
                        <span className="db-snapshot-site-more">+{snap.site_names.length - 10} more</span>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </details>
      )}

      {/* Snapshot Preview Modal */}
      {snapshotPreview && (
        <div className="db-modal-overlay" onClick={() => !snapshotPreviewLoading && setSnapshotPreview(null)}>
          <div className="db-modal db-upload-modal" onClick={e => e.stopPropagation()}>
            <div className="db-modal-header">
              <h2>Snapshot Preview</h2>
              {sourceFilter !== 'all' && (
                <span className="db-snapshot-source-badge" style={{ borderColor: SOURCE_CONFIG[sourceFilter]?.color, background: SOURCE_CONFIG[sourceFilter]?.color + '15' }}>
                  <span className="db-snapshot-source-dot" style={{ background: SOURCE_CONFIG[sourceFilter]?.color }} />
                  {SOURCE_CONFIG[sourceFilter]?.name || sourceFilter}
                </span>
              )}
              <button className="db-modal-close" onClick={() => setSnapshotPreview(null)}>&times;</button>
            </div>
            <div className="db-modal-body">
              <div className="db-upload-summary">
                <span className="db-upload-file">{snapshotPreview.description}</span>
                <span className="db-upload-stat db-upload-unchanged">{snapshotPreview.unchanged_count} unchanged</span>
                <span className="db-upload-stat db-upload-update">{snapshotPreview.changed_count} changed</span>
                {snapshotPreview.deleted_count > 0 && (
                  <span className="db-upload-stat db-upload-error">{snapshotPreview.deleted_count} deleted since</span>
                )}
                <span className="db-snapshot-preview-meta">{snapshotPreview.created_by || 'system'} &middot; {formatRelativeDate(snapshotPreview.created_at)}</span>
              </div>

              <div className="db-upload-diff">
                {snapshotPreview.sites
                  .filter(s => s.status === 'changed' || s.status === 'deleted')
                  .map(s => (
                    <div key={s.site_id} className={`db-diff-item ${s.status === 'deleted' ? 'db-diff-insert' : 'db-diff-update'}`}>
                      <div className="db-diff-header">
                        <span className={`db-upload-status-pill ${s.status === 'deleted' ? 'db-upload-status-error' : 'db-upload-status-update'}`}>
                          {s.status === 'deleted' ? 'DELETED' : 'REVERT'}
                        </span>
                        <span className="db-diff-name">{s.name}</span>
                        {s.fields.length > 0 && (
                          <span className="db-diff-count">{s.fields.length} field{s.fields.length !== 1 ? 's' : ''}</span>
                        )}
                      </div>
                      {s.status === 'changed' && s.fields.length > 0 && (
                        <div className="db-diff-fields">
                          {s.fields.map(f => (
                            <div key={f.field} className="db-diff-row">
                              <span className="db-diff-field">{f.field.replace(/_/g, ' ')}</span>
                              <span className="db-diff-old">{f.current || '(empty)'}</span>
                              <span className="db-diff-arrow">&rarr;</span>
                              <span className="db-diff-new">{f.restore_to || '(empty)'}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                {snapshotPreview.sites.filter(s => s.status === 'changed' || s.status === 'deleted').length === 0 && (
                  <div className="db-diff-empty">No differences &mdash; all sites already match the snapshot state.</div>
                )}
              </div>
            </div>
            <div className="db-modal-footer">
              <div className="db-upload-snapshot-notice">Restoring will revert the {snapshotPreview.changed_count} changed site{snapshotPreview.changed_count !== 1 ? 's' : ''} to their pre-change values. A new snapshot is created automatically.</div>
              <div className="db-modal-footer-buttons">
                <button className="db-btn db-btn-cancel" onClick={() => setSnapshotPreview(null)}>Close</button>
                <button className="db-btn db-btn-restore" onClick={() => restoreDbSnapshot(snapshotPreview.snapshot_id)} disabled={snapshotPreview.changed_count === 0}>
                  Restore {snapshotPreview.changed_count} site{snapshotPreview.changed_count !== 1 ? 's' : ''}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Site Edit History Modal */}
      {historyModal && (
        <div className="db-modal-overlay" onClick={() => setHistoryModal(null)}>
          <div className="db-modal db-modal-upload" onClick={e => e.stopPropagation()}>
            <div className="db-modal-header">
              <h2>{historyLoading ? 'Loading...' : 'Edit History'} &mdash; {historyModal.siteName}</h2>
              <button className="db-modal-close" onClick={() => setHistoryModal(null)}>&times;</button>
            </div>
            <div className="db-modal-body">
              {historyModal.history.length === 0 ? (
                <div className="db-diff-empty">No edit history found for this site.</div>
              ) : (
                <div className="db-upload-diff">
                  {historyModal.history.map((entry, i) => {
                    const dt = new Date(entry.date)
                    const dateStr = dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
                    const timeStr = dt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
                    return (
                      <div key={i} className="db-diff-item db-diff-update">
                        <div className="db-diff-header">
                          <span className={`db-snapshot-type db-snapshot-type-${entry.type || 'edit'}`}>{entry.type === 'upload' ? 'UPLOAD' : 'EDIT'}</span>
                          <span className="db-diff-name">{dateStr} {timeStr}</span>
                          <span className="db-diff-count">{entry.by || 'system'} &middot; {entry.changes.length} field{entry.changes.length !== 1 ? 's' : ''}</span>
                        </div>
                        {entry.changes.length > 0 ? (
                          <div className="db-diff-fields">
                            {entry.changes.map(c => (
                              <div key={c.field} className="db-diff-row">
                                <span className="db-diff-field">{c.field.replace(/_/g, ' ')}</span>
                                <span className="db-diff-old">{c.before || '(empty)'}</span>
                                <span className="db-diff-arrow">&rarr;</span>
                                <span className="db-diff-new">{c.after || '(empty)'}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="db-diff-fields">
                            <span className="db-diff-count" style={{ padding: '4px 0' }}>{entry.description}</span>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
            <div className="db-modal-footer">
              <button className="db-btn db-btn-cancel" onClick={() => setHistoryModal(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Diff Modal */}
      {showDiffModal && (
        <div className="db-modal-overlay" onClick={() => !diffLoading && setShowDiffModal(false)}>
          <div className="db-modal db-diff-modal" onClick={e => e.stopPropagation()}>
            <div className="db-modal-header">
              <h2>Snapshot Diff</h2>
              <button className="db-modal-close" onClick={() => setShowDiffModal(false)}>&times;</button>
            </div>
            <div className="db-modal-body db-diff-body">
              {/* Selector row */}
              <div className="db-diff-selectors">
                <div className="db-diff-select-group">
                  <label>From</label>
                  <select value={diffFrom} onChange={e => setDiffFrom(e.target.value)}>
                    {snapshots.map(s => (
                      <option key={s.date} value={s.date}>
                        {s.date} ({s.sites.toLocaleString()} sites)
                      </option>
                    ))}
                  </select>
                </div>
                <span className="db-diff-arrow">&rarr;</span>
                <div className="db-diff-select-group">
                  <label>To</label>
                  <select value={diffTo} onChange={e => setDiffTo(e.target.value)}>
                    {snapshots.map(s => (
                      <option key={s.date} value={s.date}>
                        {s.date} ({s.sites.toLocaleString()} sites)
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  className="db-btn db-btn-save"
                  onClick={fetchDiff}
                  disabled={diffLoading || diffFrom === diffTo}
                >
                  {diffLoading ? 'Loading...' : 'Compare'}
                </button>
              </div>

              {diffError && <div className="db-diff-error">{diffError}</div>}

              {diffData && (
                <>
                  {/* Header summary */}
                  <div className="db-diff-header">
                    <span>{diffData.from_count.toLocaleString()} sites</span>
                    <span className="db-diff-arrow">&rarr;</span>
                    <span>{diffData.to_count.toLocaleString()} sites</span>
                  </div>

                  {/* Summary pills */}
                  <div className="db-diff-summary">
                    <span className="db-diff-pill db-diff-pill-added">+{diffData.summary.added} added</span>
                    <span className="db-diff-pill db-diff-pill-removed">&minus;{diffData.summary.removed} removed</span>
                    <span className="db-diff-pill db-diff-pill-changed">~{diffData.summary.changed} changed</span>
                  </div>

                  {/* Field breakdown */}
                  {Object.keys(diffData.summary.fields).length > 0 && (
                    <div className="db-diff-fields-bar">
                      {Object.entries(diffData.summary.fields)
                        .sort(([, a], [, b]) => b - a)
                        .map(([field, count]) => (
                          <span key={field} className="db-diff-field-tag">{field}: {count}</span>
                        ))}
                    </div>
                  )}

                  {/* Changed section */}
                  {diffData.changed.length > 0 && (
                    <div className="db-diff-section">
                      <div className="db-diff-section-header db-diff-section-changed">
                        CHANGED ({diffData.changed.length})
                      </div>
                      <div className="db-diff-section-body">
                        {diffData.changed.map(site => {
                          const isExpanded = expandedDiffRows.has(site.id)
                          return (
                            <div key={site.id} className={`db-diff-row ${isExpanded ? 'db-diff-row-expanded' : ''}`}>
                              <div className="db-diff-row-header" onClick={() => toggleDiffRow(site.id)}>
                                <span className="db-diff-row-arrow">{isExpanded ? '\u25BC' : '\u25B6'}</span>
                                <span className="db-diff-row-name">{site.n}</span>
                                <span className="db-diff-row-fields">
                                  {Object.keys(site.fields).join(', ')}
                                </span>
                              </div>
                              {isExpanded && (
                                <div className="db-diff-row-details">
                                  <table className="db-diff-field-table">
                                    <thead>
                                      <tr>
                                        <th>Field</th>
                                        <th>Old</th>
                                        <th>New</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {Object.entries(site.fields).map(([field, change]) => (
                                        <tr key={field}>
                                          <td className="db-diff-field-name">{field}</td>
                                          <td className="db-diff-old">{change.from || '(empty)'}</td>
                                          <td className="db-diff-new">{change.to || '(empty)'}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* Added section */}
                  {diffData.added.length > 0 && (
                    <div className="db-diff-section">
                      <div
                        className="db-diff-section-header db-diff-section-added"
                        onClick={() => diffData.added.length > 20 && setDiffAddedExpanded(v => !v)}
                        style={diffData.added.length > 20 ? { cursor: 'pointer' } : undefined}
                      >
                        ADDED ({diffData.added.length})
                        {diffData.added.length > 20 && (
                          <span className="db-diff-section-toggle">
                            {diffAddedExpanded ? 'Collapse' : 'Show all'}
                          </span>
                        )}
                      </div>
                      <div className="db-diff-section-body">
                        <table className="db-diff-list-table">
                          <thead>
                            <tr>
                              <th>Name</th><th>Category</th><th>Period</th><th>Country</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(diffAddedExpanded ? diffData.added : diffData.added.slice(0, 20)).map(site => (
                              <tr key={site.id} className="db-diff-added-row">
                                <td>{site.n}</td>
                                <td>{site.t || ''}</td>
                                <td>{site.pn || ''}</td>
                                <td>{site.c || ''}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {!diffAddedExpanded && diffData.added.length > 20 && (
                          <button className="db-diff-show-all" onClick={() => setDiffAddedExpanded(true)}>
                            Show all {diffData.added.length} added sites
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Removed section */}
                  {diffData.removed.length > 0 && (
                    <div className="db-diff-section">
                      <div
                        className="db-diff-section-header db-diff-section-removed"
                        onClick={() => diffData.removed.length > 20 && setDiffRemovedExpanded(v => !v)}
                        style={diffData.removed.length > 20 ? { cursor: 'pointer' } : undefined}
                      >
                        REMOVED ({diffData.removed.length})
                        {diffData.removed.length > 20 && (
                          <span className="db-diff-section-toggle">
                            {diffRemovedExpanded ? 'Collapse' : 'Show all'}
                          </span>
                        )}
                      </div>
                      <div className="db-diff-section-body">
                        <table className="db-diff-list-table">
                          <thead>
                            <tr>
                              <th>Name</th><th>Category</th><th>Period</th><th>Country</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(diffRemovedExpanded ? diffData.removed : diffData.removed.slice(0, 20)).map(site => (
                              <tr key={site.id} className="db-diff-removed-row">
                                <td>{site.n}</td>
                                <td>{site.t || ''}</td>
                                <td>{site.pn || ''}</td>
                                <td>{site.c || ''}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {!diffRemovedExpanded && diffData.removed.length > 20 && (
                          <button className="db-diff-show-all" onClick={() => setDiffRemovedExpanded(true)}>
                            Show all {diffData.removed.length} removed sites
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Empty state */}
                  {diffData.summary.added === 0 && diffData.summary.removed === 0 && diffData.summary.changed === 0 && (
                    <div className="db-diff-empty">No differences found between these snapshots.</div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editModalSite && (
        <div className="db-modal-overlay" onClick={() => setEditModalSite(null)}>
          <div className="db-modal" onClick={e => e.stopPropagation()}>
            <div className="db-modal-header">
              <h2>Edit Site</h2>
              <button className="db-modal-close" onClick={() => setEditModalSite(null)}>&times;</button>
            </div>
            <div className="db-modal-body">
              <SiteForm
                key={editModalSite.id}
                initialValues={{
                  name: editModalSite.n,
                  description: editModalSite.d || '',
                  country: editModalSite.c || '',
                  lat: editModalSite.la,
                  lon: editModalSite.lo,
                  category: editModalSite.t || '',
                  period: resolvePeriod(editModalSite.pn, editModalSite.p),
                  sourceUrl: editModalSite.u || '',
                }}
                onChange={setModalFormValues}
                showPeriod={true}
              />
            </div>
            <div className="db-modal-footer">
              <button className="db-btn db-btn-cancel" onClick={() => setEditModalSite(null)}>Cancel</button>
              <button className="db-btn db-btn-save" onClick={saveModal}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
