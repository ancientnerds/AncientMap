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
import QualityBadge, { type QualityScore } from '../components/theo/QualityBadge'
import { NervLoadingBar } from '../components/NervLoadingBar'

const TheoReportOverlay = lazy(() => import('../components/theo/TheoReportOverlay'))
const TheoResearchLive = lazy(() => import('../components/theo/TheoResearchLive'))

// ---------------------------------------------------------------------------
// Tutorial hints — shown until the user publishes their first paper
// ---------------------------------------------------------------------------

function TutorialHint({ children, step }: { children: React.ReactNode; step?: string }) {
  const show = localStorage.getItem('theo_has_published') !== 'true'
  const [dismissed, setDismissed] = useState(false)
  if (!show || dismissed) return null
  return (
    <div className="theo-tutorial-hint">
      {step && <span className="theo-tutorial-step">{step}</span>}
      <div className="theo-tutorial-body">{children}</div>
      <button className="theo-tutorial-dismiss" onClick={() => setDismissed(true)} aria-label="Dismiss hint">✕</button>
    </div>
  )
}

function TruncatedQuestion({ text, max = 200 }: { text: string; max?: number }) {
  const truncated = text.length > max ? text.slice(0, max) + '...' : text
  return (
    <span className="theo-card-question">
      {truncated}
      <button
        className="theo-copy-question"
        onClick={e => { e.stopPropagation(); navigator.clipboard.writeText(text) }}
        title="Copy full prompt"
        aria-label="Copy full prompt"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
    </span>
  )
}

const SPECIALIST_PFPS: Record<string, string> = {
  field_archaeologist: 'artemis-greenleaf.webp',
  ceramic_analyst: 'carina-firetail.webp',
  lithics_specialist: 'nova-stonepaw.webp',
  bioarchaeologist: 'arcturus-frostbite.webp',
  geoarchaeologist: 'gaia-earthsong.webp',
  dating_specialist: 'chronos-timewalker.webp',
  epigrapher: 'astra-quilldancer.webp',
  ancient_historian: 'aeon-timegazer.webp',
  anthropologist: 'libra-balancerider.webp',
  underwater_archaeologist: 'thalassa-seaglider.webp',
  remote_sensing_expert: 'hyperion-techspine.webp',
  conservation_specialist: 'elara-lightweaver.webp',
  archaeobotanist: 'mira-petalweaver.webp',
  numismatist: 'mercury-silversurge.webp',
  archaeoastronomer: 'pleiades-starchaser.webp',
  zooarchaeologist: 'leo-blazeclaw.webp',
  classical_archaeologist: 'helios-lightbringer.webp',
  prehistorian: 'eos-dawnseeker.webp',
  geologist: 'titan-stoneshard.webp',
  paleoclimatologist: 'rhea-stormweaver.webp',
  ancient_dna_specialist: 'spectra-prismshifter.webp',
  archaeometallurgist: 'talos-ironsight.webp',
  volcanologist: 'solara-emberwave.webp',
  alternative_history_researcher: 'nox-shadowmender.webp',
  comparative_mythologist: 'spica-dreamweaver.webp',
  esoteric_traditions_scholar: 'vesper-twilightbound.webp',
  anomalous_phenomena_analyst: 'nix-voidseeker.webp',
  physicist: 'pulsar-quickscale.webp',
  archaeochemist: 'pandora-luminescent.webp',
  paleoanthropologist: 'osiris-spiritbound.webp',
  structural_engineer: 'aegis-steelmane.webp',
  historical_linguist: 'lyre-moonstrider.webp',
  architect: 'seraphina-skygazer.webp',
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
  status: string
  sites_found: number
  tools_used: number
  duration_ms: number | null
  error_message: string | null
  created_at: string | null
  completed_at: string | null
  is_public: boolean
  approved_by: string | null
  quality_score?: QualityScore | null
}

interface FullResearch extends ResearchItem {
  result: { report: string; sites_found: number; tools_used: number; total_tokens: number; duration_ms: number; quality_score?: QualityScore | null } | null
  pipeline_trace: Array<{ stage?: string; status?: string; duration_ms?: number }> | null
  total_tokens: number
}

interface DuplicateMatch {
  paper_title: string
  paper_slug: string
  author_username: string
  score: number
  best_section_title: string
}

interface PublicPaper {
  id: string
  slug: string
  title: string
  question: string
  published_by: string
  author_avatar: string | null
  published_at: string
  sites_found: number
  duration_ms: number | null
  card_description: string
  cover_url: string
  quality_score?: QualityScore | null
}

interface PublicPaperFull {
  slug: string
  question: string
  published_by: string
  published_at: string
  result: { report: string; title?: string; sites_found: number; tools_used: number; total_tokens: number; duration_ms: number; quality_score?: QualityScore | null }
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

  // Stage 2: YouTube video IDs
  const [videoIds, setVideoIds] = useState<string[]>(() => {
    try { return JSON.parse(sessionStorage.getItem('theo_video_ids') || '[]') } catch { return [] }
  })
  const [videoInput, setVideoInput] = useState('')

  // Web URLs
  const [webUrls, setWebUrls] = useState<string[]>(() => {
    try { return JSON.parse(sessionStorage.getItem('theo_web_urls') || '[]') } catch { return [] }
  })
  const [webUrlInput, setWebUrlInput] = useState('')

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
  // specialistMode removed — all specialists shown, user deselects to exclude
  const [specialistData, setSpecialistData] = useState<SpecialistCategories | null>(null)
  const [excludedSpecialists, setExcludedSpecialists] = useState<Set<string>>(new Set())
  const [loadingSpecialists, setLoadingSpecialists] = useState(false)

  // Submission
  const [submitting, setSubmitting] = useState(false)
  const [showTips, setShowTips] = useState(false)

  // Personal results list
  const [items, setItems] = useState<ResearchItem[]>([])
  const [viewingId, setViewingId] = useState<string | null>(null)
  const [viewingData, setViewingData] = useState<FullResearch | null>(null)
  const [viewingStartEditing, setViewingStartEditing] = useState(false)
  const [notifGranted, setNotifGranted] = useState(false)
  const [liveOverlayId, setLiveOverlayId] = useState<string | null>(null)
  const [liveOverlayQuestion, setLiveOverlayQuestion] = useState('')
  const [liveOverlayStartedAt, setLiveOverlayStartedAt] = useState('')
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

  function parseWebUrls(text: string): string[] {
    const urlPattern = /https?:\/\/[^\s<>"{}|\\^`[\]]+/gi
    const urls: string[] = []
    let m: RegExpExecArray | null
    while ((m = urlPattern.exec(text)) !== null) {
      const url = m[0].replace(/[.,;:!?)]+$/, '') // trim trailing punctuation
      // Skip YouTube URLs (handled separately)
      if (/youtube\.com|youtu\.be/i.test(url)) continue
      if (!urls.includes(url)) urls.push(url)
    }
    return urls
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
      const finalPrompt = question.trim()
      const body: Record<string, unknown> = {
        question: finalPrompt,
        ...(videoIds.length > 0 ? { video_ids: videoIds } : {}),
        ...(webUrls.length > 0 ? { web_urls: webUrls } : {}),
        ...(disabledAdapters.size > 0 ? { disabled_adapters: Array.from(disabledAdapters) } : {}),
      }
      // Send excluded specialists if any were deselected
      if (excludedSpecialists.size > 0) {
        body.force_exclude = Array.from(excludedSpecialists)
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
      const result = await resp.json().catch(() => null)

      // Immediately open the live overlay so user sees progress instantly
      if (result?.id) {
        setLiveOverlayId(result.id)
        setLiveOverlayQuestion(question.trim())
        setLiveOverlayStartedAt(new Date().toISOString())
      }

      // Reset wizard
      setQuestion('')
      setWizardStep(1)
      sessionStorage.removeItem('theo_question')
      setVideoIds([])
      setVideoInput('')
      sessionStorage.removeItem('theo_video_ids')
      setWebUrls([])
      setWebUrlInput('')
      sessionStorage.removeItem('theo_web_urls')
      setDisabledAdapters(new Set())
      sessionStorage.removeItem('theo_disabled_adapters')
      setRelevanceResult(null)
      setDuplicateMatches(null)
      setExcludedSpecialists(new Set())
      fetchList()
    } finally {
      setSubmitting(false)
    }
  }, [question, videoIds, disabledAdapters, submitting, excludedSpecialists, fetchList])

  // --- Result actions ---
  const handleCancel = useCallback(async (id: string) => {
    if (!window.confirm('Cancel this research? This cannot be undone.')) return
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
        localStorage.setItem('theo_has_published', 'true')
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
        body: JSON.stringify({ question: item.question }),
      })
      fetchList()
    } catch { /* ignore */ }
  }, [fetchList])

  const handleView = useCallback(async (id: string, startEditing = false) => {
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/research/${id}`, {
        headers: getAuthHeaders(),
      })
      if (!resp.ok) return
      const data: FullResearch = await resp.json()
      setViewingData(data)
      setViewingId(id)
      setViewingStartEditing(startEditing)
    } catch { /* ignore */ }
  }, [])

  const handleCloseReport = useCallback(() => {
    setViewingId(null)
    setViewingData(null)
    setViewingStartEditing(false)
    setPublicReportData(null)
    document.title = 'Theodore Furcade — Ancient Nerds Research Lab'
  }, [])

  const handleSaveEdit = useCallback(async (markdown: string) => {
    if (!viewingId) return
    try {
      const resp = await fetch(`${config.api.baseUrl}/theo/research/${viewingId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ report: markdown }),
      })
      if (resp.ok) {
        // Update local state with new report text
        setViewingData(prev => {
          if (!prev || !prev.result) return prev
          return { ...prev, result: { ...prev.result, report: markdown } }
        })
        // Refresh the list to pick up any changes
        fetchList()
        setToast({ msg: 'Paper saved', type: 'ok' })
      } else {
        const err = await resp.json().catch(() => ({ detail: 'Failed to save' }))
        setToast({ msg: err.detail || 'Failed to save', type: 'error' })
      }
    } catch {
      setToast({ msg: 'Network error saving paper', type: 'error' })
    }
  }, [viewingId, fetchList])

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
      setLiveOverlayStartedAt(running.created_at || '')
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
    setLiveOverlayStartedAt(item.created_at || '')
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
          <span className="theo-heartbeat-leds">
            {[0, 1, 2].map(i => (
              <span key={i} className="theo-hb-led theo-hb-led--alive" style={{ animationDelay: `${i * 0.3}s` }} />
            ))}
          </span>
          <span style={{ fontFamily: 'var(--font-stamp)', letterSpacing: '1.5px', textTransform: 'uppercase' as const }}>INVESTIGATING</span>
          — Watch live
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
            <a className="account-discord-btn" href={`${config.api.baseUrl}/auth/discord?return_to=${encodeURIComponent('/theo.html')}`} style={{ textDecoration: 'none' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.36-.698.772-1.362 1.225-1.993a.076.076 0 0 0-.041-.107 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.12-.094.246-.194.373-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
              </svg>
              Continue with Discord
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
              {activeItems.length > 0 && (
                <div className="theo-auto-info" style={{ marginBottom: 12 }}>
                  Theo is currently working on a research task. Wait for it to finish before submitting a new one.
                </div>
              )}
              <TutorialHint step="1/5">
                Theo is an AI research agent. Write a focused question about archaeology, ancient history,
                or the ancient world. The more specific your question, the better the research — name sites,
                time periods, and what you want investigated.
              </TutorialHint>
              <div className="theo-input-wrap">
                <textarea
                  ref={inputRef}
                  className="theo-input"
                  placeholder="What should Theo investigate? Be specific — name sites, periods, cultures, and what you want to know. (min 200 characters)"
                  value={question}
                  onChange={e => {
                    const v = e.target.value
                    setQuestion(v)
                    setRelevanceResult(null)
                    setDuplicateMatches(null)
                    sessionStorage.setItem('theo_question', v)
                  }}
                  rows={3}
                  disabled={activeItems.length > 0}
                  style={activeItems.length > 0 ? { opacity: 0.5 } : undefined}
                />
                <span className={`theo-input-counter${question.length >= 200 ? ' met' : ''}`}>
                  {question.length}/200
                </span>
              </div>

              <button className="theo-tips-toggle" onClick={() => setShowTips(!showTips)}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                {showTips ? 'Hide tips' : 'Tips for better results'}
              </button>
              {showTips && (
                <div className="theo-tips-inline">
                  <ul className="theo-tips-list">
                    <li>Name specific sites, periods, and civilizations</li>
                    <li>Include the hypothesis you want investigated</li>
                    <li>Mention specific texts or sources if relevant</li>
                    <li>Ask about competing theories to get debate</li>
                  </ul>
                </div>
              )}

              {/* Relevance check */}
              <div className="theo-relevance-row">
                <button
                  className="theo-check-btn"
                  disabled={question.trim().length < 200 || checkingRelevance || activeItems.length > 0}
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

              <TutorialHint step="2/5">
                Theo searches academic databases, web sources, and Wikipedia automatically. You can
                optionally add YouTube videos or web articles as additional sources. The source adapters
                below control which databases are searched — the defaults work well for most topics.
              </TutorialHint>
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

              {/* Web Article Sources */}
              <div className="theo-video-section">
                <div className="theo-video-label">Web Sources <span style={{ opacity: 0.5, fontWeight: 400 }}>(optional, max 10)</span></div>
                <textarea
                  className="theo-video-input"
                  placeholder="Paste article URLs here (research papers, blog posts, news articles)"
                  value={webUrlInput}
                  disabled={webUrls.length >= 10}
                  rows={2}
                  onChange={e => setWebUrlInput(e.target.value)}
                  onPaste={e => {
                    e.preventDefault()
                    const pasted = e.clipboardData.getData('text')
                    const parsed = parseWebUrls(pasted)
                    if (parsed.length > 0) {
                      setWebUrls(prev => {
                        const merged = [...prev]
                        for (const url of parsed) {
                          if (!merged.includes(url) && merged.length < 10) merged.push(url)
                        }
                        sessionStorage.setItem('theo_web_urls', JSON.stringify(merged))
                        return merged
                      })
                      setWebUrlInput('')
                    } else {
                      setWebUrlInput(pasted)
                    }
                  }}
                  onBlur={() => {
                    const text = webUrlInput.trim()
                    if (!text) return
                    const parsed = parseWebUrls(text)
                    if (parsed.length > 0) {
                      setWebUrls(prev => {
                        const merged = [...prev]
                        for (const url of parsed) {
                          if (!merged.includes(url) && merged.length < 10) merged.push(url)
                        }
                        sessionStorage.setItem('theo_web_urls', JSON.stringify(merged))
                        return merged
                      })
                      setWebUrlInput('')
                    }
                  }}
                />
                {webUrls.length > 0 && (
                  <div className="theo-video-chips">
                    {webUrls.map(url => {
                      // Show just the domain + path tail for readability
                      let label = url
                      try { label = new URL(url).hostname + new URL(url).pathname.slice(0, 30) } catch { /* keep full */ }
                      return (
                        <span key={url} className="theo-video-chip" title={url}>
                          {label.length > 40 ? label.slice(0, 37) + '...' : label}
                          <button
                            type="button"
                            className="theo-video-chip-remove"
                            onClick={() => {
                              setWebUrls(prev => {
                                const next = prev.filter(u => u !== url)
                                sessionStorage.setItem('theo_web_urls', JSON.stringify(next))
                                return next
                              })
                            }}
                            aria-label="Remove URL"
                          >&#x2715;</button>
                        </span>
                      )
                    })}
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
                <span className="theo-stage-title">AI Specialist Panel</span>
              </div>

              <TutorialHint step="3/5">
                Each specialist is an AI persona with a unique analytical lens — they look at your
                question from different angles (field methods, dating, geology, etc.). Theo auto-selects
                the most relevant ones, but you can exclude any that don't fit your topic.
                Their analyses are debated and synthesized before the paper is written.
              </TutorialHint>
              <div className="theo-spec-notice">
                Theo auto-selects the specialists most relevant to your question.
                Deselect any you want to exclude.
              </div>

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
                            {SPECIALIST_PFPS[s.id] ? (
                              <img src={`/data/specialists/${SPECIALIST_PFPS[s.id]}`} alt="" className="theo-spec-pfp" />
                            ) : (
                              <div className="theo-spec-pfp theo-spec-pfp-fallback">?</div>
                            )}
                            <span className="theo-spec-name">{s.name}</span>
                            <span className="theo-spec-title">{s.title}</span>
                          </button>
                          )
                        })}
                      </div>
                    </div>
                  ))}
              </div>

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

              <TutorialHint step="4/5">
                Review your research prompt below — you can still edit it. Once you launch, Theo will
                decompose your question into research angles, search sources, run specialist analyses,
                debate findings, and assemble a narrative paper. You'll see live progress while it runs.
              </TutorialHint>
              {/* Editable enriched research prompt */}
              <div className="theo-launch-section">
                <div className="theo-launch-label">
                  Research Prompt
                </div>
                <textarea
                  className="theo-input"
                  value={question}
                  onChange={e => { setQuestion(e.target.value); sessionStorage.setItem('theo_question', e.target.value) }}
                  rows={10}
                  disabled={activeItems.length > 0}
                  style={activeItems.length > 0 ? { opacity: 0.5 } : undefined}
                />
              </div>

              {/* Settings summary — each clickable to jump back */}
              <div className="theo-launch-settings">
                <div className="theo-launch-setting" onClick={() => setWizardStep(2)} role="button" tabIndex={0}>
                  <span className="theo-launch-setting-label">Sources</span>
                  <span className="theo-launch-setting-value">
                    {totalAdapters > 0 ? `${enabledAdapters}/${totalAdapters} adapters` : 'All'}
                    {videoIds.length > 0 && ` + ${videoIds.length} video${videoIds.length > 1 ? 's' : ''}`}
                  </span>
                  <span className="theo-launch-setting-edit">change</span>
                </div>
                <div className="theo-launch-setting" onClick={() => setWizardStep(3)} role="button" tabIndex={0}>
                  <span className="theo-launch-setting-label">Specialists</span>
                  <span className="theo-launch-setting-value">
                    {excludedSpecialists.size === 0
                      ? 'Auto (6+ will be selected based on topic)'
                      : `${excludedSpecialists.size} excluded`}
                  </span>
                  <span className="theo-launch-setting-edit">change</span>
                </div>
              </div>

              <div className="theo-submit-row">
                <button
                  className="theo-submit-btn"
                  disabled={submitting || activeItems.length > 0}
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
                <div
                  key={item.id}
                  className={`theo-card${item.status === 'running' ? ' theo-card--running' : ''}`}
                  onClick={item.status === 'running' ? () => handleWatchLive(item) : undefined}
                >
                  <div className="theo-card-top">
                    <TruncatedQuestion text={item.question} max={80} />
                    <div className="theo-card-badges">
                      {item.status === 'queued' && (
                        <span className="theo-badge theo-badge-status theo-badge-queued theo-badge-stacked">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                          {`#${activeItems.indexOf(item) + 1} Queued`}
                        </span>
                      )}
                      <button className="theo-btn-cancel theo-badge-stacked" onClick={(e) => { e.stopPropagation(); handleCancel(item.id) }}>Cancel</button>
                    </div>
                  </div>
                  {item.status === 'running' && (
                    <div className="theo-card-progress">
                      <NervLoadingBar compact sublabel="INVESTIGATING" />
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
            {doneItems.length > 0 && doneItems.some(i => i.status === 'completed') && (
              <TutorialHint step="5/5">
                Your research is complete. Open a paper to read it, then scroll to the bottom and approve it.
                Approval is required before publishing — your name is attached as the reviewer, creating
                accountability for the research. After your first published paper, these tutorial hints
                will disappear.
              </TutorialHint>
            )}
            {doneItems.length === 0 ? (
              <div className="theo-empty">
                No research results yet. Submit a question above and Theo will investigate.
              </div>
            ) : (
              doneItems.map(item => (
                <div key={item.id} className="theo-card">
                  <div className="theo-card-top">
                    <TruncatedQuestion text={item.question} />
                    <span className={`theo-badge theo-badge-status theo-badge-${item.status}`}>
                      {item.status === 'completed' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><polyline points="20 6 9 17 4 12"/></svg>Done</> :
                       item.status === 'failed' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>Failed</> :
                       item.status === 'cancelled' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><line x1="5" y1="12" x2="19" y2="12"/></svg>Cancelled</> : item.status}
                    </span>
                    {item.is_public && (
                      <span className="theo-badge theo-badge-published">Published</span>
                    )}
                    <QualityBadge qualityScore={item.quality_score} />
                  </div>
                  <div className="theo-card-meta">
                    {item.duration_ms != null && <span>{formatDurationMs(item.duration_ms)}</span>}
                    {item.created_at && <span>{timeAgo(item.created_at)}</span>}
                  </div>
                  <div className="theo-card-actions">
                    {item.status === 'completed' && !item.approved_by && (
                      <button className="theo-btn-view theo-btn-review" onClick={() => handleView(item.id, true)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>Review</button>
                    )}
                    {item.status === 'completed' && item.approved_by && (
                      <button className="theo-btn-view" onClick={() => handleView(item.id)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>Read</button>
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
                      <QualityBadge qualityScore={paper.quality_score} />
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
            durationMs={viewingData.duration_ms}
            sitesFound={viewingData.sites_found}
            toolsUsed={viewingData.tools_used}
            onClose={handleCloseReport}
            isOwner={true}
            isPublic={viewingData.is_public}
            requestId={viewingId}
            initialEditing={viewingStartEditing}
            onSaveEdit={handleSaveEdit}
            onApprove={(approvedBy, approvedAt) => {
              setViewingData(prev => {
                if (!prev?.result) return prev
                return { ...prev, result: { ...prev.result, approved_by: approvedBy, approved_at: approvedAt } }
              })
              fetchList()
              setToast({ msg: 'Paper approved for publishing', type: 'ok' })
            }}
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
            durationMs={publicReportData.duration_ms}
            sitesFound={publicReportData.sites_found}
            toolsUsed={publicReportData.tools_used}
            onClose={handleCloseReport}
            isOwner={false}
          />
        </Suspense>
      )}

      {/* Live Research Overlay */}
      {liveOverlayId && (
        <Suspense fallback={null}>
          <TheoResearchLive
            requestId={liveOverlayId}
            question={liveOverlayQuestion}
            startedAt={liveOverlayStartedAt}
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
