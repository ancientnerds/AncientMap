/**
 * Founder review modals for the Lyra Radar page.
 *
 * ApproveModal: edit/complete promotable fields, submit as overrides to
 * POST /radar/{id}/promote. Overrides are applied at promotion time only.
 * MergeModal: pick an existing site (nearby suggestion or name search),
 * submit to POST /radar/{id}/merge.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { config } from '../config'

export interface ApproveFields {
  display_name: string
  lat: number | null
  lon: number | null
  country: string | null
  site_type: string | null
  period_name: string | null
  period_start: number | null
  period_end: number | null
  description: string | null
  nearby_an_site: { site_id: string; name: string; distance_km: number } | null
}

interface ApproveModalProps {
  item: ApproveFields & { id: string }
  onSubmit: (overrides: Record<string, unknown>) => Promise<string | null>
  onClose: () => void
}

const CORE_HINT = 'Required for promotion'

export function ApproveModal({ item, onSubmit, onClose }: ApproveModalProps) {
  const [name, setName] = useState(item.display_name)
  const [lat, setLat] = useState(item.lat != null ? String(item.lat) : '')
  const [lon, setLon] = useState(item.lon != null ? String(item.lon) : '')
  const [country, setCountry] = useState(item.country ?? '')
  const [siteType, setSiteType] = useState(item.site_type ?? '')
  const [periodStart, setPeriodStart] = useState(item.period_start != null ? String(item.period_start) : '')
  const [periodEnd, setPeriodEnd] = useState(item.period_end != null ? String(item.period_end) : '')
  const [description, setDescription] = useState(item.description ?? '')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const latNum = lat.trim() === '' ? null : Number(lat)
  const lonNum = lon.trim() === '' ? null : Number(lon)
  const coordsInvalid = (latNum != null && (isNaN(latNum) || latNum < -90 || latNum > 90))
    || (lonNum != null && (isNaN(lonNum) || lonNum < -180 || lonNum > 180))

  const missingCoords = latNum == null || lonNum == null
  const missingCountry = country.trim() === ''
  const missingType = siteType.trim() === ''
  const missingDesc = description.trim().length < 50
  const canSubmit = !missingCoords && !coordsInvalid && !missingCountry && !missingType && !missingDesc && !submitting

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    // Send only fields that differ from the item (server merges over stored values)
    const overrides: Record<string, unknown> = {}
    if (name.trim() && name.trim() !== item.display_name) overrides.name = name.trim()
    if (latNum != null && latNum !== item.lat) overrides.lat = latNum
    if (lonNum != null && lonNum !== item.lon) overrides.lon = lonNum
    if (country.trim() && country.trim() !== (item.country ?? '')) overrides.country = country.trim()
    if (siteType.trim() && siteType.trim() !== (item.site_type ?? '')) overrides.site_type = siteType.trim()
    if (periodStart.trim() !== '' && Number(periodStart) !== item.period_start) overrides.period_start = Number(periodStart)
    if (periodEnd.trim() !== '' && Number(periodEnd) !== item.period_end) overrides.period_end = Number(periodEnd)
    if (description.trim() && description.trim() !== (item.description ?? '')) overrides.description = description.trim()
    const err = await onSubmit(overrides)
    setSubmitting(false)
    if (err) {
      setError(err)
    } else {
      onClose()
    }
  }

  return (
    <div className="radar-modal-overlay" onClick={onClose}>
      <div className="radar-modal" onClick={e => e.stopPropagation()}>
        <h3 className="radar-modal-title">Approve &amp; add to database</h3>
        {item.nearby_an_site && (
          <div className="radar-modal-warning">
            &#9888; Near existing AN site: {item.nearby_an_site.name} ({item.nearby_an_site.distance_km} km).
            Consider Merge instead if this is the same site.
          </div>
        )}
        <label className="radar-modal-label">Name
          <input className="radar-modal-input" value={name} onChange={e => setName(e.target.value)} />
        </label>
        <div className="radar-modal-row">
          <label className={`radar-modal-label ${missingCoords || coordsInvalid ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
            Latitude *
            <input className="radar-modal-input" value={lat} onChange={e => setLat(e.target.value)} inputMode="decimal" />
          </label>
          <label className={`radar-modal-label ${missingCoords || coordsInvalid ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
            Longitude *
            <input className="radar-modal-input" value={lon} onChange={e => setLon(e.target.value)} inputMode="decimal" />
          </label>
        </div>
        <div className="radar-modal-row">
          <label className={`radar-modal-label ${missingCountry ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
            Country *
            <input className="radar-modal-input" value={country} onChange={e => setCountry(e.target.value)} />
          </label>
          <label className={`radar-modal-label ${missingType ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
            Site type *
            <input className="radar-modal-input" value={siteType} onChange={e => setSiteType(e.target.value)} placeholder="settlement, temple, tomb…" />
          </label>
        </div>
        <div className="radar-modal-row">
          <label className="radar-modal-label">Period start (year, neg. = BCE)
            <input className="radar-modal-input" value={periodStart} onChange={e => setPeriodStart(e.target.value)} inputMode="numeric" />
          </label>
          <label className="radar-modal-label">Period end
            <input className="radar-modal-input" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)} inputMode="numeric" />
          </label>
        </div>
        <label className={`radar-modal-label ${missingDesc ? 'radar-field-missing' : ''}`} title={CORE_HINT}>
          Description * ({description.trim().length}/50 min)
          <textarea className="radar-modal-textarea" rows={4} value={description} onChange={e => setDescription(e.target.value)} />
        </label>
        {error && <div className="radar-modal-error">{error}</div>}
        <div className="radar-modal-actions">
          <button className="radar-modal-btn radar-modal-cancel" onClick={onClose}>Cancel</button>
          <button className="radar-modal-btn radar-modal-confirm" disabled={!canSubmit} onClick={submit}>
            {submitting ? 'Adding…' : 'Add to database'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface SearchResult {
  id: string
  n: string
  s: string
  c?: string
}

interface MergeModalProps {
  itemName: string
  nearbyAnSite: { site_id: string; name: string; distance_km: number } | null
  onMerge: (siteId: string) => Promise<string | null>
  onClose: () => void
}

export function MergeModal({ itemName, nearbyAnSite, onMerge, onClose }: MergeModalProps) {
  const [query, setQuery] = useState(itemName)
  const [results, setResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submittingId, setSubmittingId] = useState<string | null>(null)

  // Monotonic request counter — a stale response must not overwrite a newer one
  const searchSeqRef = useRef(0)

  const search = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setResults([])
      return
    }
    const seq = ++searchSeqRef.current
    setSearching(true)
    try {
      const resp = await fetch(`${config.api.baseUrl}/sites/search?q=${encodeURIComponent(q.trim())}&limit=8`)
      if (resp.ok) {
        const data = await resp.json()
        if (seq === searchSeqRef.current) setResults(data.sites ?? [])
      }
    } catch {
      if (seq === searchSeqRef.current) setResults([])
    } finally {
      if (seq === searchSeqRef.current) setSearching(false)
    }
  }, [])

  useEffect(() => {
    const t = window.setTimeout(() => { void search(query) }, 300)
    return () => window.clearTimeout(t)
  }, [query, search])

  const pick = async (siteId: string) => {
    setSubmittingId(siteId)
    setError(null)
    const err = await onMerge(siteId)
    setSubmittingId(null)
    if (err) {
      setError(err)
    } else {
      onClose()
    }
  }

  return (
    <div className="radar-modal-overlay" onClick={onClose}>
      <div className="radar-modal" onClick={e => e.stopPropagation()}>
        <h3 className="radar-modal-title">Merge into existing site</h3>
        <p className="radar-modal-hint">
          "{itemName}" becomes an alias of the selected site — future news mentions
          will match it directly and this card will not come back.
        </p>
        {nearbyAnSite && (
          <button
            className="radar-merge-result radar-merge-nearby"
            disabled={submittingId !== null}
            onClick={() => pick(nearbyAnSite.site_id)}
          >
            <span className="radar-merge-name">{nearbyAnSite.name}</span>
            <span className="radar-merge-meta">AN Originals · {nearbyAnSite.distance_km} km away</span>
          </button>
        )}
        <input
          className="radar-modal-input"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search existing sites…"
        />
        {searching && <div className="radar-modal-hint">Searching…</div>}
        {results.filter(r => r.id !== nearbyAnSite?.site_id).map(r => (
          <button
            key={r.id}
            className="radar-merge-result"
            disabled={submittingId !== null}
            onClick={() => pick(r.id)}
          >
            <span className="radar-merge-name">{r.n}</span>
            <span className="radar-merge-meta">{r.s}{r.c ? ` · ${r.c}` : ''}</span>
          </button>
        ))}
        {error && <div className="radar-modal-error">{error}</div>}
        <div className="radar-modal-actions">
          <button className="radar-modal-btn radar-modal-cancel" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
