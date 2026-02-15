import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { config } from '../config'
import { CATEGORY_COLORS, PERIOD_COLORS, getCategoryColor, getPeriodColor } from '../constants/colors'
import { resolvePeriod } from '../data/sites'
import type { SiteData } from '../data/sites'
import { SitePopupOverlay } from '../components/SitePopupOverlay'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
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
}

type IssueFilter = 'all' | 'no_period' | 'no_type' | 'no_country' | 'suspect_modern' | 'no_desc' | 'no_source' | 'no_image' | 'no_coords'
type SortColumn = 'name' | 'type' | 'period' | 'country'
type SortDir = 'asc' | 'desc'

const CATEGORY_OPTIONS = Object.keys(CATEGORY_COLORS)
const PERIOD_OPTIONS = Object.keys(PERIOD_COLORS)

function hasPeriodIssue(s: AuditSite) { return !s.pn && s.p == null }
function hasTypeIssue(s: AuditSite) { return !s.t }
function hasCountryIssue(s: AuditSite) { return !s.c }
function isSuspectModern(s: AuditSite) { return s.p != null && s.p > 1500 }
function hasDescIssue(s: AuditSite) { return !s.d }
function hasSourceIssue(s: AuditSite) { return !s.u }
function hasImageIssue(s: AuditSite) { return !s.i }
function hasCoordsIssue(s: AuditSite) { return s.la === 0 && s.lo === 0 }

export default function DbAuditPage() {
  const [sites, setSites] = useState<AuditSite[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Filters & sort
  const [searchQuery, setSearchQuery] = useState('')
  const [activeIssue, setActiveIssue] = useState<IssueFilter>('all')
  const [typeFilter, setTypeFilter] = useState('all')
  const [countryFilter, setCountryFilter] = useState('all')
  const [periodFilter, setPeriodFilter] = useState('all')
  const [editedByFilter, setEditedByFilter] = useState('all')
  const [sortColumn, setSortColumn] = useState<SortColumn>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

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

  // Fetch all sites
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${config.api.baseUrl}/sites/all?source=ancient_nerds&source=ancient_nerds_radar&limit=100000&${CACHE_BUSTER}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        setSites(data.sites || [])
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load sites')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

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

  // Source display name for header
  const SOURCE_DISPLAY: Record<string, string> = { ancient_nerds: 'ANCIENT NERDS Original' }
  const sourceDisplay = useMemo(() => {
    const ids = Array.from(new Set(sites.map(s => s.s))).sort()
    return ids.map(id => SOURCE_DISPLAY[id] || id).join(', ')
  }, [sites])

  // Unique filter values
  const uniqueTypes = useMemo(() =>
    Array.from(new Set(sites.map(s => s.t).filter(Boolean) as string[])).sort()
  , [sites])

  const uniqueCountries = useMemo(() =>
    Array.from(new Set(sites.map(s => s.c).filter(Boolean) as string[])).sort()
  , [sites])

  const uniquePeriods = useMemo(() =>
    Array.from(new Set(sites.map(s => resolvePeriod(s.pn, s.p)).filter(v => v && v !== 'Unknown'))).sort()
  , [sites])

  const uniqueEditedBy = useMemo(() =>
    Array.from(new Set(sites.map(s => s.eb || 'initial'))).sort()
  , [sites])

  // Filtered & sorted sites
  const filteredSites = useMemo(() => {
    let result = sites

    // Issue filter
    if (activeIssue === 'no_period') result = result.filter(hasPeriodIssue)
    else if (activeIssue === 'no_type') result = result.filter(hasTypeIssue)
    else if (activeIssue === 'no_country') result = result.filter(hasCountryIssue)
    else if (activeIssue === 'suspect_modern') result = result.filter(isSuspectModern)
    else if (activeIssue === 'no_desc') result = result.filter(hasDescIssue)
    else if (activeIssue === 'no_source') result = result.filter(hasSourceIssue)
    else if (activeIssue === 'no_image') result = result.filter(hasImageIssue)
    else if (activeIssue === 'no_coords') result = result.filter(hasCoordsIssue)

    // Dropdown filters
    if (typeFilter !== 'all') result = result.filter(s => (s.t || '') === typeFilter)
    if (countryFilter !== 'all') result = result.filter(s => (s.c || '') === countryFilter)
    if (periodFilter !== 'all') result = result.filter(s => resolvePeriod(s.pn, s.p) === periodFilter)
    if (editedByFilter !== 'all') result = result.filter(s => (s.eb || 'initial') === editedByFilter)

    // Search
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter(s => s.n.toLowerCase().includes(q))
    }

    // Sort
    result = [...result].sort((a, b) => {
      let av = '', bv = ''
      switch (sortColumn) {
        case 'name': av = a.n; bv = b.n; break
        case 'type': av = a.t || ''; bv = b.t || ''; break
        case 'period': av = resolvePeriod(a.pn, a.p); bv = resolvePeriod(b.pn, b.p); break
        case 'country': av = a.c || ''; bv = b.c || ''; break
      }
      const cmp = av.localeCompare(bv)
      return sortDir === 'asc' ? cmp : -cmp
    })

    return result
  }, [sites, activeIssue, typeFilter, countryFilter, periodFilter, editedByFilter, searchQuery, sortColumn, sortDir])

  // Auth gate
  const requireAuth = useCallback((cb: () => void) => {
    if (isAuthenticated) { cb(); return }
    setShowPinModal(true)
    // Store the callback intent — we'll call it after auth succeeds
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
      setSites(prev => prev.map(s => {
        if (s.id !== site.id) return s
        const updated = { ...s }
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
          c: s.c, // country not in modal
          u: modalForm.sourceUrl || undefined,
          eb: 'audit',
        }
      }))
      setEditModalSite(null)
    }
  }, [editModalSite, modalForm, saveSite])

  // Sort handler
  const handleSort = useCallback((col: SortColumn) => {
    if (sortColumn === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortColumn(col); setSortDir('asc') }
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
          <span className="db-header-db">({sourceDisplay})</span>
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
        <div className="db-filter-group">
          <label>Type:</label>
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
            <option value="all">All</option>
            {uniqueTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="db-filter-group">
          <label>Country:</label>
          <select value={countryFilter} onChange={e => setCountryFilter(e.target.value)}>
            <option value="all">All</option>
            {uniqueCountries.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="db-filter-group">
          <label>Period:</label>
          <select value={periodFilter} onChange={e => setPeriodFilter(e.target.value)}>
            <option value="all">All</option>
            {uniquePeriods.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="db-filter-group">
          <label>Edited By:</label>
          <select value={editedByFilter} onChange={e => setEditedByFilter(e.target.value)}>
            <option value="all">All</option>
            {uniqueEditedBy.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
        </div>
        <div className="db-filter-group">
          <label>Search:</label>
          <div className="db-search-wrap">
            <input
              type="text"
              placeholder="Filter by name..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="db-search-clear" onClick={() => setSearchQuery('')}>&times;</button>
            )}
          </div>
        </div>
        <div className="db-filter-count">{filteredSites.length} sites</div>
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
              {isAuthenticated && <th className="db-th db-th-edit">Edit</th>}
            </tr>
          </thead>
          <tbody>
            {filteredSites.map(site => {
              const period = resolvePeriod(site.pn, site.p)
              const isEditingType = editingCell?.id === site.id && editingCell.field === 'type'
              const isEditingPeriod = editingCell?.id === site.id && editingCell.field === 'period'
              const isEditingCountry = editingCell?.id === site.id && editingCell.field === 'country'
              const flagUrl = site.c ? getCountryFlatFlagUrl(site.c) : null

              return (
                <tr key={site.id} className="db-row">
                  {/* Name — clickable → popup */}
                  <td className="db-td db-td-name" title={site.id} onClick={() => openPopup(site)}>
                    {site.n}
                  </td>

                  {/* Coordinates — click to copy */}
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
                        {PERIOD_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
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

                  {/* Country cell — flag + text */}
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

                  {/* Description — truncated, click to expand */}
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
      </div>

      {/* Footer */}
      <div className="db-footer">
        Showing {filteredSites.length} of {sites.length} sites
        {activeIssue !== 'all' && ` \u2014 filtered: ${activeIssue.replace(/_/g, ' ')}`}
        {typeFilter !== 'all' && ` \u2014 type: ${typeFilter}`}
        {countryFilter !== 'all' && ` \u2014 country: ${countryFilter}`}
        {periodFilter !== 'all' && ` \u2014 period: ${periodFilter}`}
        {editedByFilter !== 'all' && ` \u2014 edited by: ${editedByFilter}`}
        {searchQuery && ` \u2014 search: "${searchQuery}"`}
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
                  {PERIOD_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
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
