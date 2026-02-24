import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react'
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
import SiteForm from '../components/SiteForm'
import type { SiteFormValues } from '../components/SiteForm'
import '../styles/db-audit.css'

const LyraProfileModal = lazy(() => import('../components/LyraProfileModal'))

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
  c?: string       // country
  u?: string       // source_url
  i?: string       // thumbnail_url
  eb?: string      // edited_by
  ea?: string      // edited_at (ISO timestamp)
}

type IssueFilter = 'all' | 'no_period' | 'no_type' | 'no_country' | 'suspect_modern' | 'no_desc' | 'no_source' | 'no_image' | 'no_coords'
type SortColumn = 'name' | 'type' | 'period' | 'country' | 'edited_at'
type SortDir = 'asc' | 'desc'

const CATEGORY_OPTIONS = Object.keys(CATEGORY_COLORS)
const ROWS_PER_PAGE = 500

// PERIOD_ORDER and SORTED_PERIODS imported from constants/colors.ts

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

// SOURCE_CONFIG imported from constants/colors.ts

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

  // Copied coords toast
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Site popup
  const [popupSite, setPopupSite] = useState<SiteData | null>(null)

  // Lyra profile
  const [showLyraProfile, setShowLyraProfile] = useState(false)

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
  const [dbSnapshots, setDbSnapshots] = useState<{ id: string; created_at: string; description: string; row_count: number }[]>([])

  // Pending edits (edit session)
  const [pendingEdits, setPendingEdits] = useState<Map<string, PendingEdit>>(new Map())
  const [showReviewModal, setShowReviewModal] = useState(false)
  const [committing, setCommitting] = useState(false)

  // Upload
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadParsed, setUploadParsed] = useState<ParsedSite[]>([])
  const [uploadFileName, setUploadFileName] = useState('')
  const [uploadTarget, setUploadTarget] = useState('ancient_nerds')
  const [uploading, setUploading] = useState(false)

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

  // Fetch DB snapshots
  const refreshDbSnapshots = useCallback(async () => {
    try {
      const res = await fetch(`${config.api.baseUrl}/sites/snapshots?${CACHE_BUSTER}`)
      if (res.ok) {
        const data = await res.json()
        setDbSnapshots(data.snapshots || [])
      }
    } catch { /* optional */ }
  }, [])

  useEffect(() => { refreshDbSnapshots() }, [refreshDbSnapshots])

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
    else { setSortColumn(col); setSortDir(col === 'edited_at' ? 'desc' : 'asc') }
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

  // Copy coords to clipboard
  const copyCoords = useCallback((la: number, lo: number, id: string) => {
    navigator.clipboard.writeText(`${la.toFixed(4)}, ${lo.toFixed(4)}`)
    setCopiedId(id)
    setTimeout(() => setCopiedId(prev => prev === id ? null : prev), 1000)
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
  const handleUploadFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadFileName(file.name)
    const reader = new FileReader()
    reader.onload = () => {
      const text = reader.result as string
      let parsed: ParsedSite[] = []
      if (file.name.endsWith('.csv')) parsed = parseCSV(text)
      else if (file.name.endsWith('.geojson')) parsed = parseGeoJSON(text)
      else parsed = parseJSON(text)

      // Match against existing sites by name
      const nameIndex = new Map(sites.map(s => [s.n.toLowerCase(), s]))
      for (const p of parsed) {
        const existing = nameIndex.get(p.name.toLowerCase())
        if (existing) {
          p._status = 'update'
          p._matchedId = existing.id
        } else if (!p._status) {
          p._status = 'insert'
        }
      }
      setUploadParsed(parsed)
    }
    reader.readAsText(file)
  }, [sites])

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
        body: JSON.stringify({ sites: payload, target_source: uploadTarget }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const result = await res.json()
      setShowUploadModal(false)
      setUploadParsed([])
      setUploadFileName('')
      refreshDbSnapshots()
      alert(`Upload complete: ${result.inserted} inserted, ${result.updated} updated`)
      // Re-fetch sites
      discardAllEdits()
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [token, uploadParsed, uploadTarget, refreshDbSnapshots, discardAllEdits])

  // Restore a DB snapshot
  const restoreDbSnapshot = useCallback(async (snapshotId: string) => {
    if (!token) return
    if (!confirm('Restore this snapshot? This will revert the affected sites to their pre-change state.')) return
    try {
      const res = await fetch(`${config.api.baseUrl}/sites/snapshots/${snapshotId}/restore`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const result = await res.json()
      alert(`Restored ${result.restored} sites`)
      discardAllEdits()
      refreshDbSnapshots()
    } catch (e: unknown) {
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
        speechBubble="I help maintain and enrich the sites database"
        onAvatarClick={() => setShowLyraProfile(true)}
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
                    const effectiveDelta = isChunked
                      ? (c.qdrant_count === 0 && c.pg_count > 0 ? c.pg_count : 0)
                      : c.delta
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
                            ) : effectiveDelta > 0 ? (
                              <span className="db-qdrant-delta stale">-{effectiveDelta.toLocaleString()}</span>
                            ) : null}
                          </>
                        ) : (
                          <>
                            <span className="db-qdrant-counts">
                              <span title="Qdrant">{c.qdrant_count.toLocaleString()}</span>
                              <span className="db-qdrant-sep">/</span>
                              <span title="PostgreSQL">{c.pg_count.toLocaleString()}</span>
                            </span>
                            {effectiveDelta != null && effectiveDelta !== 0 && (
                              <span className={`db-qdrant-delta ${effectiveDelta > 0 ? 'stale' : 'over'}`}>
                                {effectiveDelta > 0 ? `-${effectiveDelta.toLocaleString()}` : `+${Math.abs(effectiveDelta).toLocaleString()}`}
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
            <a className="db-unlock-btn" href={`${config.api.baseUrl}/auth/discord`}>
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

      {/* Per-source version selectors */}
      {snapshots.length > 0 && (
        <div className="db-version-selectors">
          <span className="db-version-selectors-label">Snapshots</span>
          {Object.entries(SOURCE_CONFIG).map(([sid, cfg]) => {
            const ver = sourceVersions[sid] || 'latest'
            const pin = activePins[sid]
            const isPinned = pin != null
            const isPinnedToThis = isPinned && pin === ver
            const isViewingPinned = isPinned && ver === pin

            return (
              <div
                key={sid}
                className="db-version-selector"
                style={{ borderColor: cfg.color + '55' }}
              >
                <span
                  className="db-source-abbr-badge"
                  style={{ background: cfg.color + '25', color: cfg.color }}
                >
                  {cfg.abbr}
                </span>
                <select
                  value={ver}
                  onChange={e => setSourceVersions(prev => ({ ...prev, [sid]: e.target.value }))}
                >
                  <option value="latest">Latest (live)</option>
                  {snapshots.map(s => {
                    const parts = s.date.split('_')
                    const d = new Date(parts[0] + 'T' + (parts[1] ? `${parts[1].slice(0,2)}:${parts[1].slice(2,4)}:${parts[1].slice(4,6)}Z` : '00:00:00Z'))
                    const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                      + (parts[1] ? ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }) : '')
                    const count = s.by_source?.[sid]
                    return (
                      <option key={s.date} value={s.date}>
                        {label} ({count != null ? count.toLocaleString() : '?'})
                      </option>
                    )
                  })}
                </select>
                {isPinned && isViewingPinned && (
                  <span className="db-pin-indicator">PUBLIC</span>
                )}
                {isFounder && ver !== 'latest' && (
                  isPinnedToThis ? (
                    <button
                      className="db-pin-btn db-pin-btn-active"
                      onClick={() => handleSetPin(sid, null)}
                      disabled={pinLoading === sid}
                    >
                      {pinLoading === sid ? '...' : 'Unpin'}
                    </button>
                  ) : (
                    <button
                      className="db-pin-btn"
                      onClick={() => handleSetPin(sid, ver)}
                      disabled={pinLoading === sid}
                    >
                      {pinLoading === sid ? '...' : 'Set as Public'}
                    </button>
                  )
                )}
                {isFounder && ver === 'latest' && isPinned && (
                  <button
                    className="db-pin-btn db-pin-btn-active"
                    onClick={() => handleSetPin(sid, null)}
                    disabled={pinLoading === sid}
                  >
                    {pinLoading === sid ? '...' : 'Unpin'}
                  </button>
                )}
              </div>
            )
          })}
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
              <th className="db-th" onClick={() => handleSort('type')}>Type{sortArrow('type')}</th>
              <th className="db-th" onClick={() => handleSort('period')}>Period{sortArrow('period')}</th>
              <th className="db-th" onClick={() => handleSort('country')}>Country{sortArrow('country')}</th>
              <th className="db-th db-th-nosort">Desc</th>
              <th className="db-th db-th-nosort">URL</th>
              <th className="db-th db-th-nosort">Img</th>
              <th className="db-th db-th-nosort">User</th>
              <th className="db-th db-th-nosort db-th-db">DB</th>
              <th className="db-th" onClick={() => handleSort('edited_at')}>Last Edited{sortArrow('edited_at')}</th>
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
                  <td className="db-td db-td-name" title={site.id} onClick={() => openPopup(site)}>
                    {site.n}
                  </td>

                  {/* Coordinates */}
                  <td className="db-td db-td-coords" onClick={() => copyCoords(site.la, site.lo, site.id)}>
                    {site.la.toFixed(4)}, {site.lo.toFixed(4)}
                    {copiedId === site.id && <span className="db-copied-toast">Copied!</span>}
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

                  {/* Image thumbnail */}
                  <td className="db-td db-td-img">
                    {site.i ? (
                      <img src={site.i} className="db-thumb" alt="" loading="lazy" />
                    ) : <span className="db-missing">&mdash;</span>}
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

                  {/* Last edited (timestamp) */}
                  <td className="db-td db-td-timestamp" title={site.ea || ''}>
                    {site.ea ? formatRelativeDate(site.ea) : <span className="db-muted">&mdash;</span>}
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

      {/* Footer */}
      <div className="db-footer">
        Showing {displayedSites.length} of {filteredSites.length} sites
        {filteredSites.length < sites.length && ` (${sites.length} total)`}
        {sourceFilter !== 'all' && ` \u2014 source: ${SOURCE_CONFIG[sourceFilter]?.name}`}
      </div>

      {/* Site Popup Overlay */}
      {popupSite && <SitePopupOverlay site={popupSite} onClose={() => setPopupSite(null)} />}

      {showLyraProfile && (
        <Suspense fallback={null}>
          <LyraProfileModal onClose={() => setShowLyraProfile(false)} />
        </Suspense>
      )}

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
              <div className="db-field">
                <label>Target Database</label>
                <select value={uploadTarget} onChange={e => setUploadTarget(e.target.value)}>
                  {Object.entries(SOURCE_CONFIG).map(([id, cfg]) => (
                    <option key={id} value={id}>{cfg.name}</option>
                  ))}
                </select>
              </div>
              <div className="db-field">
                <label>File (CSV, JSON, or GeoJSON)</label>
                <input type="file" accept=".csv,.json,.geojson" onChange={handleUploadFile} />
              </div>
              {uploadParsed.length > 0 && (
                <>
                  <div className="db-upload-summary">
                    <span className="db-upload-file">{uploadFileName}</span>
                    <span className="db-upload-stat db-upload-insert">{uploadParsed.filter(p => p._status === 'insert').length} new</span>
                    <span className="db-upload-stat db-upload-update">{uploadParsed.filter(p => p._status === 'update').length} updates</span>
                    <span className="db-upload-stat db-upload-error">{uploadParsed.filter(p => p._status === 'error').length} errors</span>
                  </div>
                  <div className="db-upload-preview">
                    <table className="db-table">
                      <thead>
                        <tr>
                          <th className="db-th db-th-nosort">Status</th>
                          <th className="db-th db-th-nosort">Name</th>
                          <th className="db-th db-th-nosort">Type</th>
                          <th className="db-th db-th-nosort">Period</th>
                          <th className="db-th db-th-nosort">Country</th>
                        </tr>
                      </thead>
                      <tbody>
                        {uploadParsed.slice(0, 100).map((p, i) => (
                          <tr key={i} className={`db-row db-upload-row-${p._status}`}>
                            <td className="db-td">
                              <span className={`db-upload-status-pill db-upload-status-${p._status}`}>
                                {p._status === 'insert' ? 'NEW' : p._status === 'update' ? 'UPD' : 'ERR'}
                              </span>
                            </td>
                            <td className="db-td">{p.name}</td>
                            <td className="db-td">{p.site_type || ''}</td>
                            <td className="db-td">{p.period_name || ''}</td>
                            <td className="db-td">{p.country || ''}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {uploadParsed.length > 100 && <div className="db-muted" style={{ padding: 8 }}>...and {uploadParsed.length - 100} more</div>}
                  </div>
                </>
              )}
            </div>
            <div className="db-modal-footer">
              <button className="db-btn db-btn-cancel" onClick={() => { setShowUploadModal(false); setUploadParsed([]); setUploadFileName('') }} disabled={uploading}>Cancel</button>
              <button className="db-btn db-btn-commit" onClick={commitUpload} disabled={uploading || uploadParsed.filter(p => p._status !== 'error').length === 0}>
                {uploading ? 'Uploading...' : `Commit Upload (${uploadParsed.filter(p => p._status !== 'error').length})`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DB Snapshots (undo history) */}
      {isFounder && dbSnapshots.length > 0 && (
        <details className="db-snapshots-panel">
          <summary className="db-snapshots-summary">Undo History ({dbSnapshots.length} snapshots)</summary>
          <div className="db-snapshots-list">
            {dbSnapshots.map(snap => (
              <div key={snap.id} className="db-snapshot-item">
                <span className="db-snapshot-desc">{snap.description}</span>
                <span className="db-snapshot-meta">{snap.row_count} rows &middot; {formatRelativeDate(snap.created_at)}</span>
                <button className="db-btn db-btn-restore" onClick={() => restoreDbSnapshot(snap.id)}>Restore</button>
              </div>
            ))}
          </div>
        </details>
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
                              <th>Name</th><th>Type</th><th>Period</th><th>Country</th>
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
                              <th>Name</th><th>Type</th><th>Period</th><th>Country</th>
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
