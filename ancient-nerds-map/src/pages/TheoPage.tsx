/**
 * TheoPage — Theodore Furcade Research Lab.
 * Async research agent: submit a question, pick effort, get a structured report.
 * Accessed via /theo.html (separate Vite entry point).
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { formatDurationMs, timeAgo } from '../utils/formatters'
import PageHeader from '../components/layout/PageHeader'
import '../styles/theo.css'

const TheoReportOverlay = lazy(() => import('../components/theo/TheoReportOverlay'))
const TheoResearchLive = lazy(() => import('../components/theo/TheoResearchLive'))

const EFFORTS = [
  { key: 'brief', label: 'Brief', time: '~2 min' },
  { key: 'paper', label: 'Paper', time: '~5-8 min' },
  { key: 'thesis', label: 'Thesis', time: '~15 min' },
] as const

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
  const [question, setQuestion] = useState('')
  const [effort, setEffort] = useState<string>('auto')
  const [submitting, setSubmitting] = useState(false)
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

  // Request notification permission on load
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

      // Check for newly completed items → browser notification
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
      // Update prev status
      const map = new Map<string, string>()
      for (const item of data) map.set(item.id, item.status)
      prevStatusRef.current = map
    } catch {
      // ignore
    }
  }, [notifGranted])

  // Poll every 10s
  useEffect(() => {
    fetchList()
    pollRef.current = setInterval(fetchList, 10000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [fetchList])

  // Submit
  const handleSubmit = useCallback(async () => {
    if (question.trim().length < 10 || submitting) return
    setSubmitting(true)
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ question: question.trim(), effort }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed to submit' }))
        alert(err.detail || 'Failed to submit')
        return
      }
      setQuestion('')
      fetchList()
    } finally {
      setSubmitting(false)
    }
  }, [question, effort, submitting, fetchList])

  // Cancel
  const handleCancel = useCallback(async (id: string) => {
    try {
      await fetch(`${config.api.baseUrl}/theo/research/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      fetchList()
    } catch {
      // ignore
    }
  }, [fetchList])

  // Retry (resubmit same question/effort)
  const handleRetry = useCallback(async (item: ResearchItem) => {
    try {
      await fetch(`${config.api.baseUrl}/theo/research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ question: item.question, effort: item.effort }),
      })
      fetchList()
    } catch {
      // ignore
    }
  }, [fetchList])

  // View report
  const handleView = useCallback(async (id: string) => {
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/research/${id}`, {
        headers: getAuthHeaders(),
      })
      if (!resp.ok) return
      const data: FullResearch = await resp.json()
      setViewingData(data)
      setViewingId(id)
    } catch {
      // ignore
    }
  }, [])

  const handleCloseReport = useCallback(() => {
    setViewingId(null)
    setViewingData(null)
  }, [])

  // Auto-open live overlay when research is running
  useEffect(() => {
    const running = items.find(i => i.status === 'running' && !liveOverlayClosed.has(i.id))
    if (running && liveOverlayId !== running.id) {
      setLiveOverlayId(running.id)
      setLiveOverlayQuestion(running.question)
    } else if (!running && liveOverlayId && !items.find(i => i.id === liveOverlayId && i.status === 'running')) {
      // Research finished — keep overlay open so user can see final result
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

  // Key handler for textarea submit
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }, [handleSubmit])

  const selectedEffort = EFFORTS.find(e => e.key === effort)

  // Split items into active and completed
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
          <div className="theo-avatar-placeholder">🐻</div>
          <div>
            <h1 className="theo-title">Theodore Furcade</h1>
            <div className="theo-subtitle">Archaeological Research Specialist</div>
          </div>
        </div>
        <div className="theo-quote">"Give me a question. I'll dig deep."</div>
      </div>

      {/* Submit Form */}
      <div className="theo-form">
        <div className="theo-input-wrap">
          <textarea
            ref={inputRef}
            className="theo-input"
            placeholder="What should Theo investigate?"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
          />
        </div>

        <div className="theo-effort-row">
          <span className="theo-effort-label">Effort</span>
          {EFFORTS.map(e => (
            <button
              key={e.key}
              className={`theo-effort-btn${effort === e.key ? ' active' : ''}`}
              onClick={() => setEffort(e.key)}
            >
              {e.label}
            </button>
          ))}
          <span className="theo-effort-time">
            {selectedEffort?.time}
          </span>
        </div>

        <div className="theo-submit-row">
          <button
            className="theo-submit-btn"
            disabled={question.trim().length < 10 || submitting}
            onClick={handleSubmit}
          >
            {submitting ? 'Submitting...' : 'Submit Research Request'}
          </button>
        </div>
      </div>

      {/* Active Queue */}
      {activeItems.length > 0 && (
        <div className="theo-list">
          <div className="theo-list-header">Active ({activeItems.length})</div>
          {activeItems.map(item => (
            <div key={item.id} className="theo-card">
              <div className="theo-card-top">
                <span className="theo-card-question">{item.question}</span>
                <span className="theo-badge theo-badge-effort">{item.effort}</span>
                <span className={`theo-badge theo-badge-status theo-badge-${item.status}`}>
                  {item.status === 'running' ? '● Running' : `#${activeItems.indexOf(item) + 1} Queued`}
                </span>
              </div>
              {item.status === 'running' && (
                <div className="theo-card-actions">
                  <button className="theo-btn-view" onClick={() => handleWatchLive(item)}>
                    Watch Live
                  </button>
                  <button className="theo-btn-cancel" onClick={() => handleCancel(item.id)}>
                    Cancel
                  </button>
                </div>
              )}
              {item.status === 'queued' && (
                <div className="theo-card-actions">
                  <button className="theo-btn-cancel" onClick={() => handleCancel(item.id)}>
                    Cancel
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Completed */}
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
                  {item.status === 'completed' ? '✓ Done' :
                   item.status === 'failed' ? '✗ Failed' :
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
                  <button className="theo-btn-view" onClick={() => handleView(item.id)}>
                    View Report
                  </button>
                )}
                {item.status === 'failed' && (
                  <>
                    <button className="theo-btn-retry" onClick={() => handleRetry(item)}>
                      Retry
                    </button>
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
