/**
 * ProposalsReview — the prospector's queue inside the Radar page.
 *
 * A proposal is a place named in our own papers, stories or the old radar,
 * resolved to a Wikidata entity where possible and checked against the
 * curated set. Every card shows WHY it was proposed (verbatim quotes with
 * deep links) and WHAT the dedup ladder checked before calling it new.
 * Founder-only: the API refuses without a founder token.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { config } from '../config'
import { formatCoord } from '../utils/formatters'
import { SiteBadges, CountryFlag, CopyButton } from './metadata'
import { ApproveModal, MergeModal } from './RadarReviewModals'
import type { SiteData } from '../data/sites'

interface Evidence {
  corpus: string
  source_pk: string
  mentioned_as: string
  quote: string
  locator: string
  footnotes: number[]
}

interface TraceEntry {
  rung: string
  site: string
  site_id: string
  source: string
  site_country: string | null
  distance_m: number | null
  signal: number | null
  same_name: boolean
  killed_by: string | null
  shared_tokens?: string[]
  [k: string]: unknown
}

export interface Proposal {
  id: string
  name: string
  aliases: string[]
  status: string
  place_class: string
  resolved_label: string | null
  wikidata_qid: string | null
  enwiki_title: string | null
  resolution_path: string | null
  resolution_note: string | null
  prior_verdict: string | null
  contribution_id: string | null
  lat: number | null
  lon: number | null
  coord_precision: number | null
  location_rung: string
  country: string | null
  country_in_text: string | null
  site_type: string | null
  period_start: number | null
  period_end: number | null
  period_name: string | null
  period_phrase: string | null
  description: string | null
  thumbnail_url: string | null
  wikipedia_url: string | null
  dedup_verdict: string
  dedup_trace: TraceEntry[]
  scope_verdict: string
  an_site_id: string | null
  external_site_id: string | null
  external_source_id: string | null
  promoted_site_id: string | null
  evidence_count: number
  corpus_kinds: string[]
  missing_core_fields: string[]
  evidence: Evidence[]
}

type ProposalStatus = 'review' | 'have_it' | 'approved' | 'merged' | 'rejected' | 'out_of_scope' | 'not_a_place'

const STATUS_CHIPS: Array<[ProposalStatus, string]> = [
  ['review', 'To review'],
  ['have_it', 'Already ours'],
  ['approved', 'Approved'],
  ['merged', 'Merged'],
  ['rejected', 'Rejected'],
  ['out_of_scope', 'Out of scope'],
  ['not_a_place', 'Not a place'],
]

const STATUS_PILL: Record<string, [string, string]> = {
  new: ['New', 'lyra-status-enriched'],
  needs_decision: ['Needs decision', 'lyra-confidence-medium'],
  have_it: ['Already ours', 'lyra-status-added'],
  approved: ['Approved', 'lyra-status-added'],
  merged: ['Merged', 'lyra-status-added'],
  rejected: ['Rejected', 'lyra-status-rejected'],
  out_of_scope: ['Out of scope', 'lyra-status-pending'],
  not_a_place: ['Not a place', 'lyra-status-pending'],
}

const CORPUS_LABEL: Record<string, string> = {
  paper: 'paper',
  story: 'story',
  radar: 'radar',
  entities_legacy: 'story (2026-03 index)',
}

const CORPUS_LINK: Record<string, string> = {
  paper: 'open in paper',
  story: 'watch',
  radar: 'watch',
  entities_legacy: 'watch',
}

function locationLabel(p: Proposal): string {
  if (p.location_rung === 'wikidata_p625') {
    const prec = p.coord_precision != null ? ` (precision ${p.coord_precision}°)` : ''
    return `coordinates from Wikidata${prec}`
  }
  if (p.location_rung === 'contribution') return 'coordinates from the radar’s own enrichment'
  if (p.location_rung.startsWith('external:')) return `coordinates from ${p.location_rung.slice(9)}`
  return 'no coordinates — you place the pin'
}

function nearestTraceHit(p: Proposal): { site_id: string; name: string; distance_km: number } | null {
  if (!p.an_site_id) return null
  const hit = p.dedup_trace.find(t => t.site_id === p.an_site_id)
  return { site_id: p.an_site_id, name: hit?.site ?? 'curated site', distance_km: hit?.distance_m != null ? Math.round(hit.distance_m / 100) / 10 : 0 }
}

function toSiteData(p: Proposal): SiteData {
  return {
    id: p.promoted_site_id || p.id,
    title: p.name,
    coordinates: [p.lon ?? NaN, p.lat ?? NaN],
    category: p.site_type || 'Unknown',
    period: p.period_name || 'Unknown',
    periodStart: p.period_start,
    location: p.country || '',
    description: p.description || '',
    sourceId: 'lyra',
    sourceUrl: p.wikipedia_url || undefined,
  }
}

function SameAsPicker({ p, candidates, onPick, onClose }: {
  p: Proposal
  candidates: Proposal[]
  onPick: (otherId: string) => Promise<string | null>
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    return candidates
      .filter(c => c.id !== p.id && (!q || c.name.toLowerCase().includes(q)))
      .slice(0, 8)
  }, [query, candidates, p.id])
  return (
    <div className="radar-modal-overlay" onClick={onClose}>
      <div className="radar-modal" onClick={e => e.stopPropagation()}>
        <h3 className="radar-modal-title">“{p.name}” is the same place as…</h3>
        <p className="radar-modal-hint">The other card folds into this one: its quotes move here, its name becomes an alias.</p>
        <input className="radar-modal-input" autoFocus placeholder="Type a name from the queue" value={query}
               onChange={e => setQuery(e.target.value)} />
        {matches.map(c => (
          <button key={c.id} className="radar-merge-result"
                  onClick={async () => { const err = await onPick(c.id); if (err) setError(err); else onClose() }}>
            <span>{c.name}</span>
            <span className="radar-merge-meta">{c.evidence_count} mention{c.evidence_count === 1 ? '' : 's'}{c.country ? ` · ${c.country}` : ''}</span>
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

function ProposalCard({ p, all, canReview, onViewSite, onApprove, onMerge, onSameAs, onReject }: {
  p: Proposal
  all: Proposal[]
  canReview: boolean
  onViewSite: (s: SiteData) => void
  onApprove: (id: string, overrides: Record<string, unknown>) => Promise<string | null>
  onMerge: (id: string, siteId: string) => Promise<string | null>
  onSameAs: (id: string, otherId: string) => Promise<string | null>
  onReject: (id: string) => Promise<void>
}) {
  const [traceOpen, setTraceOpen] = useState(false)
  const [allEvidence, setAllEvidence] = useState(false)
  const [showApprove, setShowApprove] = useState(false)
  const [showMerge, setShowMerge] = useState(false)
  const [showSameAs, setShowSameAs] = useState(false)
  const [confirmReject, setConfirmReject] = useState(false)
  const [pill, pillCls] = STATUS_PILL[p.status] ?? [p.status, 'lyra-status-pending']
  const nearest = nearestTraceHit(p)
  const evidence = allEvidence ? p.evidence : p.evidence.slice(0, 3)
  const open = p.status === 'new' || p.status === 'needs_decision'

  return (
    <div className="lyra-discovery-card">
      <div className="lyra-discovery-name-block">
        <h3 className="lyra-discovery-name">
          {p.name}
          <CopyButton text={p.name} title="Copy name" size={14} />
          <span className={`lyra-status-pill ${pillCls}`}>{pill}</span>
          {p.prior_verdict && (
            <span className="lyra-status-pill lyra-status-pending" title="A machine verdict from the old radar, not a human one">
              previously judged: {p.prior_verdict.replace(/_/g, ' ')}
            </span>
          )}
        </h3>
        {p.resolved_label && p.resolved_label !== p.name && (
          <span className="lyra-discovery-original-name">Wikidata label: {p.resolved_label}</span>
        )}
        {p.aliases.length > 0 && (
          <span className="lyra-discovery-original-name">Also named: {p.aliases.join(' · ')}</span>
        )}
      </div>

      {p.resolution_note && (
        <div className="lyra-discovery-rejection">{p.resolution_note}</div>
      )}
      {p.status === 'needs_decision' && nearest && (
        <div className="lyra-discovery-nearby-an">
          Possible duplicate of <strong>{nearest.name}</strong>
          {nearest.distance_km > 0 && <> ({nearest.distance_km} km away)</>} — decide below.
        </div>
      )}
      {p.status === 'have_it' && nearest && (
        <div className="lyra-discovery-nearby-an">Already in the curated set as <strong>{nearest.name}</strong>.</div>
      )}

      {(p.country || (p.lat != null && p.lon != null)) && (
        <div className="lyra-discovery-country-row">
          {p.country && <CountryFlag country={p.country} size="md" showName />}
          {p.lat != null && p.lon != null && (
            <span className="lyra-discovery-coords">
              {formatCoord(p.lat, true)}, {formatCoord(p.lon, false)}
              <CopyButton text={`${formatCoord(p.lat, true)}, ${formatCoord(p.lon, false)}`} title="Copy coordinates" />
            </span>
          )}
        </div>
      )}
      <div className="proposal-location">
        {locationLabel(p)}{!p.country && p.country_in_text ? ` · text says “${p.country_in_text}”` : ''}
      </div>
      <SiteBadges category={p.site_type} period={p.period_name} periodStart={p.period_start} size="md" />

      {p.thumbnail_url && (
        <div className="lyra-discovery-image-wrap lyra-image-clickable" onClick={() => onViewSite(toSiteData(p))}>
          <img src={p.thumbnail_url} alt="" className="lyra-discovery-image" loading="lazy" />
        </div>
      )}
      {p.description && (
        <div className="lyra-discovery-description-section">
          <p className="lyra-discovery-description lyra-description-clamped">{p.description}</p>
        </div>
      )}

      <div className="lyra-wiki-links-row">
        {p.wikipedia_url && (
          <a href={p.wikipedia_url} target="_blank" rel="noopener noreferrer" className="lyra-wiki-link">Wikipedia</a>
        )}
        {p.wikidata_qid && (
          <a href={`https://www.wikidata.org/wiki/${p.wikidata_qid}`} target="_blank" rel="noopener noreferrer" className="lyra-wiki-link lyra-wikidata-link">
            {p.wikidata_qid}
          </a>
        )}
        {p.resolution_path && p.resolution_path !== 'none' && (
          <span className="lyra-source-tag" title="How the entity was identified">resolved via {p.resolution_path}</span>
        )}
        {p.external_source_id && (
          <span className="lyra-source-tag" title="Also catalogued in an external source">also in {p.external_source_id}</span>
        )}
      </div>

      <div className="proposal-evidence">
        <div className="lyra-score-sources-label">
          Why it was proposed ({p.evidence_count} mention{p.evidence_count === 1 ? '' : 's'}
          {p.corpus_kinds.length > 0 && <> · {p.corpus_kinds.map(k => CORPUS_LABEL[k] ?? k).join(', ')}</>}):
        </div>
        {evidence.map((e, i) => (
          <blockquote key={i} className="proposal-quote">
            “{e.quote}”
            <a href={e.locator} target="_blank" rel="noopener noreferrer" className="proposal-quote-link">
              {CORPUS_LINK[e.corpus] ?? 'source'}
            </a>
          </blockquote>
        ))}
        {p.evidence.length > 3 && (
          <button className="lyra-collapsible-header" onClick={() => setAllEvidence(v => !v)}>
            {allEvidence ? 'show fewer' : `show all ${p.evidence.length}`}
          </button>
        )}
      </div>

      <div className="lyra-collapsible">
        <button className="lyra-collapsible-header" onClick={() => setTraceOpen(v => !v)}>
          <span className="lyra-collapsible-arrow">{traceOpen ? '▾' : '▸'}</span>
          What was checked · verdict: {p.dedup_verdict} ({p.dedup_trace.length})
        </button>
        {traceOpen && (
          <div className="proposal-trace">
            {p.dedup_trace.length === 0 && <div className="lyra-source-empty">no curated site came close on name, spelling or location</div>}
            {p.dedup_trace.map((t, i) => (
              <div key={i} className={`proposal-trace-row${t.killed_by ? ' killed' : ''}`}>
                <span className="proposal-trace-rung">{t.rung}</span>
                <span>{t.site}</span>
                {t.site_country && <span className="lyra-source-empty">{t.site_country}</span>}
                {t.signal != null && <span className="lyra-source-empty">signal {t.signal}</span>}
                {t.distance_m != null && <span className="lyra-source-empty">{t.distance_m >= 1000 ? `${Math.round(t.distance_m / 1000)} km` : `${t.distance_m} m`}</span>}
                {t.same_name && <span className="lyra-source-tag">same name</span>}
                {t.killed_by && <span className="proposal-trace-killed">✕ {t.killed_by}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {open && p.missing_core_fields.length > 0 && (
        <div className="radar-modal-warning">
          Approve needs: {p.missing_core_fields.join(', ')} — fill them in the approve form.
        </div>
      )}

      {canReview && open && (
        <div className="radar-review-actions">
          <button className="lyra-promote-btn" onClick={() => setShowApprove(true)}>Approve</button>
          <button className="radar-merge-btn" onClick={() => setShowMerge(true)} title="This is an existing site in the database">Merge</button>
          <button className="radar-merge-btn" onClick={() => setShowSameAs(true)} title="Another card in this queue names the same place">Same as…</button>
          {confirmReject ? (
            <button className="radar-dismiss-btn radar-dismiss-confirm" onBlur={() => setConfirmReject(false)}
                    onClick={() => { setConfirmReject(false); onReject(p.id) }}>
              Confirm reject?
            </button>
          ) : (
            <button className="radar-dismiss-btn" onClick={() => setConfirmReject(true)}>Reject</button>
          )}
        </div>
      )}

      {showApprove && (
        <ApproveModal
          item={{
            display_name: p.name, lat: p.lat, lon: p.lon, country: p.country, site_type: p.site_type,
            period_start: p.period_start, period_end: p.period_end, description: p.description,
            nearby_an_site: nearest,
          } as never}
          onSubmit={(overrides) => onApprove(p.id, overrides)}
          onClose={() => setShowApprove(false)}
        />
      )}
      {showMerge && (
        <MergeModal itemName={p.name} nearbyAnSite={nearest}
                    onMerge={(siteId) => onMerge(p.id, siteId)} onClose={() => setShowMerge(false)} />
      )}
      {showSameAs && (
        <SameAsPicker p={p} candidates={all} onPick={(otherId) => onSameAs(p.id, otherId)} onClose={() => setShowSameAs(false)} />
      )}
    </div>
  )
}

export default function ProposalsReview({ token, isFounder, onViewSite, columnCount }: {
  token: string | null
  isFounder: boolean
  onViewSite: (s: SiteData) => void
  columnCount: number
}) {
  const [status, setStatus] = useState<ProposalStatus>('review')
  const [items, setItems] = useState<Proposal[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const headers = useCallback((json = false): HeadersInit => ({
    Authorization: `Bearer ${token}`,
    ...(json ? { 'Content-Type': 'application/json' } : {}),
  }), [token])

  const load = useCallback(async () => {
    if (!token) { setError('Sign in as a founder to review proposals.'); return }
    setLoading(true); setError(null)
    try {
      const r = await fetch(`${config.api.baseUrl}/proposals?status=${status}&limit=500`, { headers: headers() })
      if (!r.ok) throw new Error(r.status === 403 ? 'Founder access required.' : `HTTP ${r.status}`)
      const d = await r.json()
      setItems(d.items); setCounts(d.counts); setTotal(d.total_count)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [token, status, headers])

  useEffect(() => { load() }, [load])

  const post = useCallback(async (path: string, body?: unknown): Promise<string | null> => {
    const r = await fetch(`${config.api.baseUrl}/proposals/${path}`, {
      method: 'POST', headers: headers(body !== undefined), ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }))
      return typeof d.detail === 'object' && d.detail?.message ? d.detail.message : String(d.detail || r.statusText)
    }
    return null
  }, [headers])

  const drop = (id: string) => setItems(prev => prev.filter(p => p.id !== id))
  const onApprove = async (id: string, overrides: Record<string, unknown>) => {
    const err = await post(`${id}/approve`, Object.keys(overrides).length ? overrides : undefined)
    if (!err) { drop(id); load() }
    return err
  }
  const onMerge = async (id: string, siteId: string) => {
    const err = await post(`${id}/merge/${siteId}`)
    if (!err) { drop(id); load() }
    return err
  }
  const onSameAs = async (id: string, otherId: string) => {
    const err = await post(`${id}/same-as/${otherId}`)
    if (!err) { drop(otherId); load() }
    return err
  }
  const onReject = async (id: string) => {
    const err = await post(`${id}/reject`)
    if (err) alert(`Reject failed: ${err}`); else { drop(id); load() }
  }

  const reviewCount = (counts.new ?? 0) + (counts.needs_decision ?? 0)

  return (
    <div className="proposals-review">
      <div className="lyra-filter-group proposals-filter">
        <div className="lyra-discoveries-filter-chips">
          {STATUS_CHIPS.map(([val, label]) => {
            const n = val === 'review' ? reviewCount : (counts[val] ?? 0)
            return (
              <button key={val} className={`news-page-chip${status === val ? ' active' : ''}`} onClick={() => setStatus(val)}>
                {label}{n ? ` ${n}` : ''}
              </button>
            )
          })}
        </div>
      </div>
      {error && <div className="news-page-error">{error}</div>}
      {!error && !loading && items.length === 0 && (
        <div className="news-page-empty">Nothing here. {status === 'review' ? 'The queue is empty.' : ''}</div>
      )}
      <div className="lyra-discoveries-grid">
        {Array.from({ length: columnCount }, (_, col) => (
          <div key={col} className="lyra-discoveries-column">
            {items.filter((_, i) => i % columnCount === col).map(p => (
              <ProposalCard key={p.id} p={p} all={items} canReview={isFounder} onViewSite={onViewSite}
                            onApprove={onApprove} onMerge={onMerge} onSameAs={onSameAs} onReject={onReject} />
            ))}
          </div>
        ))}
      </div>
      {loading && <div className="news-page-loading">Loading…</div>}
      {!loading && total > items.length && <div className="news-page-empty">Showing {items.length} of {total}.</div>}
    </div>
  )
}
