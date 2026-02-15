import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { config } from '../config'
import { CATEGORY_COLORS, PERIOD_COLORS, getCategoryColor, getPeriodColor } from '../constants/colors'
import { resolvePeriod } from '../data/sites'
import type { SiteData } from '../data/sites'
import { SitePopupOverlay } from '../components/SitePopupOverlay'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { exportCSV, exportJSON, exportGeoJSON } from '../utils/exportFormats'
import PinAuthModal from '../components/PinAuthModal'
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

// Chronological order for period sorting (oldest first, index 0 = oldest)
const PERIOD_ORDER: Record<string, number> = {
  '< 4500 BC': 0,
  '4500 - 3000 BC': 1,
  '3000 - 1500 BC': 2,
  '1500 - 500 BC': 3,
  '500 BC - 1 AD': 4,
  '1 - 500 AD': 5,
  '500 - 1000 AD': 6,
  '1000 - 1500 AD': 7,
  '1500+ AD': 8,
  'Unknown': 9,
}

// Sort periods chronologically (oldest first)
const SORTED_PERIODS = Object.keys(PERIOD_COLORS).sort((a, b) => (PERIOD_ORDER[a] ?? 99) - (PERIOD_ORDER[b] ?? 99))

interface SnapshotEntry {
  date: string
  file: string
  sites: number
}

const SOURCE_CONFIG: Record<string, { name: string; color: string }> = {
  ancient_nerds: { name: 'ANCIENT NERDS Original', color: '#FFD700' },
  lyra: { name: 'ANCIENT NERDS Radar', color: '#8b5cf6' },
  ancient_nerds_community: { name: 'ANCIENT NERDS Community', color: '#22c55e' },
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

  // Auth
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [adminPin, setAdminPin] = useState<string | null>(null)
  const [showPinModal, setShowPinModal] = useState(false)

  // Inline editing
  const [editingCell, setEditingCell] = useState<{ id: string; field: 'type' | 'period' | 'country' } | null>(null)
  const [editValue, setEditValue] = useState('')

  // Modal editing
  const [editModalSite, setEditModalSite] = useState<AuditSite | null>(null)
  const [modalForm, setModalForm] = useState({ title: '', description: '', lat: '', lon: '', category: '', period: '', sourceUrl: '' })
  const [saving, setSaving] = useState(false)

  // Expanded descriptions
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  // Copied coords toast
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Site popup
  const [popupSite, setPopupSite] = useState<SiteData | null>(null)

  // Source filter
  const [sourceFilter, setSourceFilter] = useState('all')

  // Version snapshots
  const [snapshots, setSnapshots] = useState<SnapshotEntry[]>([])
  const [selectedVersion, setSelectedVersion] = useState('latest')

  // Fetch snapshot manifest on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${config.api.baseUrl}/snapshots/?${CACHE_BUSTER}`)
        if (res.ok) {
          const data = await res.json()
          setSnapshots(data.snapshots || [])
        }
      } catch {
        // Snapshots are optional — if endpoint is unavailable, just show "Latest"
      }
    })()
  }, [])

  // Fetch sites (live or from snapshot)
  useEffect(() => {
    (async () => {
      setLoading(true)
      setError('')
      try {
        let data: { sites?: AuditSite[] }
        if (selectedVersion === 'latest') {
          const res = await fetch(`${config.api.baseUrl}/sites/all?source=ancient_nerds&source=lyra&source=ancient_nerds_community&limit=100000&${CACHE_BUSTER}`)
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          data = await res.json()
        } else {
          const res = await fetch(`/data/snapshots/${selectedVersion}.json`)
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          data = await res.json()
        }
        setSites(data.sites || [])
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load sites')
      } finally {
        setLoading(false)
      }
    })()
  }, [selectedVersion])

  // Compute stats
  const stats = useMemo(() => {
    const total = sites.length
    const no_period = sites.filter(hasPeriodIssue).length
    const no_type = sites.filter(hasTypeIssue).length
    const no_country = sites.filter(hasCountryIssue).length
    const suspect_modern = sites.filter(isSuspectModern).length
    const no_desc = sites.filter(hasDescIssue).length
    const no_source = sites.filter(hasSourceIssue).length
    const no_image = sites.filter(hasImageIssue).length
    const no_coords = sites.filter(hasCoordsIssue).length
    return { total, no_period, no_type, no_country, suspect_modern, no_desc, no_source, no_image, no_coords }
  }, [sites])

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

  // Auth gate
  const requireAuth = useCallback((cb: () => void) => {
    if (isAuthenticated) { cb(); return }
    setShowPinModal(true)
    pendingAuthAction.current = cb
  }, [isAuthenticated])

  const pendingAuthAction = useRef<(() => void) | null>(null)

  const handleAuthSuccess = useCallback((_token: string, pin?: string) => {
    setIsAuthenticated(true)
    setAdminPin(pin || null)
    setShowPinModal(false)
    if (pendingAuthAction.current) {
      pendingAuthAction.current()
      pendingAuthAction.current = null
    }
  }, [])

  // Save site via PUT
  const saveSite = useCallback(async (siteId: string, update: {
    title: string; description?: string; category: string; period: string;
    coordinates: [number, number]; sourceUrl?: string
  }) => {
    if (!adminPin) return false
    setSaving(true)
    try {
      const res = await fetch(`${config.api.baseUrl}/sites/${siteId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Pin': adminPin,
        },
        body: JSON.stringify({
          title: update.title,
          location: null,
          category: update.category,
          period: update.period,
          description: update.description || null,
          sourceUrl: update.sourceUrl || null,
          coordinates: update.coordinates,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      return true
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Save failed')
      return false
    } finally {
      setSaving(false)
    }
  }, [adminPin])

  // Inline edit handlers
  const startInlineEdit = useCallback((site: AuditSite, field: 'type' | 'period' | 'country') => {
    requireAuth(() => {
      setEditingCell({ id: site.id, field })
      if (field === 'type') setEditValue(site.t || '')
      else if (field === 'period') setEditValue(resolvePeriod(site.pn, site.p))
      else setEditValue(site.c || '')
    })
  }, [requireAuth])

  const commitInlineEdit = useCallback(async () => {
    if (!editingCell) return
    const site = sites.find(s => s.id === editingCell.id)
    if (!site) return

    const { field } = editingCell
    const newType = field === 'type' ? editValue : (site.t || 'Unknown')
    const newPeriod = field === 'period' ? editValue : resolvePeriod(site.pn, site.p)
    const ok = await saveSite(site.id, {
      title: site.n,
      description: site.d,
      category: newType,
      period: newPeriod,
      coordinates: [site.lo, site.la],
      sourceUrl: site.u,
    })

    if (ok) {
      const now = new Date().toISOString()
      setSites(prev => prev.map(s => {
        if (s.id !== site.id) return s
        const updated = { ...s, ea: now }
        if (field === 'type') updated.t = editValue
        else if (field === 'period') updated.pn = editValue
        else updated.c = editValue
        updated.eb = 'audit'
        return updated
      }))
    }
    setEditingCell(null)
  }, [editingCell, editValue, sites, saveSite])

  const cancelInlineEdit = useCallback(() => setEditingCell(null), [])

  // Modal edit handlers
  const openEditModal = useCallback((site: AuditSite) => {
    requireAuth(() => {
      setEditModalSite(site)
      setModalForm({
        title: site.n,
        description: site.d || '',
        lat: String(site.la),
        lon: String(site.lo),
        category: site.t || '',
        period: resolvePeriod(site.pn, site.p),
        sourceUrl: site.u || '',
      })
    })
  }, [requireAuth])

  const saveModal = useCallback(async () => {
    if (!editModalSite) return
    const lat = parseFloat(modalForm.lat)
    const lon = parseFloat(modalForm.lon)
    if (isNaN(lat) || isNaN(lon)) { alert('Invalid coordinates'); return }

    const ok = await saveSite(editModalSite.id, {
      title: modalForm.title,
      description: modalForm.description,
      category: modalForm.category,
      period: modalForm.period,
      coordinates: [lon, lat],
      sourceUrl: modalForm.sourceUrl,
    })

    if (ok) {
      const now = new Date().toISOString()
      setSites(prev => prev.map(s => {
        if (s.id !== editModalSite.id) return s
        return {
          ...s,
          n: modalForm.title,
          d: modalForm.description || undefined,
          la: lat,
          lo: lon,
          t: modalForm.category || undefined,
          pn: modalForm.period,
          c: s.c,
          u: modalForm.sourceUrl || undefined,
          eb: 'audit',
          ea: now,
        }
      }))
      setEditModalSite(null)
    }
  }, [editModalSite, modalForm, saveSite])

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
      <div className="db-header">
        <div className="db-header-left">
          <span className="db-logo">ANCIENT NERDS</span>
          <span className="db-header-sep">&middot;</span>
          <span className="db-header-title">Database Audit</span>
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
          {snapshots.length > 0 && (
            <div className="db-version-badge" style={selectedVersion !== 'latest' ? {
              borderColor: '#22d3ee',
              background: 'rgba(34, 211, 238, 0.08)',
            } : undefined}>
              <span className="db-version-dot" style={{
                background: selectedVersion !== 'latest' ? '#22d3ee' : 'var(--text-secondary)'
              }} />
              <select value={selectedVersion} onChange={e => setSelectedVersion(e.target.value)}>
                <option value="latest">Latest (live)</option>
                {snapshots.map(s => (
                  <option key={s.date} value={s.date}>
                    {new Date(s.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} ({s.sites.toLocaleString()} sites)
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <div className="db-header-right">
          {isAuthenticated ? (
            <span className="db-auth-badge db-auth-unlocked">Editing Unlocked</span>
          ) : (
            <button className="db-unlock-btn" onClick={() => setShowPinModal(true)}>
              Unlock Editing
            </button>
          )}
        </div>
      </div>

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
              <th className="db-th db-th-nosort">Edited</th>
              <th className="db-th" onClick={() => handleSort('edited_at')}>Last Edited{sortArrow('edited_at')}</th>
              {isAuthenticated && <th className="db-th db-th-edit">Edit</th>}
            </tr>
          </thead>
          <tbody>
            {displayedSites.map(site => {
              const period = resolvePeriod(site.pn, site.p)
              const isEditingType = editingCell?.id === site.id && editingCell.field === 'type'
              const isEditingPeriod = editingCell?.id === site.id && editingCell.field === 'period'
              const isEditingCountry = editingCell?.id === site.id && editingCell.field === 'country'
              const flagUrl = site.c ? getCountryFlatFlagUrl(site.c) : null

              return (
                <tr key={site.id} className="db-row">
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
                    onClick={() => !isEditingType && isAuthenticated && startInlineEdit(site, 'type')}
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
                    ) : (
                      <span
                        className={`db-badge ${!site.t ? 'missing' : ''}`}
                        style={site.t ? { backgroundColor: getCategoryColor(site.t) + '33', color: getCategoryColor(site.t), borderColor: getCategoryColor(site.t) + '66' } : undefined}
                      >
                        {site.t || 'MISSING'}
                      </span>
                    )}
                  </td>

                  {/* Period cell */}
                  <td
                    className={`db-td db-td-editable ${isEditingPeriod ? 'editing' : ''}`}
                    onClick={() => !isEditingPeriod && isAuthenticated && startInlineEdit(site, 'period')}
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
                    ) : (
                      <span
                        className={`db-badge ${hasPeriodIssue(site) ? 'missing' : ''}`}
                        style={!hasPeriodIssue(site) ? { backgroundColor: getPeriodColor(period) + '33', color: getPeriodColor(period), borderColor: getPeriodColor(period) + '66' } : undefined}
                      >
                        {period}
                      </span>
                    )}
                  </td>

                  {/* Country cell */}
                  <td
                    className={`db-td db-td-country db-td-editable ${isEditingCountry ? 'editing' : ''}`}
                    onClick={() => !isEditingCountry && isAuthenticated && startInlineEdit(site, 'country')}
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
                          {site.d.length > 80 ? site.d.slice(0, 80) + '\u2026' : site.d}
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

                  {/* Edited by */}
                  <td className={`db-td db-td-edited db-edited-${site.eb || 'initial'}`}>
                    {site.eb || 'initial'}
                  </td>

                  {/* Last edited (timestamp) */}
                  <td className="db-td db-td-timestamp" title={site.ea || ''}>
                    {site.ea ? formatRelativeDate(site.ea) : <span className="db-muted">&mdash;</span>}
                  </td>

                  {/* Edit button */}
                  {isAuthenticated && (
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

      {/* PIN Auth Modal */}
      <PinAuthModal
        isOpen={showPinModal}
        onClose={() => { setShowPinModal(false); pendingAuthAction.current = null }}
        onSuccess={handleAuthSuccess}
        variant="admin"
      />

      {/* Edit Modal */}
      {editModalSite && (
        <div className="db-modal-overlay" onClick={() => !saving && setEditModalSite(null)}>
          <div className="db-modal" onClick={e => e.stopPropagation()}>
            <div className="db-modal-header">
              <h2>Edit Site</h2>
              <button className="db-modal-close" onClick={() => !saving && setEditModalSite(null)}>&times;</button>
            </div>
            <div className="db-modal-body">
              <div className="db-field">
                <label>Name</label>
                <input value={modalForm.title} onChange={e => setModalForm(f => ({ ...f, title: e.target.value }))} />
              </div>
              <div className="db-field">
                <label>Description</label>
                <textarea rows={3} value={modalForm.description} onChange={e => setModalForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              <div className="db-field-row">
                <div className="db-field">
                  <label>Latitude</label>
                  <input type="number" step="any" value={modalForm.lat} onChange={e => setModalForm(f => ({ ...f, lat: e.target.value }))} />
                </div>
                <div className="db-field">
                  <label>Longitude</label>
                  <input type="number" step="any" value={modalForm.lon} onChange={e => setModalForm(f => ({ ...f, lon: e.target.value }))} />
                </div>
              </div>
              <div className="db-field">
                <label>Category</label>
                <select value={modalForm.category} onChange={e => setModalForm(f => ({ ...f, category: e.target.value }))}>
                  <option value="">-- none --</option>
                  {CATEGORY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="db-field">
                <label>Period</label>
                <select value={modalForm.period} onChange={e => setModalForm(f => ({ ...f, period: e.target.value }))}>
                  {SORTED_PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="db-field">
                <label>Source URL</label>
                <input value={modalForm.sourceUrl} onChange={e => setModalForm(f => ({ ...f, sourceUrl: e.target.value }))} />
              </div>
            </div>
            <div className="db-modal-footer">
              <button className="db-btn db-btn-cancel" onClick={() => setEditModalSite(null)} disabled={saving}>Cancel</button>
              <button className="db-btn db-btn-save" onClick={saveModal} disabled={saving}>
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
