/**
 * TheoPage — Theodore Furcade Research Lab.
 * 3-stage research wizard: Topic+Scope -> Specialists -> Review+Launch
 * Plus results list with live streaming and report overlays.
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { formatDurationMs, timeAgo } from '../utils/formatters'
import PageHeader from '../components/layout/PageHeader'
import '../styles/theo.css'

const TheoReportOverlay = lazy(() => import('../components/theo/TheoReportOverlay'))
const TheoResearchLive = lazy(() => import('../components/theo/TheoResearchLive'))

const EFFORTS = [
  { key: 'brief', label: 'Research Brief', time: '~3 min', desc: 'Quick literature overview' },
  { key: 'note', label: 'Research Note', time: '~8 min', desc: '3 specialists, structured analysis' },
  { key: 'article', label: 'Journal Article', time: '~20 min', desc: '5 specialists, full debate' },
  { key: 'review', label: 'Literature Review', time: '~40 min', desc: '6 specialists, comprehensive' },
  { key: 'thesis', label: 'Thesis Chapter', time: '~60 min', desc: '8 specialists, multi-round debate' },
] as const

interface SpecialistInfo {
  id: string
  name: string
  title: string
  domain: string
  perspective: string
}

interface SpecialistCategories {
  'Archaeological Core': SpecialistInfo[]
  'Interdisciplinary Science': SpecialistInfo[]
  'Fringe / Alternative': SpecialistInfo[]
}

interface ResearchItem {
  id: string
  question: string
  effort: string
  status: string
  sites_found: number
  tools_used: number
  duration_ms: number | null
  error_message: string | null
  created_at: string | null
  completed_at: string | null
}

interface FullResearch extends ResearchItem {
  result: { report: string; sites_found: number; tools_used: number; total_tokens: number; effort: string; duration_ms: number } | null
  pipeline_trace: Array<{ stage?: string; status?: string; duration_ms?: number }> | null
  total_tokens: number
}

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('an_auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}


export default function TheoPage() {
  // Wizard state
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3>(1)
  const [question, setQuestion] = useState('')
  const [effort, setEffort] = useState<string>('article')

  // Stage 1: relevance check
  const [checkingRelevance, setCheckingRelevance] = useState(false)
  const [relevanceResult, setRelevanceResult] = useState<{ relevant: boolean; reason: string } | null>(null)

  // Stage 2: specialists
  const [specialistMode, setSpecialistMode] = useState<'auto' | 'manual'>('auto')
  const [specialistData, setSpecialistData] = useState<SpecialistCategories | null>(null)
  const [selectedSpecialists, setSelectedSpecialists] = useState<Set<string>>(new Set())
  const [excludedSpecialists, setExcludedSpecialists] = useState<Set<string>>(new Set())
  const [loadingSpecialists, setLoadingSpecialists] = useState(false)

  // Submission
  const [submitting, setSubmitting] = useState(false)

  // Results list
  const [items, setItems] = useState<ResearchItem[]>([])
  const [viewingId, setViewingId] = useState<string | null>(null)
  const [viewingData, setViewingData] = useState<FullResearch | null>(null)
  const [notifGranted, setNotifGranted] = useState(false)
  const [liveOverlayId, setLiveOverlayId] = useState<string | null>(null)
  const [liveOverlayQuestion, setLiveOverlayQuestion] = useState('')
  const [liveOverlayClosed, setLiveOverlayClosed] = useState<Set<string>>(new Set())

  const inputRef = useRef<HTMLTextAreaElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevStatusRef = useRef<Map<string, string>>(new Map())

  // Request notification permission
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().then(p => setNotifGranted(p === 'granted'))
    } else if ('Notification' in window) {
      setNotifGranted(Notification.permission === 'granted')
    }
  }, [])

  // Fetch research list
  const fetchList = useCallback(async () => {
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/research`, {
        headers: getAuthHeaders(),
      })
      if (!resp.ok) return
      const data: ResearchItem[] = await resp.json()
      setItems(data)

      if (notifGranted) {
        for (const item of data) {
          const prev = prevStatusRef.current.get(item.id)
          if (prev && prev !== 'completed' && item.status === 'completed') {
            new Notification('Theo finished his research', {
              body: item.question.substring(0, 100),
            })
          }
        }
      }
      const map = new Map<string, string>()
      for (const item of data) map.set(item.id, item.status)
      prevStatusRef.current = map
    } catch { /* ignore */ }
  }, [notifGranted])

  // Poll every 10s
  useEffect(() => {
    fetchList()
    pollRef.current = setInterval(fetchList, 10000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [fetchList])

  // Load specialists on first visit to step 2
  const loadSpecialists = useCallback(async () => {
    if (specialistData) return
    setLoadingSpecialists(true)
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/specialists`)
      if (resp.ok) {
        const data: SpecialistCategories = await resp.json()
        setSpecialistData(data)
        // Default: all selected
        const allIds = new Set<string>()
        for (const specs of Object.values(data)) {
          for (const s of specs) allIds.add(s.id)
        }
        setSelectedSpecialists(allIds)
      }
    } catch { /* ignore */ }
    setLoadingSpecialists(false)
  }, [specialistData])

  // --- Stage 1: Check Relevance ---
  const handleCheckTopic = useCallback(async () => {
    if (question.trim().length < 10) return
    setCheckingRelevance(true)
    setRelevanceResult(null)
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/check-relevance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ question: question.trim() }),
      })
      if (resp.ok) {
        const data = await resp.json()
        setRelevanceResult(data)
      } else {
        setRelevanceResult({ relevant: false, reason: 'Failed to check relevance' })
      }
    } catch {
      setRelevanceResult({ relevant: false, reason: 'Network error' })
    }
    setCheckingRelevance(false)
  }, [question])

  // --- Stage 2 transition ---
  const goToStep2 = useCallback(() => {
    setWizardStep(2)
    loadSpecialists()
  }, [loadSpecialists])

  // --- Stage 3: Submit ---
  const handleSubmit = useCallback(async () => {
    if (question.trim().length < 10 || submitting) return
    setSubmitting(true)
    try {
      const body: Record<string, unknown> = {
        question: question.trim(),
        effort,
      }
      if (specialistMode === 'manual') {
        // All specialists in the pool
        const allIds = specialistData
          ? Object.values(specialistData).flat().map(s => s.id)
          : []
        const forceInclude = allIds.filter(id => selectedSpecialists.has(id) && !excludedSpecialists.has(id))
        const forceExclude = allIds.filter(id => excludedSpecialists.has(id))
        if (forceInclude.length > 0) body.force_include = forceInclude
        if (forceExclude.length > 0) body.force_exclude = forceExclude
      }

      const resp = await fetch(`${config.api.baseUrl}/theo/research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed to submit' }))
        alert(err.detail || 'Failed to submit')
        return
      }
      // Reset wizard
      setQuestion('')
      setWizardStep(1)
      setRelevanceResult(null)
      setSpecialistMode('auto')
      fetchList()
    } finally {
      setSubmitting(false)
    }
  }, [question, effort, submitting, specialistMode, selectedSpecialists, excludedSpecialists, specialistData, fetchList])

  // --- Result actions ---
  const handleCancel = useCallback(async (id: string) => {
    try {
      await fetch(`${config.api.baseUrl}/theo/research/${id}`, {
        method: 'DELETE', headers: getAuthHeaders(),
      })
      fetchList()
    } catch { /* ignore */ }
  }, [fetchList])

  const handleRetry = useCallback(async (item: ResearchItem) => {
    try {
      await fetch(`${config.api.baseUrl}/theo/research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ question: item.question, effort: item.effort }),
      })
      fetchList()
    } catch { /* ignore */ }
  }, [fetchList])

  const handleView = useCallback(async (id: string) => {
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/research/${id}`, {
        headers: getAuthHeaders(),
      })
      if (!resp.ok) return
      const data: FullResearch = await resp.json()
      setViewingData(data)
      setViewingId(id)
    } catch { /* ignore */ }
  }, [])

  const handleCloseReport = useCallback(() => {
    setViewingId(null)
    setViewingData(null)
  }, [])

  // Auto-open live overlay for running research
  useEffect(() => {
    const running = items.find(i => i.status === 'running' && !liveOverlayClosed.has(i.id))
    if (running && liveOverlayId !== running.id) {
      setLiveOverlayId(running.id)
      setLiveOverlayQuestion(running.question)
    }
  }, [items, liveOverlayClosed, liveOverlayId])

  const handleCloseLive = useCallback(() => {
    if (liveOverlayId) {
      setLiveOverlayClosed(prev => new Set(prev).add(liveOverlayId))
    }
    setLiveOverlayId(null)
    setLiveOverlayQuestion('')
  }, [liveOverlayId])

  const handleWatchLive = useCallback((item: ResearchItem) => {
    setLiveOverlayClosed(prev => {
      const next = new Set(prev)
      next.delete(item.id)
      return next
    })
    setLiveOverlayId(item.id)
    setLiveOverlayQuestion(item.question)
  }, [])

  // Toggle specialist in manual mode
  const toggleSpecialist = useCallback((id: string) => {
    setExcludedSpecialists(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const selectedEffort = EFFORTS.find(e => e.key === effort)
  const activeItems = items.filter(i => i.status === 'queued' || i.status === 'running')
  const doneItems = items.filter(i => i.status !== 'queued' && i.status !== 'running')

  return (
    <div className="theo-page">
      <PageHeader currentPage="theo">
        <span style={{ fontSize: 12, color: 'var(--theo-amber, #d4912a)', letterSpacing: 1 }}>
          Research Lab
        </span>
      </PageHeader>

      {/* Hero */}
      <div className="theo-hero">
        <div className="theo-avatar-row">
          <div className="theo-avatar-placeholder">&#x1f43b;</div>
          <div>
            <h1 className="theo-title">Theodore Furcade</h1>
            <div className="theo-subtitle">Archaeological Research Specialist</div>
          </div>
        </div>
        <div className="theo-quote">"Give me a question. I'll dig deep."</div>
      </div>

      {/* Wizard Steps Indicator */}
      <div className="theo-wizard-steps">
        <div className={`theo-step-dot ${wizardStep >= 1 ? 'active' : ''}`}>
          <span className="theo-step-num">1</span>
          <span className="theo-step-label">Topic</span>
        </div>
        <div className="theo-step-line" />
        <div className={`theo-step-dot ${wizardStep >= 2 ? 'active' : ''}`}>
          <span className="theo-step-num">2</span>
          <span className="theo-step-label">Specialists</span>
        </div>
        <div className="theo-step-line" />
        <div className={`theo-step-dot ${wizardStep >= 3 ? 'active' : ''}`}>
          <span className="theo-step-num">3</span>
          <span className="theo-step-label">Launch</span>
        </div>
      </div>

      {/* ═══════ STAGE 1: Topic + Scope ═══════ */}
      {wizardStep === 1 && (
        <div className="theo-form">
          <div className="theo-input-wrap">
            <textarea
              ref={inputRef}
              className="theo-input"
              placeholder="What should Theo investigate?"
              value={question}
              onChange={e => { setQuestion(e.target.value); setRelevanceResult(null) }}
              rows={3}
            />
          </div>

          {/* Tier selector */}
          <div className="theo-scope-section">
            <div className="theo-scope-label">Scope</div>
            <div className="theo-scope-grid">
              {EFFORTS.map(e => (
                <button
                  key={e.key}
                  className={`theo-scope-card${effort === e.key ? ' active' : ''}`}
                  onClick={() => setEffort(e.key)}
                >
                  <span className="theo-scope-name">{e.label}</span>
                  <span className="theo-scope-time">{e.time}</span>
                  <span className="theo-scope-desc">{e.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Relevance check */}
          <div className="theo-relevance-row">
            <button
              className="theo-check-btn"
              disabled={question.trim().length < 10 || checkingRelevance}
              onClick={handleCheckTopic}
            >
              {checkingRelevance ? 'Checking...' : 'Check Topic'}
            </button>

            {relevanceResult && (
              <div className={`theo-relevance-result ${relevanceResult.relevant ? 'relevant' : 'irrelevant'}`}>
                {relevanceResult.relevant
                  ? 'Topic accepted'
                  : relevanceResult.reason}
              </div>
            )}

            {relevanceResult?.relevant && (
              <button className="theo-next-btn" onClick={goToStep2}>
                Next
              </button>
            )}
          </div>
        </div>
      )}

      {/* ═══════ STAGE 2: Specialist Selection ═══════ */}
      {wizardStep === 2 && (
        <div className="theo-form">
          <div className="theo-stage-header">
            <button className="theo-back-btn" onClick={() => setWizardStep(1)}>Back</button>
            <span className="theo-stage-title">Specialist Panel</span>
          </div>

          <div className="theo-specialist-toggle">
            <button
              className={`theo-toggle-btn ${specialistMode === 'auto' ? 'active' : ''}`}
              onClick={() => setSpecialistMode('auto')}
            >
              Auto-select
            </button>
            <button
              className={`theo-toggle-btn ${specialistMode === 'manual' ? 'active' : ''}`}
              onClick={() => setSpecialistMode('manual')}
            >
              Choose manually
            </button>
          </div>

          {specialistMode === 'auto' && (
            <div className="theo-auto-info">
              Specialists are chosen automatically based on your question's domain. The{' '}
              <strong>{selectedEffort?.label}</strong> tier uses{' '}
              <strong>{selectedEffort?.key === 'brief' ? '1' : selectedEffort?.key === 'note' ? '3' : selectedEffort?.key === 'article' ? '5' : selectedEffort?.key === 'review' ? '6' : '8'}</strong>{' '}
              specialists.
            </div>
          )}

          {specialistMode === 'manual' && (
            <div className="theo-specialist-pool">
              {loadingSpecialists && <div className="theo-auto-info">Loading specialists...</div>}
              {specialistData && (Object.entries(specialistData) as [string, SpecialistInfo[]][]).map(([category, specs]) => (
                <div key={category} className="theo-spec-category">
                  <div className="theo-spec-category-label">
                    {category} ({specs.length})
                  </div>
                  <div className="theo-spec-grid">
                    {specs.map(s => {
                      const excluded = excludedSpecialists.has(s.id)
                      return (
                        <button
                          key={s.id}
                          className={`theo-spec-card ${excluded ? 'excluded' : 'included'}`}
                          onClick={() => toggleSpecialist(s.id)}
                          title={s.perspective}
                        >
                          <span className="theo-spec-name">{s.name}</span>
                          <span className="theo-spec-title">{s.title}</span>
                          <span className="theo-spec-domain">{s.domain}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="theo-submit-row">
            <button className="theo-next-btn" onClick={() => setWizardStep(3)}>
              Next
            </button>
          </div>
        </div>
      )}

      {/* ═══════ STAGE 3: Review + Launch ═══════ */}
      {wizardStep === 3 && (
        <div className="theo-form">
          <div className="theo-stage-header">
            <button className="theo-back-btn" onClick={() => setWizardStep(2)}>Back</button>
            <span className="theo-stage-title">Review & Launch</span>
          </div>

          <div className="theo-review-summary">
            <div className="theo-review-item">
              <span className="theo-review-label">Question</span>
              <span className="theo-review-value">{question}</span>
            </div>
            <div className="theo-review-item">
              <span className="theo-review-label">Scope</span>
              <span className="theo-review-value">
                {selectedEffort?.label} ({selectedEffort?.time})
              </span>
            </div>
            <div className="theo-review-item">
              <span className="theo-review-label">Specialists</span>
              <span className="theo-review-value">
                {specialistMode === 'auto'
                  ? 'Auto-selected based on question'
                  : `Manual: ${(specialistData ? Object.values(specialistData).flat().length : 0) - excludedSpecialists.size} included, ${excludedSpecialists.size} excluded`}
              </span>
            </div>
          </div>

          <div className="theo-tips">
            <div className="theo-tips-label">Tips for better results</div>
            <ul className="theo-tips-list">
              <li>Name specific sites, periods, and civilizations</li>
              <li>Include the hypothesis you want investigated</li>
              <li>Mention specific texts or sources if relevant</li>
              <li>Ask about competing theories to get debate</li>
            </ul>
          </div>

          <div className="theo-submit-row">
            <button
              className="theo-submit-btn"
              disabled={submitting}
              onClick={handleSubmit}
            >
              {submitting ? 'Submitting...' : 'Start Research'}
            </button>
          </div>
        </div>
      )}

      {/* ═══════ Active Queue ═══════ */}
      {activeItems.length > 0 && (
        <div className="theo-list">
          <div className="theo-list-header">Active ({activeItems.length})</div>
          {activeItems.map(item => (
            <div key={item.id} className="theo-card">
              <div className="theo-card-top">
                <span className="theo-card-question">{item.question}</span>
                <span className="theo-badge theo-badge-effort">{item.effort}</span>
                <span className={`theo-badge theo-badge-status theo-badge-${item.status}`}>
                  {item.status === 'running' ? '&#x25cf; Running' : `#${activeItems.indexOf(item) + 1} Queued`}
                </span>
              </div>
              {item.status === 'running' && (
                <div className="theo-card-actions">
                  <button className="theo-btn-view" onClick={() => handleWatchLive(item)}>Watch Live</button>
                  <button className="theo-btn-cancel" onClick={() => handleCancel(item.id)}>Cancel</button>
                </div>
              )}
              {item.status === 'queued' && (
                <div className="theo-card-actions">
                  <button className="theo-btn-cancel" onClick={() => handleCancel(item.id)}>Cancel</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ═══════ Completed Results ═══════ */}
      <div className="theo-list">
        <div className="theo-list-header">
          {doneItems.length > 0 ? `Results (${doneItems.length})` : 'Results'}
        </div>
        {doneItems.length === 0 ? (
          <div className="theo-empty">
            No research results yet. Submit a question above and Theo will investigate.
          </div>
        ) : (
          doneItems.map(item => (
            <div key={item.id} className="theo-card">
              <div className="theo-card-top">
                <span className="theo-card-question">{item.question}</span>
                <span className="theo-badge theo-badge-effort">{item.effort}</span>
                <span className={`theo-badge theo-badge-status theo-badge-${item.status}`}>
                  {item.status === 'completed' ? 'Done' :
                   item.status === 'failed' ? 'Failed' :
                   item.status === 'cancelled' ? 'Cancelled' : item.status}
                </span>
              </div>
              <div className="theo-card-meta">
                {item.duration_ms != null && <span>{formatDurationMs(item.duration_ms)}</span>}
                {item.sites_found > 0 && <span>{item.sites_found} sites</span>}
                {item.tools_used > 0 && <span>{item.tools_used} tools</span>}
                {item.created_at && <span>{timeAgo(item.created_at)}</span>}
              </div>
              <div className="theo-card-actions">
                {item.status === 'completed' && (
                  <button className="theo-btn-view" onClick={() => handleView(item.id)}>View Report</button>
                )}
                {item.status === 'failed' && (
                  <>
                    <button className="theo-btn-retry" onClick={() => handleRetry(item)}>Retry</button>
                    {item.error_message && (
                      <span style={{ fontSize: 10, color: 'var(--status-error-soft)', marginLeft: 4 }}>
                        {item.error_message.substring(0, 80)}
                      </span>
                    )}
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Report Overlay */}
      {viewingId && viewingData?.result && (
        <Suspense fallback={null}>
          <TheoReportOverlay
            question={viewingData.question}
            result={viewingData.result}
            pipelineTrace={viewingData.pipeline_trace}
            effort={viewingData.effort}
            durationMs={viewingData.duration_ms}
            sitesFound={viewingData.sites_found}
            toolsUsed={viewingData.tools_used}
            onClose={handleCloseReport}
          />
        </Suspense>
      )}

      {/* Live Research Overlay */}
      {liveOverlayId && (
        <Suspense fallback={null}>
          <TheoResearchLive
            requestId={liveOverlayId}
            question={liveOverlayQuestion}
            onClose={handleCloseLive}
          />
        </Suspense>
      )}
    </div>
  )
}
