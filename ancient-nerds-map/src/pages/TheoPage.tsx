/**
 * TheoPage — Theodore Furcade Research Lab.
 * 4-stage research wizard: Topic -> Sources -> Specialists -> Launch
 * Plus results list with live streaming and report overlays.
 * Auth-gated: logged-out users see the public library; logged-in users get the full wizard.
 */

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react'
import { config } from '../config'
import { formatDurationMs, timeAgo } from '../utils/formatters'
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
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

const EFFORT_LABELS: Record<string, string> = {
  brief: 'Brief', note: 'Note', article: 'Article', review: 'Review', thesis: 'Thesis',
}

const SPECIALIST_COUNTS: Record<string, number> = {
  brief: 1, note: 3, article: 5, review: 6, thesis: 8,
}

const ADAPTER_GROUP_ORDER = ['internal', 'academic', 'heritage', 'web'] as const
const ADAPTER_GROUP_LABELS: Record<string, string> = {
  internal: 'Internal',
  academic: 'Academic',
  heritage: 'Heritage',
  web: 'Web',
}

interface AuthUser {
  username: string
  discord_id: string
  avatar_url: string | null
  has_researcher_role: boolean
}

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

interface AdapterInfo {
  label: string
  icon: string
  favicon: string
  group: string
}

type AdapterData = Record<string, AdapterInfo>

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
  is_public: boolean
}

interface FullResearch extends ResearchItem {
  result: { report: string; sites_found: number; tools_used: number; total_tokens: number; effort: string; duration_ms: number } | null
  pipeline_trace: Array<{ stage?: string; status?: string; duration_ms?: number }> | null
  total_tokens: number
}

interface DuplicateMatch {
  paper_title: string
  paper_slug: string
  author_username: string
  score: number
  best_section_title: string
  effort: string
}

interface PublicPaper {
  id: string
  slug: string
  title: string
  question: string
  published_by: string
  author_avatar: string | null
  effort: string
  published_at: string
  sites_found: number
  duration_ms: number | null
  card_description: string
  cover_url: string
}

interface PublicPaperFull {
  slug: string
  question: string
  effort: string
  published_by: string
  published_at: string
  result: { report: string; title?: string; sites_found: number; tools_used: number; total_tokens: number; effort: string; duration_ms: number }
  sites_found: number
  tools_used: number
  duration_ms: number | null
}

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('an_auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}


export default function TheoPage() {
  // Auth state
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [authChecked, setAuthChecked] = useState(false)

  // Wizard state — 4 steps: Topic, Sources, Specialists, Launch
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3 | 4>(1)
  const [question, setQuestion] = useState(() => sessionStorage.getItem('theo_question') || '')
  const [effort, setEffort] = useState<string>(() => sessionStorage.getItem('theo_effort') || 'article')

  // Stage 2: YouTube video IDs
  const [videoIds, setVideoIds] = useState<string[]>(() => {
    try { return JSON.parse(sessionStorage.getItem('theo_video_ids') || '[]') } catch { return [] }
  })
  const [videoInput, setVideoInput] = useState('')

  // Stage 2: source adapters
  const [adapterData, setAdapterData] = useState<AdapterData | null>(null)
  const [loadingAdapters, setLoadingAdapters] = useState(false)
  const [disabledAdapters, setDisabledAdapters] = useState<Set<string>>(() => {
    try {
      const saved = sessionStorage.getItem('theo_disabled_adapters')
      return saved ? new Set<string>(JSON.parse(saved)) : new Set<string>()
    } catch { return new Set<string>() }
  })

  // Stage 1: relevance check
  const [checkingRelevance, setCheckingRelevance] = useState(false)
  const [relevanceResult, setRelevanceResult] = useState<{ relevant: boolean; reason: string } | null>(null)

  // Stage 1: duplicate detection (inline)
  const [checkingDuplicates, setCheckingDuplicates] = useState(false)
  const [duplicateMatches, setDuplicateMatches] = useState<DuplicateMatch[] | null>(null)

  // Stage 3: specialists
  const [specialistMode, setSpecialistMode] = useState<'auto' | 'manual'>('auto')
  const [specialistData, setSpecialistData] = useState<SpecialistCategories | null>(null)
  const [selectedSpecialists, setSelectedSpecialists] = useState<Set<string>>(new Set())
  const [excludedSpecialists, setExcludedSpecialists] = useState<Set<string>>(new Set())
  const [loadingSpecialists, setLoadingSpecialists] = useState(false)

  // Submission
  const [submitting, setSubmitting] = useState(false)

  // Personal results list
  const [items, setItems] = useState<ResearchItem[]>([])
  const [viewingId, setViewingId] = useState<string | null>(null)
  const [viewingData, setViewingData] = useState<FullResearch | null>(null)
  const [notifGranted, setNotifGranted] = useState(false)
  const [liveOverlayId, setLiveOverlayId] = useState<string | null>(null)
  const [liveOverlayQuestion, setLiveOverlayQuestion] = useState('')
  const [liveOverlayClosed, setLiveOverlayClosed] = useState<Set<string>>(new Set())

  // Public library
  const [publicPapers, setPublicPapers] = useState<PublicPaper[]>([])
  const [publicOffset, setPublicOffset] = useState(0)
  const [publicHasMore, setPublicHasMore] = useState(false)
  const [loadingPublic, setLoadingPublic] = useState(false)
  const [publicReportData, setPublicReportData] = useState<PublicPaperFull | null>(null)
  const [publicTotal, setPublicTotal] = useState(0)

  // Toast notifications
  const [toast, setToast] = useState<{ msg: string; type: 'ok' | 'error' } | null>(null)

  const inputRef = useRef<HTMLTextAreaElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevStatusRef = useRef<Map<string, string>>(new Map())

  // Auto-dismiss toast after 3 seconds
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [toast])

  // Check auth on mount
  useEffect(() => {
    const token = localStorage.getItem('an_auth_token')
    if (!token) {
      setAuthChecked(true)
      return
    }
    fetch(`${config.api.baseUrl}/theo/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => {
        if (r.ok) return r.json()
        return null
      })
      .then((data: AuthUser | null) => {
        if (data) setAuthUser(data)
      })
      .catch(() => { /* no token or invalid */ })
      .finally(() => setAuthChecked(true))
  }, [])

  // Request notification permission
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().then(p => setNotifGranted(p === 'granted'))
    } else if ('Notification' in window) {
      setNotifGranted(Notification.permission === 'granted')
    }
  }, [])

  // Fetch public library
  const fetchPublicPapers = useCallback(async (offset: number, append: boolean) => {
    setLoadingPublic(true)
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/public?offset=${offset}&limit=20`)
      if (resp.ok) {
        const data: { papers: PublicPaper[]; total: number } = await resp.json()
        const papers = data.papers || []
        setPublicPapers(prev => append ? [...prev, ...papers] : papers)
        setPublicHasMore(offset + papers.length < (data.total || 0))
        setPublicOffset(offset + papers.length)
        setPublicTotal(data.total || 0)
      }
    } catch { /* ignore */ }
    setLoadingPublic(false)
  }, [])

  // Load public papers on mount
  useEffect(() => {
    fetchPublicPapers(0, false)
  }, [fetchPublicPapers])

  // Fetch personal research list
  const fetchList = useCallback(async () => {
    if (!authUser) return
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
  }, [notifGranted, authUser])

  // Poll every 10s (only when logged in)
  useEffect(() => {
    if (!authUser) return
    fetchList()
    pollRef.current = setInterval(fetchList, 10000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [fetchList, authUser])

  // Load adapters on first visit to step 2
  const loadAdapters = useCallback(async () => {
    if (adapterData) return
    setLoadingAdapters(true)
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/adapters`)
      if (resp.ok) {
        const data: AdapterData = await resp.json()
        setAdapterData(data)
      }
    } catch { /* ignore */ }
    setLoadingAdapters(false)
  }, [adapterData])

  // Load specialists on first visit to step 3
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

  // --- YouTube URL parser ---
  function parseYouTubeIds(text: string): string[] {
    const patterns: RegExp[] = [
      /(?:youtube\.com\/(?:watch\?(?:[^&]*&)*v=|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/g,
    ]
    const ids: string[] = []
    for (const pattern of patterns) {
      let m: RegExpExecArray | null
      while ((m = pattern.exec(text)) !== null) {
        const id = m[1]
        if (!ids.includes(id)) ids.push(id)
      }
    }
    // Also match bare 11-char IDs not already captured
    const barePattern = /(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])/g
    let bm: RegExpExecArray | null
    while ((bm = barePattern.exec(text)) !== null) {
      const id = bm[1]
      if (!ids.includes(id)) ids.push(id)
    }
    return ids
  }

  // --- Stage 1: Check Relevance + Duplicates in sequence ---
  const handleCheckTopic = useCallback(async () => {
    if (question.trim().length < 10) return
    setCheckingRelevance(true)
    setRelevanceResult(null)
    setDuplicateMatches(null)
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/check-relevance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ question: question.trim() }),
      })
      if (resp.ok) {
        const data: { relevant: boolean; reason: string } = await resp.json()
        setRelevanceResult(data)
        if (data.relevant) {
          // Immediately run duplicate check inline
          setCheckingDuplicates(true)
          try {
            const dupResp = await fetch(`${config.api.baseUrl}/theo/check-duplicates`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
              body: JSON.stringify({ question: question.trim() }),
            })
            if (dupResp.ok) {
              const dupData: { matches: DuplicateMatch[] } = await dupResp.json()
              setDuplicateMatches(dupData.matches || [])
            } else {
              setDuplicateMatches([])
            }
          } catch {
            setDuplicateMatches([])
          }
          setCheckingDuplicates(false)
        }
      } else {
        setRelevanceResult({ relevant: false, reason: 'Failed to check relevance' })
      }
    } catch {
      setRelevanceResult({ relevant: false, reason: 'Network error' })
    }
    setCheckingRelevance(false)
  }, [question])

  // --- Step 2 transition ---
  const goToStep2 = useCallback(() => {
    setWizardStep(2)
    loadAdapters()
  }, [loadAdapters])

  // --- Stage 3 transition ---
  const goToStep3 = useCallback(() => {
    setWizardStep(3)
    loadSpecialists()
  }, [loadSpecialists])

  // --- Stage 4: Submit ---
  const handleSubmit = useCallback(async () => {
    if (question.trim().length < 10 || submitting) return
    setSubmitting(true)
    try {
      const body: Record<string, unknown> = {
        question: question.trim(),
        effort,
        ...(videoIds.length > 0 ? { video_ids: videoIds } : {}),
        ...(disabledAdapters.size > 0 ? { disabled_adapters: Array.from(disabledAdapters) } : {}),
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
        setToast({ msg: err.detail || 'Failed to submit', type: 'error' })
        return
      }
      // Reset wizard
      setQuestion('')
      setWizardStep(1)
      sessionStorage.removeItem('theo_question')
      sessionStorage.removeItem('theo_effort')
      setVideoIds([])
      setVideoInput('')
      sessionStorage.removeItem('theo_video_ids')
      setDisabledAdapters(new Set())
      sessionStorage.removeItem('theo_disabled_adapters')
      setRelevanceResult(null)
      setDuplicateMatches(null)
      setSpecialistMode('auto')
      fetchList()
    } finally {
      setSubmitting(false)
    }
  }, [question, effort, videoIds, disabledAdapters, submitting, specialistMode, selectedSpecialists, excludedSpecialists, specialistData, fetchList])

  // --- Result actions ---
  const handleCancel = useCallback(async (id: string) => {
    try {
      await fetch(`${config.api.baseUrl}/theo/research/${id}`, {
        method: 'DELETE', headers: getAuthHeaders(),
      })
      fetchList()
    } catch { /* ignore */ }
  }, [fetchList])

  const handleDelete = useCallback(async (id: string) => {
    if (!confirm('Delete this research? This cannot be undone.')) return
    try {
      await fetch(`${config.api.baseUrl}/theo/research/${id}`, {
        method: 'DELETE', headers: getAuthHeaders(),
      })
      fetchList()
    } catch { /* ignore */ }
  }, [fetchList])

  const handlePublish = useCallback(async (id: string) => {
    if (!confirm('Publish this research to the public library?\n\nIt will be visible to everyone on the site with your name as author, and used as a citation source in future research.')) return
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/research/${id}/publish`, {
        method: 'POST', headers: getAuthHeaders(),
      })
      if (resp.ok) {
        setToast({ msg: 'Published to the public library', type: 'ok' })
      } else {
        const err = await resp.json().catch(() => ({ detail: 'Failed to publish' }))
        setToast({ msg: err.detail || 'Failed to publish', type: 'error' })
      }
      fetchList()
    } catch { /* ignore */ }
  }, [fetchList])

  const handleUnpublish = useCallback(async (id: string) => {
    if (!confirm('Remove this paper from the public library? It will remain in your private results.')) return
    try {
      await fetch(`${config.api.baseUrl}/theo/research/${id}/unpublish`, {
        method: 'POST', headers: getAuthHeaders(),
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
    setPublicReportData(null)
    document.title = 'Theodore Furcade — Ancient Nerds Research Lab'
  }, [])

  // Duplicate card: read a public match
  const handleReadDuplicateMatch = useCallback(async (slug: string) => {
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/public/${slug}`)
      if (!resp.ok) return
      const data: PublicPaperFull = await resp.json()
      setPublicReportData(data)
    } catch { /* ignore */ }
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

  // Toggle adapter
  const toggleAdapter = useCallback((key: string) => {
    setDisabledAdapters(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      sessionStorage.setItem('theo_disabled_adapters', JSON.stringify(Array.from(next)))
      return next
    })
  }, [])

  const selectedEffort = EFFORTS.find(e => e.key === effort)
  const activeItems = items.filter(i => i.status === 'queued' || i.status === 'running')
  const doneItems = items.filter(i => i.status !== 'queued' && i.status !== 'running')

  // Active running item that is not being watched (for the investigation banner)
  const runningItem = authUser ? items.find(i => i.status === 'running') : null
  const showInvestigatingBanner = !!(runningItem && !liveOverlayId)

  // Adapter group map for Stage 2 render
  const adaptersByGroup: Record<string, Array<[string, AdapterInfo]>> = {}
  if (adapterData) {
    for (const group of ADAPTER_GROUP_ORDER) {
      adaptersByGroup[group] = Object.entries(adapterData).filter(([, info]) => info.group === group)
    }
  }

  // Enabled adapter count for Stage 4 summary
  const totalAdapters = adapterData ? Object.keys(adapterData).length : 0
  const enabledAdapters = totalAdapters - disabledAdapters.size

  if (!authChecked) {
    return (
      <div className="theo-page">
        <PageHeader currentPage="theo">
          <span style={{ fontSize: 12, color: 'var(--theo-amber, #d4912a)', letterSpacing: 1 }}>
            Research Lab
          </span>
        </PageHeader>
        <div className="theo-auth-loading">
          <div className="theo-skeleton-bar" style={{ width: '60%', margin: '0 auto 10px' }} />
          <div className="theo-skeleton-bar" style={{ width: '40%', margin: '0 auto 10px' }} />
          <div className="theo-skeleton-bar" style={{ width: '50%', margin: '0 auto' }} />
        </div>
      </div>
    )
  }

  return (
    <div className="theo-page">
      <PageHeader currentPage="theo">
        <span className="page-header-title">Research Lab</span>
      </PageHeader>
      <AiNoticeBanner message="Research papers and illustrations are AI-generated. Always verify claims with original sources." />

      {/* Investigating banner — shown when research is running and live overlay is closed */}
      {showInvestigatingBanner && (
        <button
          className="theo-investigating-banner"
          onClick={() => handleWatchLive(runningItem!)}
        >
          <span className="theo-live-dot" style={{ display: 'inline-block' }} />
          Theo is investigating... Watch live
        </button>
      )}

      {/* Hero */}
      <div className="theo-hero">
        <div className="theo-avatar-row">
          <img src="/images/theo.png" alt="Theodore Furcade" className="theo-avatar" />
          <div>
            <h1 className="theo-title">Theodore Furcade</h1>
            <div className="theo-subtitle">Archaeological Research Agent</div>
          </div>
        </div>
        <div className="theo-quote">"Give me a question. I'll dig deep."</div>
      </div>

      {/* ═══════ LOGGED OUT VIEW ═══════ */}
      {!authUser && (
        <>
          {/* Login prompt */}
          <div className="theo-login-prompt">
            <div className="theo-login-prompt-title">Start your own research</div>
            <div className="theo-login-prompt-desc">
              Log in with Discord to submit questions to Theo, track your research, and publish findings to the community.
            </div>
            <a className="theo-login-btn" href="/auth/discord">
              Log in with Discord
            </a>
          </div>
        </>
      )}

      {/* ═══════ LOGGED IN VIEW — Wizard ═══════ */}
      {authUser && (
        <>
          {/* Wizard Steps Indicator — 4 steps: Topic, Sources, Specialists, Launch */}
          <div className="theo-wizard-steps">
            <div className={`theo-step-dot ${wizardStep >= 1 ? 'active' : ''} ${wizardStep > 1 ? 'completed' : ''}`}>
              <span className="theo-step-num">
                {wizardStep > 1 ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                ) : '1'}
              </span>
              <span className="theo-step-label">Topic</span>
            </div>
            <div className="theo-step-line" />
            <div className={`theo-step-dot ${wizardStep >= 2 ? 'active' : ''} ${wizardStep > 2 ? 'completed' : ''}`}>
              <span className="theo-step-num">
                {wizardStep > 2 ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                ) : '2'}
              </span>
              <span className="theo-step-label">Sources</span>
            </div>
            <div className="theo-step-line" />
            <div className={`theo-step-dot ${wizardStep >= 3 ? 'active' : ''} ${wizardStep > 3 ? 'completed' : ''}`}>
              <span className="theo-step-num">
                {wizardStep > 3 ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                ) : '3'}
              </span>
              <span className="theo-step-label">Specialists</span>
            </div>
            <div className="theo-step-line" />
            <div className={`theo-step-dot ${wizardStep >= 4 ? 'active' : ''}`}>
              <span className="theo-step-num">4</span>
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
                  onChange={e => {
                    const v = e.target.value
                    setQuestion(v)
                    setRelevanceResult(null)
                    setDuplicateMatches(null)
                    sessionStorage.setItem('theo_question', v)
                  }}
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
                      onClick={() => { setEffort(e.key); sessionStorage.setItem('theo_effort', e.key) }}
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
                  <button
                    className="theo-next-btn"
                    disabled={checkingDuplicates}
                    onClick={goToStep2}
                  >
                    {checkingDuplicates ? 'Checking...' : 'Next'}
                  </button>
                )}
              </div>

              {/* Inline duplicate results */}
              {relevanceResult?.relevant && (
                <>
                  {checkingDuplicates && (
                    <div className="theo-auto-info" style={{ marginTop: 12 }}>
                      Scanning for similar research...
                    </div>
                  )}
                  {!checkingDuplicates && duplicateMatches !== null && duplicateMatches.length > 0 && (
                    <div className="theo-inline-duplicates">
                      <div className="theo-inline-dup-header">
                        Similar research found — review before continuing
                      </div>
                      {duplicateMatches.map(match => (
                        <div key={match.paper_slug} className="theo-inline-dup-card">
                          <span className="theo-inline-dup-title">{match.paper_title}</span>
                          <span className="theo-inline-dup-meta">by {match.author_username}</span>
                          <span className="theo-badge theo-badge-similarity">
                            {Math.round(match.score * 100)}% similar
                          </span>
                          <button
                            className="theo-inline-dup-read"
                            onClick={() => handleReadDuplicateMatch(match.paper_slug)}
                          >
                            Read
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ═══════ STAGE 2: Sources ═══════ */}
          {wizardStep === 2 && (
            <div className="theo-form">
              <div className="theo-stage-header">
                <button className="theo-back-btn" onClick={() => setWizardStep(1)}>Back</button>
                <span className="theo-stage-title">Sources</span>
              </div>

              {/* YouTube Sources */}
              <div className="theo-video-section">
                <div className="theo-video-label">YouTube Sources <span style={{ opacity: 0.5, fontWeight: 400 }}>(optional)</span></div>
                <textarea
                  className="theo-video-input"
                  placeholder="Paste YouTube URLs here (max 5)"
                  value={videoInput}
                  disabled={videoIds.length >= 5}
                  rows={2}
                  onChange={e => {
                    const text = e.target.value
                    setVideoInput(text)
                  }}
                  onPaste={e => {
                    e.preventDefault()
                    const pasted = e.clipboardData.getData('text')
                    const parsed = parseYouTubeIds(pasted)
                    if (parsed.length > 0) {
                      setVideoIds(prev => {
                        const merged = [...prev]
                        for (const id of parsed) {
                          if (!merged.includes(id) && merged.length < 5) merged.push(id)
                        }
                        sessionStorage.setItem('theo_video_ids', JSON.stringify(merged))
                        return merged
                      })
                      setVideoInput('')
                    } else {
                      setVideoInput(pasted)
                    }
                  }}
                  onBlur={e => {
                    const text = e.target.value.trim()
                    if (!text) return
                    const parsed = parseYouTubeIds(text)
                    if (parsed.length > 0) {
                      setVideoIds(prev => {
                        const merged = [...prev]
                        for (const id of parsed) {
                          if (!merged.includes(id) && merged.length < 5) merged.push(id)
                        }
                        sessionStorage.setItem('theo_video_ids', JSON.stringify(merged))
                        return merged
                      })
                      setVideoInput('')
                    }
                  }}
                />
                {videoIds.length > 0 && (
                  <div className="theo-video-chips">
                    {videoIds.map(id => (
                      <span key={id} className="theo-video-chip">
                        {id}
                        <button
                          type="button"
                          className="theo-video-chip-remove"
                          onClick={() => {
                            setVideoIds(prev => {
                              const next = prev.filter(v => v !== id)
                              sessionStorage.setItem('theo_video_ids', JSON.stringify(next))
                              return next
                            })
                          }}
                          aria-label={"Remove video " + id}
                        >&#x2715;</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Source Adapter Toggles */}
              <div className="theo-scope-section">
                <div className="theo-scope-label">Source Adapters</div>
                {loadingAdapters && (
                  <div className="theo-auto-info">Loading adapters...</div>
                )}
                {adapterData && (
                  <div className="theo-adapter-grid">
                    {ADAPTER_GROUP_ORDER.map(group => {
                      const entries = adaptersByGroup[group] || []
                      if (entries.length === 0) return null
                      return (
                        <div key={group} className="theo-adapter-group">
                          <div className="theo-adapter-group-label">{ADAPTER_GROUP_LABELS[group]}</div>
                          <div className="theo-adapter-cards">
                            {entries.map(([key, info]) => {
                              const isEnabled = !disabledAdapters.has(key)
                              return (
                                <div
                                  key={key}
                                  className={`theo-adapter-card ${isEnabled ? 'enabled' : 'disabled'}`}
                                  onClick={() => toggleAdapter(key)}
                                  role="checkbox"
                                  aria-checked={isEnabled}
                                  tabIndex={0}
                                  onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggleAdapter(key) } }}
                                >
                                  {info.favicon ? (
                                    <img src={info.favicon} alt="" className="theo-adapter-favicon" />
                                  ) : key === 'ancientnerds_db' ? (
                                    <svg className="theo-adapter-favicon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
                                  ) : key === 'ancientnerds_research' ? (
                                    <svg className="theo-adapter-favicon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                                  ) : null}
                                  <span className="theo-adapter-label">{info.label}</span>
                                  <label className="theo-adapter-toggle" onClick={e => e.stopPropagation()}>
                                    <input
                                      type="checkbox"
                                      checked={isEnabled}
                                      onChange={() => toggleAdapter(key)}
                                      aria-label={`Toggle ${info.label}`}
                                    />
                                    <span className="theo-adapter-toggle-track" />
                                    <span className="theo-adapter-toggle-thumb" />
                                  </label>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              <div className="theo-submit-row">
                <button className="theo-next-btn" onClick={goToStep3}>
                  Next
                </button>
              </div>
            </div>
          )}

          {/* ═══════ STAGE 3: Specialist Selection ═══════ */}
          {wizardStep === 3 && (
            <div className="theo-form">
              <div className="theo-stage-header">
                <button className="theo-back-btn" onClick={() => setWizardStep(2)}>Back</button>
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
                              data-tooltip={s.perspective}
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
                <button className="theo-next-btn" onClick={() => setWizardStep(4)}>
                  Next
                </button>
              </div>
            </div>
          )}

          {/* ═══════ STAGE 4: Review + Launch ═══════ */}
          {wizardStep === 4 && (
            <div className="theo-form">
              <div className="theo-stage-header">
                <button className="theo-back-btn" onClick={() => setWizardStep(3)}>Back</button>
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
                  <span className="theo-review-label">Sources</span>
                  <span className="theo-review-value">
                    {totalAdapters > 0
                      ? `${enabledAdapters} of ${totalAdapters} adapters enabled`
                      : 'All adapters enabled'}
                    {videoIds.length > 0 && `, ${videoIds.length} YouTube video${videoIds.length > 1 ? 's' : ''}`}
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

              {/* Research prompt preview */}
              <div style={{ marginTop: 16 }}>
                <div className="theo-prompt-preview-label">Research prompt</div>
                <div className="theo-prompt-preview">{question}</div>
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
                    <span className="theo-badge theo-badge-effort">{EFFORT_LABELS[item.effort] || item.effort}</span>
                    <span className={`theo-badge theo-badge-status theo-badge-${item.status}`}>
                      {item.status === 'running' ? <>● Running</> : <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>{`#${activeItems.indexOf(item) + 1} Queued`}</>}
                    </span>
                  </div>
                  {item.status === 'running' && (
                    <div className="theo-card-actions">
                      <button className="theo-btn-view" onClick={() => handleWatchLive(item)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>Live</button>
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
            <div className="theo-list-header" style={{ display: 'flex', alignItems: 'center' }}>
              <span>{doneItems.length > 0 ? `Results (${doneItems.length})` : 'Results'}</span>
              {doneItems.length > 0 && (
                <button
                  className="theo-new-research-btn"
                  onClick={() => {
                    setWizardStep(1)
                    setTimeout(() => inputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50)
                  }}
                >
                  + New
                </button>
              )}
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
                    <span className="theo-badge theo-badge-effort">{EFFORT_LABELS[item.effort] || item.effort}</span>
                    <span className={`theo-badge theo-badge-status theo-badge-${item.status}`}>
                      {item.status === 'completed' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><polyline points="20 6 9 17 4 12"/></svg>Done</> :
                       item.status === 'failed' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>Failed</> :
                       item.status === 'cancelled' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><line x1="5" y1="12" x2="19" y2="12"/></svg>Cancelled</> : item.status}
                    </span>
                    {item.is_public && (
                      <span className="theo-badge theo-badge-published">Published</span>
                    )}
                  </div>
                  <div className="theo-card-meta">
                    {item.duration_ms != null && <span>{formatDurationMs(item.duration_ms)}</span>}
                    <span>{SPECIALIST_COUNTS[item.effort] ?? '?'} specialists</span>
                    {item.created_at && <span>{timeAgo(item.created_at)}</span>}
                  </div>
                  <div className="theo-card-actions">
                    {item.status === 'completed' && (
                      <button className="theo-btn-view" onClick={() => handleView(item.id)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>Report</button>
                    )}
                    {item.status === 'failed' && (
                      <>
                        <button className="theo-btn-retry" onClick={() => handleRetry(item)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>Retry</button>
                        {item.error_message && (
                          <span style={{ fontSize: 10, color: 'var(--status-error-soft)', marginLeft: 4 }}>
                            {item.error_message.substring(0, 80)}
                          </span>
                        )}
                      </>
                    )}
                    {item.status === 'completed' && authUser.has_researcher_role && !item.is_public && (
                      <button className="theo-btn-publish" onClick={() => handlePublish(item.id)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>Publish</button>
                    )}
                    {item.status === 'completed' && item.is_public && (
                      <button className="theo-btn-unpublish" onClick={() => handleUnpublish(item.id)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>Unpublish</button>
                    )}
                    {(item.status === 'completed' || item.status === 'failed' || item.status === 'cancelled') && (
                      <button className="theo-btn-delete" onClick={() => handleDelete(item.id)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>Delete</button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}

      {/* ═══════ Public Research Library ═══════ */}
      <div className="theo-list theo-public-library">
        <div className="theo-list-header">
          {publicTotal > 0 ? `Public Research Library (${publicTotal})` : 'Public Research Library'}
        </div>
        {publicPapers.length === 0 && !loadingPublic ? (
          <div className="theo-empty">No published research yet.</div>
        ) : (
          <>
            <div className="theo-public-grid">
              {publicPapers.map(paper => (
                <div
                  key={paper.slug}
                  className={`theo-public-card${authUser?.username === paper.published_by ? ' theo-public-card--own' : ''}`}
                  onClick={() => { window.location.href = `/research.html?slug=${paper.slug}` }}
                  role="button"
                  tabIndex={0}
                  aria-label={paper.title}
                  onKeyDown={e => { if (e.key === 'Enter') window.location.href = `/research.html?slug=${paper.slug}` }}
                >
                  <div className="theo-public-card-hero">
                    <img src={paper.cover_url} alt="" className="theo-public-card-img" loading="lazy" />
                    <div className="theo-public-card-vignette" />
                    <div className="theo-public-card-title">{paper.title}</div>
                  </div>
                  <div className="theo-public-card-body">
                    {paper.card_description && (
                      <p className="theo-public-card-desc">{paper.card_description}</p>
                    )}
                    <div className="theo-public-card-footer">
                      <span className="theo-public-card-author">
                        {paper.author_avatar && (
                          <img src={paper.author_avatar} alt="" className="theo-author-avatar" />
                        )}
                        {paper.published_by}
                      </span>
                      <span className="theo-badge theo-badge-effort">{EFFORT_LABELS[paper.effort] || paper.effort}</span>
                      <span className="theo-public-card-date">{timeAgo(paper.published_at)}</span>
                      <button
                        className="theo-public-card-share"
                        aria-label="Copy link"
                        onClick={(e) => {
                          e.stopPropagation()
                          navigator.clipboard.writeText(window.location.origin + '/theo.html#' + paper.slug)
                          setToast({ msg: 'Link copied!', type: 'ok' })
                        }}
                        title="Copy link"
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {publicHasMore && (
              <div className="theo-load-more-row">
                <button
                  className="theo-load-more-btn"
                  disabled={loadingPublic}
                  onClick={() => fetchPublicPapers(publicOffset, true)}
                >
                  {loadingPublic ? 'Loading...' : 'Load more'}
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Report Overlay — personal research */}
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

      {/* Report Overlay — public paper */}
      {publicReportData && (
        <Suspense fallback={null}>
          <TheoReportOverlay
            question={publicReportData.question}
            result={publicReportData.result}
            pipelineTrace={null}
            effort={publicReportData.effort}
            durationMs={publicReportData.duration_ms}
            sitesFound={publicReportData.sites_found}
            toolsUsed={publicReportData.tools_used}
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

      {/* Toast notifications */}
      {toast && (
        <div className={`theo-toast theo-toast-${toast.type}`}>
          {toast.msg}
        </div>
      )}
    </div>
  )
}
