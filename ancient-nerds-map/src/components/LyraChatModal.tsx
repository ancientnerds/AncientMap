/**
 * LyraChatModal — Chat with Lyra Whiskerbyte.
 *
 * Features:
 * - Admin auth gate (Bearer key + Turnstile)
 * - Text input with streaming responses
 * - SSE streaming with token-by-token display
 * - Conversation history (client-side)
 * - Context-aware: receives contextType, contextId, contextYear props
 * - Site highlighting on globe from tool results
 * - Markdown rendering for assistant messages
 * - Sites sidebar with search
 * - Token usage display
 */

import { useState, useEffect, useRef, useCallback, useMemo, lazy, Suspense } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { config } from '../config'
import type { LyraContextType, LyraMessage, SiteHighlight, NewsHighlight, ConversationSummary } from '../types/ai'
import { getCategoryColor, getPeriodColor } from '../constants/colors'
import { enrichLyraContent } from '../utils/lyraContentEnricher'
import { formatRelativeDate } from '../utils/formatters'
import PageHeader from './layout/PageHeader'
import SiteResultItem from './SiteResultItem'
import { SitePopupOverlay } from './SitePopupOverlay'
import { apiDetailToSiteData } from '../utils/siteApi'
import { resolvePeriod } from '../data/sites'
import type { SiteData } from '../data/sites'
import { useFocusTrap } from '../hooks/useFocusTrap'
import SiteChip from './lyra/SiteChip'
import LyraWelcome from './lyra/LyraWelcome'
import PipelinePanel from './lyra/PipelinePanel'
import { applyPipelineEvent } from '../types/pipeline'
import type { PipelineEvent } from '../types/pipeline'
import { navigateGlobeToCoords } from '../utils/globeNavigation'
import { addDiscoveries, getDiscoveryCount } from '../utils/lyraDiscoveries'
import { notifyAchievements } from './AchievementToast'
import NewsCard, { newsHighlightToCardProps } from './news/NewsCard'

const LyraProfileModal = lazy(() => import('./LyraProfileModal'))

interface Props {
  isOpen: boolean
  onClose: () => void
  contextType?: LyraContextType
  contextId?: string
  contextYear?: number
  onHighlightSites?: (siteIds: string[]) => void
  onFlyToSite?: (coords: [number, number]) => void
  onOpenSitePopup?: (site: SiteData) => void
  onOpenEmpirePopup?: (empireId: string) => void
  mode?: 'modal' | 'page'
}


/* ---- Tool status icons ---- */
function getToolIcon(s: string): string {
  if (s.includes('site')) return '\uD83D\uDD0D '
  if (s.includes('news') || s.includes('radar')) return '\uD83D\uDCE1 '
  if (s.includes('transcript')) return '\uD83D\uDCDC '
  if (s.includes('empire')) return '\uD83D\uDC51 '
  if (s.includes('image') || s.includes('photo')) return '\uD83D\uDCF7 '
  return '\u2699\uFE0F '
}

/* ---- Conversation persistence ---- */
const STORAGE_KEY = 'lyra_conversations'

interface StoredConversation {
  id: string
  title: string
  updatedAt: number
  messages: (Omit<LyraMessage, 'timestamp'> & { timestamp: string })[]
}

function saveConversation(id: string, title: string, messages: LyraMessage[]) {
  const all = loadAllStored()
  const serialized: StoredConversation = {
    id,
    title,
    updatedAt: Date.now(),
    messages: messages.map(m => ({
      ...m,
      timestamp: m.timestamp.toISOString(),
      isStreaming: undefined,
      pipelineTrace: m.pipelineTrace
        ? {
            isLive: false,
            nodes: m.pipelineTrace.nodes.map(n => ({ ...n, startedAt: null })),
          }
        : undefined,
    })),
  }
  const idx = all.findIndex(c => c.id === id)
  if (idx >= 0) all[idx] = serialized
  else all.unshift(serialized)
  // Keep max 50 conversations
  if (all.length > 50) all.length = 50
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    // Quota exceeded — drop oldest conversations and retry
    all.length = Math.min(all.length, 25)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(all)) } catch { /* give up */ }
  }
}

function loadConversation(id: string): LyraMessage[] {
  const all = loadAllStored()
  const conv = all.find(c => c.id === id)
  if (!conv) return []
  return conv.messages.map(m => ({ ...m, timestamp: new Date(m.timestamp) }))
}

function listConversations(): ConversationSummary[] {
  return loadAllStored()
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .map(c => ({ id: c.id, title: c.title, updatedAt: c.updatedAt }))
}

function deleteConversation(id: string) {
  const all = loadAllStored().filter(c => c.id !== id)
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(all)) } catch { /* quota */ }
}

function loadAllStored(): StoredConversation[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

/* ---- Custom URL sanitizer — allow Lyra's custom protocols ---- */
const ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'lyra-video', 'lyra-site', 'lyra-coord', 'site', 'flag', 'empire']
function lyraUrlTransform(url: string): string {
  const colonIndex = url.indexOf(':')
  if (colonIndex === -1) return url
  const protocol = url.trim().slice(0, colonIndex)
  if (ALLOWED_PROTOCOLS.includes(protocol.toLowerCase())) return url
  return ''
}

/* ---- Inline YouTube video embed (thumbnail → iframe) ---- */

function LyraInlineVideo({ news, children }: { news: NewsHighlight; children?: React.ReactNode }) {
  const [expanded, setExpanded] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const videoId = news.video_id
  const ts = news.timestamp_seconds
  const ytUrl = ts != null
    ? `https://www.youtube.com/watch?v=${videoId}&t=${ts}`
    : `https://www.youtube.com/watch?v=${videoId}`
  const embedUrl = ts != null
    ? `https://www.youtube.com/embed/${videoId}?start=${ts}&autoplay=1`
    : `https://www.youtube.com/embed/${videoId}?autoplay=1`
  // Use maxresdefault (1280x720, true 16:9) with fallback to mqdefault (320x180, true 16:9)
  // Never use hqdefault — it's 480x360 (4:3) with black letterbox bars
  const [thumbFailed, setThumbFailed] = useState(false)
  const thumbUrl = thumbFailed
    ? `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`
    : `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`

  const formatTs = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${String(sec).padStart(2, '0')}`
  }

  const handleMouseEnter = () => {
    if (leaveTimer.current) { clearTimeout(leaveTimer.current); leaveTimer.current = null }
    if (!expanded) {
      hoverTimer.current = setTimeout(() => setShowPreview(true), 300)
    }
  }
  const handleMouseLeave = () => {
    if (hoverTimer.current) { clearTimeout(hoverTimer.current); hoverTimer.current = null }
    leaveTimer.current = setTimeout(() => setShowPreview(false), 200)
  }
  const handlePreviewEnter = () => {
    if (leaveTimer.current) { clearTimeout(leaveTimer.current); leaveTimer.current = null }
  }
  const handlePreviewLeave = () => {
    leaveTimer.current = setTimeout(() => setShowPreview(false), 200)
  }

  // When collapsed: inline span with button. When expanded: div with full embed.
  if (!expanded) {
    return (
      <span className="lyra-inline-video-wrap">
        <button
          className="lyra-inline-video"
          onClick={() => { setExpanded(true); setShowPreview(false) }}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          title={news.headline || `Watch on YouTube`}
        >
          {children}
        </button>
        {showPreview && news.headline && (
          <div
            className="lyra-video-preview"
            onMouseEnter={handlePreviewEnter}
            onMouseLeave={handlePreviewLeave}
          >
            <NewsCard {...newsHighlightToCardProps(news)} size="sm" />
          </div>
        )}
      </span>
    )
  }

  return (
    <div className="lyra-inline-video-wrap lyra-inline-video-wrap--expanded">
      <button
        className="lyra-inline-video"
        onClick={() => setExpanded(false)}
        title="Collapse video"
      >
        {children}
      </button>
      <div className="lyra-inline-video-embed">
        {!playing ? (
          <div
            className="lyra-inline-video-thumb"
            onClick={() => setPlaying(true)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter') setPlaying(true) }}
          >
            <img src={thumbUrl} alt={news.headline || 'Video thumbnail'} onError={() => { if (!thumbFailed) setThumbFailed(true) }} />
            <div className="lyra-inline-video-play-overlay">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="white">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
            {ts != null && (
              <span className="lyra-inline-video-ts">{formatTs(ts)}</span>
            )}
          </div>
        ) : (
          <div className="lyra-inline-video-iframe-wrap">
            <iframe
              src={embedUrl}
              title={news.headline || 'YouTube video'}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        )}
        <a
          className="lyra-inline-video-external"
          href={ytUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          Watch on YouTube {ts != null && `at ${formatTs(ts)}`} ↗
        </a>
      </div>
    </div>
  )
}

export default function LyraChatModal({
  isOpen,
  onClose,
  contextType = 'global',
  contextId,
  contextYear,
  onHighlightSites,
  onFlyToSite,
  onOpenSitePopup,
  onOpenEmpirePopup,
  mode = 'modal',
}: Props) {
  const [messages, setMessages] = useState<LyraMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<React.ReactNode | null>(null)
  const [sidebarNews, setSidebarNews] = useState<NewsHighlight[]>([])
  const [selectedSite, setSelectedSite] = useState<SiteData | null>(null)
  const [showDossier, setShowDossier] = useState(false)
  const [conversationId, setConversationId] = useState<string>(() => crypto.randomUUID())
  const [conversations, setConversations] = useState<ConversationSummary[]>(() => listConversations())
  const [showHistory, setShowHistory] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SiteData[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [pipelineOpen, setPipelineOpen] = useState(() => localStorage.getItem('lyra_pipeline_open') !== 'false')
  const [viewingPipelineFor, setViewingPipelineFor] = useState<string | null>(null)

  // Auth state — Discord OAuth token from localStorage
  const [authToken, setAuthToken] = useState<string | null>(() =>
    localStorage.getItem('an_auth_token')
  )
  const [userCredits, setUserCredits] = useState<number | null>(null)
  const [isUnlimited, setIsUnlimited] = useState(false)
  const [totalDiscoveries, setTotalDiscoveries] = useState(() => getDiscoveryCount())
  const [chatStreak, setChatStreak] = useState<number>(0)
  const [webSearchEnabled, setWebSearchEnabled] = useState(false)
  const isAuthenticated = !!authToken

  const focusTrapRef = useFocusTrap(isOpen && mode === 'modal')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const searchAbortRef = useRef<AbortController | null>(null)
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const lastUserMsgRef = useRef<string>('')
  // U1: Batch thinking token updates — accumulate in ref, flush every 100ms
  // (prevents 50-100 re-renders/sec during Ollama streaming)
  const thinkingBufferRef = useRef<{ content: string; timer: ReturnType<typeof setTimeout> | null; assistantId: string }>({ content: '', timer: null, assistantId: '' })
  const [showScrollFab, setShowScrollFab] = useState(false)
  const [lyraStatus, setLyraStatus] = useState<string | null>(null)
  const userScrolledUpRef = useRef(false)
  const messagesContainerRef = useRef<HTMLDivElement>(null)

  // Abort in-flight SSE stream + search on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      searchAbortRef.current?.abort()
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)
      if (thinkingBufferRef.current.timer) clearTimeout(thinkingBufferRef.current.timer)
    }
  }, [])

  // Q3: Use ref for sidebarNews so mdComponents doesn't recreate on every SSE news event
  const sidebarNewsRef = useRef(sidebarNews)
  sidebarNewsRef.current = sidebarNews

  // Custom react-markdown components for interactive content
  const mdComponents = useMemo(() => ({
    a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) => {
      // Country flag link: flag:code (from enricher)
      if (href?.startsWith('flag:')) {
        const code = href.slice('flag:'.length).toLowerCase()
        return (
          <span className="lyra-inline-flag-wrap">
            <img className="lyra-inline-flag" src={`/flags-flat/${code}.webp`} alt="" />
            {children}
          </span>
        )
      }
      // Site link: site:UUID (LLM-emitted) or lyra-site:id:lon:lat (legacy enricher)
      if (href?.startsWith('site:') || href?.startsWith('lyra-site:')) {
        const siteId = href.startsWith('site:')
          ? href.slice('site:'.length)
          : href.slice('lyra-site:'.length).split(':')[0]
        // Q5: Validate UUID format to prevent path traversal via crafted links
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(siteId)) return <span>{children}</span>
        return (
          <SiteChip
            siteId={siteId}
            onOpenPopup={(site) => {
              if (onOpenSitePopup) { onOpenSitePopup(site); onClose() }
              else setSelectedSite(site)
            }}
            onFlyTo={onFlyToSite}
            onHighlight={onHighlightSites}
          >
            {children}
          </SiteChip>
        )
      }
      // Coordinate link: lyra-coord:lat,lon
      if (href?.startsWith('lyra-coord:')) {
        const coordStr = href.slice('lyra-coord:'.length)
        const [lat, lon] = coordStr.split(',')
        const numLat = parseFloat(lat)
        const numLon = parseFloat(lon)
        return (
          <span className="lyra-inline-coord">
            <button
              className="lyra-inline-coord-link"
              title="Fly to location on globe"
              onClick={() => {
                if (onFlyToSite) {
                  onFlyToSite([numLon, numLat])
                } else {
                  navigateGlobeToCoords(numLat, numLon, true)
                }
              }}
            >
              <svg className="lyra-inline-coord-pin" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              </svg>
              <span>{lat}, {lon}</span>
            </button>
            <button
              className="lyra-inline-coord-copy"
              title="Copy coordinates"
              onClick={(e) => {
                const btn = e.currentTarget
                navigator.clipboard.writeText(`${lat}, ${lon}`).catch(() => {})
                btn.classList.add('copied')
                setTimeout(() => btn.classList.remove('copied'), 2000)
              }}
            >
              <svg className="lyra-inline-coord-copy-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              <svg className="lyra-inline-coord-check-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </button>
          </span>
        )
      }
      // Video link: lyra-video:VIDEO_ID:TIMESTAMP
      if (href?.startsWith('lyra-video:')) {
        const parts = href.slice('lyra-video:'.length).split(':')
        const videoId = parts[0]
        const timestamp = parseInt(parts[1] || '0', 10) || 0
        // Look up by video_id — no index mismatch possible
        const newsItem = sidebarNewsRef.current.find(n => n.video_id === videoId)
          ?? { video_id: videoId, headline: '', channel: String(children) || '', timestamp_seconds: timestamp }
        return <LyraInlineVideo news={newsItem}>{children}</LyraInlineVideo>
      }
      // Empire link: empire:POLITY_ID — clickable badge that opens empire popup
      if (href?.startsWith('empire:')) {
        const polityId = href.slice('empire:'.length)
        if (!/^[a-z][a-z0-9_]+$/.test(polityId)) return <span>{children}</span>
        return (
          <button
            className="lyra-empire-chip"
            title={`View ${polityId}`}
            onClick={() => onOpenEmpirePopup?.(polityId)}
          >
            <svg className="lyra-empire-chip-icon" width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z"/>
            </svg>
            {children}
          </button>
        )
      }
      // Normal link — only allow http/https to block javascript: protocol XSS
      if (!href?.startsWith('http://') && !href?.startsWith('https://')) return <span>{children}</span>
      // Web citation link: [N] → superscript style
      const textContent = Array.isArray(children) ? children.join('') : String(children ?? '')
      if (/^\[\d+\]$/.test(textContent)) {
        return <a className="lyra-citation-link" href={href} target="_blank" rel="noopener noreferrer" title={href}>{textContent}</a>
      }
      return <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    },
    img: ({ src, alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) => {
      if (!src) return null
      return (
        <img
          {...props}
          src={src}
          alt={alt || ''}
          onError={(e) => { e.currentTarget.style.display = 'none' }}
          loading="lazy"
        />
      )
    },
  }), [onHighlightSites, onFlyToSite, onOpenSitePopup, onOpenEmpirePopup, onClose]) // sidebarNews accessed via ref — no re-render on news events

  // Auto-scroll: only if user hasn't scrolled up
  const lastMsg = messages[messages.length - 1]
  useEffect(() => {
    if (!userScrolledUpRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length, lastMsg?.content.length, lastMsg?.thinking?.length])

  // Track scroll position for FAB visibility
  useEffect(() => {
    const el = messagesContainerRef.current
    if (!el) return
    const onScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      setShowScrollFab(distFromBottom > 150)
      userScrolledUpRef.current = distFromBottom > 150
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [isAuthenticated]) // eslint-disable-line react-hooks/exhaustive-deps

  // Focus input when opening (if authenticated)
  useEffect(() => {
    if (isOpen && isAuthenticated) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen, isAuthenticated])

  // Auto-focus input on any keypress so the user can always type
  // without clicking the field first (better UX)
  useEffect(() => {
    if (!isOpen || !isAuthenticated) return
    const onKeyDown = (e: KeyboardEvent) => {
      // Skip if already focused, or if modifier keys are held (Ctrl+C, etc.)
      if (document.activeElement === inputRef.current) return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      // Skip non-printable keys (arrows, F-keys, Escape, etc.)
      if (e.key.length !== 1 && e.key !== 'Backspace') return
      // Skip if user is typing in another input/textarea
      const tag = (document.activeElement as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      inputRef.current?.focus()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isOpen, isAuthenticated])

  // Fetch credits when using Discord auth
  useEffect(() => {
    if (!authToken) return
    fetch(`${config.api.baseUrl}/auth/me`, {
      headers: { 'Authorization': `Bearer ${authToken}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) { setUserCredits(data.credits); setIsUnlimited(!!data.is_unlimited) }
        else {
          // Token expired/invalid — clear it
          localStorage.removeItem('an_auth_token')
          setAuthToken(null)
        }
      })
      .catch(() => {})
  }, [authToken])


  // Debounced site search
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)

    if (searchQuery.trim().length < 3) {
      setSearchResults([])
      setSearchLoading(false)
      return
    }

    setSearchLoading(true)
    searchDebounceRef.current = setTimeout(() => {
      searchAbortRef.current?.abort()
      const controller = new AbortController()
      searchAbortRef.current = controller

      const encoded = encodeURIComponent(searchQuery.trim())
      fetch(`${config.api.baseUrl}/sites/search?q=${encoded}&limit=30`, { signal: controller.signal })
        .then(res => res.json())
        .then(data => {
          if (controller.signal.aborted) return
          const parsed: SiteData[] = (data.sites || []).map((s: { id: string; n: string; la: number; lo: number; s: string; t?: string; p?: number; pn?: string; d?: string; cd?: string; c?: string; u?: string }) => ({
            id: s.id,
            title: s.n,
            coordinates: [s.lo, s.la] as [number, number],
            category: s.t || 'Unknown',
            period: resolvePeriod(s.pn, s.p),
            periodStart: s.p ?? null,
            location: s.c || '',
            description: s.d || '',
            cardDescription: s.cd,
            sourceId: s.s,
            sourceUrl: s.u,
          }))
          setSearchResults(parsed)
          setSearchLoading(false)
        })
        .catch(err => {
          if (err.name !== 'AbortError') {
            setSearchResults([])
            setSearchLoading(false)
          }
        })
    }, 300)

    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)
    }
  }, [searchQuery])

  // Close on Escape: pipeline panel → search panel → stop streaming → close modal
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (pipelineOpen) {
          setPipelineOpen(false)
          localStorage.setItem('lyra_pipeline_open', 'false')
        } else if (searchOpen) {
          setSearchOpen(false)
          setSearchQuery('')
          setSearchResults([])
        } else if (isStreaming) {
          abortRef.current?.abort()
        } else if (mode === 'modal') {
          onClose()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, isStreaming, searchOpen, pipelineOpen, onClose, mode])

  const clearAuth = useCallback(() => {
    localStorage.removeItem('an_auth_token')
    setAuthToken(null)
    setUserCredits(null)
    setIsUnlimited(false)
    setMessages([])
  }, [])

  const startNewChat = useCallback(() => {
    // Save current conversation if non-empty
    if (messages.length > 0) {
      const title = messages.find(m => m.role === 'user')?.content.slice(0, 50) || 'New conversation'
      saveConversation(conversationId, title, messages)
    }
    setConversationId(crypto.randomUUID())
    setMessages([])
    setSidebarNews([])
    setError(null)
    setShowHistory(false)
    setConversations(listConversations())
  }, [messages, conversationId])

  const loadChat = useCallback((id: string) => {
    // Save current conversation first if non-empty
    if (messages.length > 0) {
      const title = messages.find(m => m.role === 'user')?.content.slice(0, 50) || 'New conversation'
      saveConversation(conversationId, title, messages)
    }
    const loaded = loadConversation(id)
    setConversationId(id)
    setMessages(loaded)
    setSidebarNews([])
    setError(null)
    setShowHistory(false)
  }, [messages, conversationId])

  const handleDeleteConversation = useCallback((id: string) => {
    deleteConversation(id)
    setConversations(listConversations())
    // If we deleted the current conversation, start fresh
    if (id === conversationId) {
      setConversationId(crypto.randomUUID())
      setMessages([])
      setSidebarNews([])
    }
  }, [conversationId])

  const sendMessage = useCallback(async (text?: string) => {
    const messageText = text || input.trim()
    if (!messageText || isStreaming) return
    if (!authToken) return

    // Check credits (unlimited users bypass)
    if (!isUnlimited && userCredits !== null && userCredits <= 0) {
      setError(<>No credits remaining. Visit your <a href="/account.html" style={{ color: '#ff6b6b', textDecoration: 'underline' }}>Account page</a> for details.</>)
      return
    }

    setError(null)
    setInput('')
    lastUserMsgRef.current = messageText
    if (inputRef.current) inputRef.current.style.height = 'auto'
    // Reset sidebar for new query
    setSidebarNews([])

    // Add user message + assistant placeholder in one update (U2: avoid double re-render)
    const userMsg: LyraMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: messageText,
      timestamp: new Date(),
    }
    const assistantId = `assistant-${Date.now()}`
    const assistantMsg: LyraMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    }
    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)
    setLyraStatus(null)

    // Auto-open pipeline panel on new query (respects user preference)
    if (localStorage.getItem('lyra_pipeline_open') !== 'false') {
      setPipelineOpen(true)
      setSearchOpen(false)
    }
    setViewingPipelineFor(null) // Switch to latest trace

    // Build request
    const history = messages
      .filter(m => !m.isStreaming)
      .slice(-10) // Q4: Match server-side cap (agent takes history[-10:])
      .map(m => ({ role: m.role, content: m.content }))

    const body = {
      message: messageText,
      context_type: contextType,
      context_id: contextId,
      context_year: contextYear,
      history,
      backend: 'anthropic',
      web_search: webSearchEnabled,
    }

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch(`${config.api.baseUrl}/lyra/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!response.ok) {
        // Handle auth errors — reset auth state
        if (response.status === 401 || response.status === 403) {
          clearAuth()
          throw new Error('Session expired. Please re-authenticate.')
        }
        const err = await response.json().catch(() => ({ detail: 'Request failed' }))
        if (response.status === 429) {
          throw new Error(err.detail || 'Rate limited. Please wait.')
        }
        if (response.status === 409) throw new Error(err.detail || 'You already have a request queued.')
        if (response.status === 503) throw new Error(err.detail || 'Queue is full. Try again later.')
        throw new Error(err.detail || `HTTP ${response.status}`)
      }

      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let collectedSites: SiteHighlight[] = []
      let eventType = ''
      let receivedDone = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              // Use data.type from JSON payload (always present, immune to chunk splitting)
              const type = data.type || eventType || ''

              if (type === 'thinking' && data.content) {
                setLyraStatus('Thinking...')
                // U1: Batch thinking tokens — accumulate in ref, flush every 100ms
                const buf = thinkingBufferRef.current
                buf.content += data.content
                buf.assistantId = assistantId
                if (!buf.timer) {
                  buf.timer = setTimeout(() => {
                    const pending = buf.content
                    buf.content = ''
                    buf.timer = null
                    if (pending) {
                      setMessages(prev => prev.map(m =>
                        m.id === buf.assistantId
                          ? { ...m, thinking: (m.thinking || '') + pending }
                          : m
                      ))
                    }
                  }, 100)
                }
              } else if (type === 'diffusion' && data.content) {
                setLyraStatus(null)
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: data.content }
                    : m
                ))
              } else if (type === 'status' && data.content) {
                // Pre-tool-call preamble: move streamed tokens to a status line
                // and reset content so the real answer starts clean
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, statusLines: [...(m.statusLines || []), data.content], content: '' }
                    : m
                ))
              } else if (type === 'sites' && data.sites) {
                collectedSites = data.sites
                const disc = addDiscoveries(data.sites.map((s: { id: string }) => s.id))
                if (disc.newCount > 0) setTotalDiscoveries(disc.total)
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, sites: data.sites, discoveries: disc.newCount > 0 ? disc : undefined }
                    : m
                ))
              } else if (type === 'news' && data.news) {
                // Merge & deduplicate by video_id+headline
                setSidebarNews(prev => {
                  const keys = new Set(prev.map(n => `${n.video_id}::${n.headline}`))
                  const merged = [...prev]
                  for (const n of data.news as NewsHighlight[]) {
                    const key = `${n.video_id}::${n.headline}`
                    if (!keys.has(key)) { merged.push(n); keys.add(key) }
                  }
                  return merged
                })
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, news: data.news }
                    : m
                ))
              } else if (type === 'done') {
                receivedDone = true
                // U1: Flush any buffered thinking tokens before finalizing
                const buf = thinkingBufferRef.current
                if (buf.timer) { clearTimeout(buf.timer); buf.timer = null }
                if (buf.content) {
                  const pending = buf.content
                  buf.content = ''
                  setMessages(prev => prev.map(m =>
                    m.id === assistantId
                      ? { ...m, thinking: (m.thinking || '') + pending }
                      : m
                  ))
                }
                const tokens = data.metadata?.tokens ?? undefined
                const structuredOutput = data.metadata?.structured_output ?? undefined
                // Update credits from done event (Discord auth only)
                if (data.metadata?.credits_remaining !== undefined) {
                  setUserCredits(data.metadata.credits_remaining)
                }
                if (data.metadata?.chat_streak) {
                  setChatStreak(data.metadata.chat_streak)
                }
                setMessages(prev => {
                  const updated = prev.map(m =>
                    m.id === assistantId
                      ? {
                          ...m,
                          isStreaming: false,
                          tokens,
                          structuredOutput,
                          pipelineTrace: m.pipelineTrace
                            ? { ...m.pipelineTrace, isLive: false }
                            : undefined,
                        }
                      : m
                  )
                  // Auto-save conversation
                  const title = updated.find(m => m.role === 'user')?.content.slice(0, 50) || 'New conversation'
                  saveConversation(conversationId, title, updated)
                  setConversations(listConversations())
                  return updated
                })
              } else if (type === 'achievements' && data.achievements) {
                notifyAchievements(data.achievements)
              } else if (type === 'pipeline' && data.stage) {
                // Pipeline events — only update trace, no status narration
                // (diffusion crystallizing effect IS the visual feedback)
                const pEvent: PipelineEvent = { stage: data.stage, status: data.status, duration_ms: data.duration_ms ?? null, meta: data.meta ?? null }
                setMessages(prev => prev.map(m => {
                  if (m.id !== assistantId) return m
                  const trace = m.pipelineTrace ?? { nodes: [], isLive: true }
                  return { ...m, pipelineTrace: { ...trace, nodes: applyPipelineEvent(trace.nodes, pEvent) } }
                }))
              } else if (type === 'error') {
                throw new Error(data.error || 'Stream error')
              }
            } catch (e) {
              if (e instanceof SyntaxError) continue
              throw e
            }
          }
        }
      }

      // Stream ended without a done event — finalize the message so it doesn't hang
      if (!receivedDone) {
        setMessages(prev => prev.map(m =>
          m.id === assistantId
            ? { ...m, isStreaming: false, content: m.content || (m.statusLines?.length ? '' : '') }
            : m
        ))
        if (!abortRef.current?.signal.aborted) {
          setError('Response was interrupted. Try again.')
        }
      }

      // Highlight sites on globe
      if (collectedSites.length > 0 && onHighlightSites) {
        onHighlightSites(collectedSites.map(s => s.id).filter(Boolean))
      }

    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        setMessages(prev => prev.map(m =>
          m.id === assistantId
            ? { ...m, content: m.content + '\n\n*[Stopped]*', isStreaming: false }
            : m
        ))
      } else {
        const errMsg = (e as Error).message || 'An error occurred'
        setError(errMsg)
        // Keep the message if it has content/thinking, otherwise remove it
        setMessages(prev => {
          const msg = prev.find(m => m.id === assistantId)
          if (msg && (msg.content || msg.thinking)) {
            return prev.map(m => m.id === assistantId ? { ...m, isStreaming: false } : m)
          }
          return prev.filter(m => m.id !== assistantId)
        })
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
      setLyraStatus(null)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [input, isStreaming, authToken, userCredits, isUnlimited, messages, contextType, contextId, contextYear, onHighlightSites, clearAuth, conversationId])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }, [sendMessage])

  const handleExampleClick = useCallback((question: string) => {
    sendMessage(question)
  }, [sendMessage])

  if (!isOpen) return null

  const isPage = mode === 'page'

  const header = isPage ? (
    <PageHeader
      speechBubble="I can search 1M+ sites, find news, and answer archaeology questions!"
      onAvatarClick={() => setShowDossier(true)}
      currentPage="lyra"
      rightSection={
        <div className="lyra-chat-header-actions">
          {authToken && userCredits !== null && (
            <span className="lyra-credits-badge" title="Lyra credits remaining">
              {isUnlimited ? '∞' : userCredits.toLocaleString()} credits
            </span>
          )}
          {chatStreak > 1 && (
            <span className="lyra-gamify-chip" title={`${chatStreak}-day chat streak`}>
              {'\uD83D\uDD25'} {chatStreak}
            </span>
          )}
          {totalDiscoveries > 0 && (
            <span className="lyra-gamify-chip" title={`${totalDiscoveries} sites discovered with Lyra`}>
              {'\uD83E\uDDED'} {totalDiscoveries}
            </span>
          )}
          {messages.length > 0 && (
            <button className="lyra-chat-icon-btn" onClick={startNewChat} title="New chat">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
            </button>
          )}
          <button className="lyra-chat-icon-btn" onClick={() => { setConversations(listConversations()); setShowHistory(!showHistory) }} title="Chat history">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
            </svg>
          </button>
          <button className={`lyra-chat-icon-btn lp-header-btn${pipelineOpen ? ' active' : ''}${messages.some(m => m.pipelineTrace) ? ' has-trace' : ''}`} onClick={() => { const next = !pipelineOpen; setPipelineOpen(next); localStorage.setItem('lyra_pipeline_open', String(next)); if (next) { setSearchOpen(false); setSearchQuery(''); setSearchResults([]) } }} title="Pipeline trace">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" />
              <circle cx="12" cy="18" r="2.5" />
              <line x1="6" y1="8.5" x2="12" y2="15.5" /><line x1="18" y1="8.5" x2="12" y2="15.5" />
            </svg>
          </button>
          <button className={`lyra-chat-icon-btn${searchOpen ? ' active' : ''}`} onClick={() => { const next = !searchOpen; setSearchOpen(next); if (next) { setPipelineOpen(false); localStorage.setItem('lyra_pipeline_open', 'false') } else { setSearchQuery(''); setSearchResults([]) } }} title="Search sites">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
          {isStreaming && (
            <button className="lyra-chat-stop-btn" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          )}
        </div>
      }
    >
      <span className="page-header-title">Lyra</span>
    </PageHeader>
  ) : (
    <div className="lyra-chat-header">
      <div className="lyra-chat-header-left">
        <img
          src="/lyra.gif"
          alt="Lyra"
          className="lyra-chat-avatar lyra-avatar-clickable"
          onClick={() => setShowDossier(true)}
        />
        <div>
          <div className="lyra-chat-header-name">Lyra Whiskerbyte</div>
          {messages.length === 0 ? (
            <div className="lyra-chat-speech-bubble">
              I can search 1M+ sites, find news, and answer archaeology questions!
            </div>
          ) : (
            <div className="lyra-chat-header-status">Archaeological Agent</div>
          )}
        </div>
      </div>
      <div className="lyra-chat-header-right">
        {authToken && userCredits !== null && (
          <span className="lyra-credits-badge" title="Lyra credits remaining">
            {isUnlimited ? '∞' : userCredits.toLocaleString()} credits
          </span>
        )}
        {chatStreak > 1 && (
          <span className="lyra-gamify-chip" title={`${chatStreak}-day chat streak`}>
            {'\uD83D\uDD25'} {chatStreak}
          </span>
        )}
        {totalDiscoveries > 0 && (
          <span className="lyra-gamify-chip" title={`${totalDiscoveries} sites discovered with Lyra`}>
            {'\uD83E\uDDED'} {totalDiscoveries}
          </span>
        )}
        {messages.length > 0 && (
          <button className="lyra-chat-icon-btn" onClick={startNewChat} title="New chat">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
          </button>
        )}
        <button className="lyra-chat-icon-btn" onClick={() => { setConversations(listConversations()); setShowHistory(!showHistory) }} title="Chat history">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
          </svg>
        </button>
        <button className={`lyra-chat-icon-btn lp-header-btn${pipelineOpen ? ' active' : ''}${messages.some(m => m.pipelineTrace) ? ' has-trace' : ''}`} onClick={() => { const next = !pipelineOpen; setPipelineOpen(next); localStorage.setItem('lyra_pipeline_open', String(next)); if (next) { setSearchOpen(false); setSearchQuery(''); setSearchResults([]) } }} title="Pipeline trace">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" />
            <circle cx="12" cy="18" r="2.5" />
            <line x1="6" y1="8.5" x2="12" y2="15.5" /><line x1="18" y1="8.5" x2="12" y2="15.5" />
          </svg>
        </button>
        <button className={`lyra-chat-icon-btn${searchOpen ? ' active' : ''}`} onClick={() => { const next = !searchOpen; setSearchOpen(next); if (next) { setPipelineOpen(false); localStorage.setItem('lyra_pipeline_open', 'false') } else { setSearchQuery(''); setSearchResults([]) } }} title="Search sites">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </button>
        {isStreaming && (
          <button className="lyra-chat-stop-btn" onClick={() => abortRef.current?.abort()}>
            Stop
          </button>
        )}
        <a className="lyra-chat-icon-btn" href="/lyra.html" target="_blank" rel="noopener noreferrer" title="Open in new tab">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </a>
        <button className="lyra-chat-close-btn" onClick={onClose}>
          <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
          </svg>
        </button>
      </div>
    </div>
  )

  const historyPanel = showHistory && (
    <div className="lyra-chat-history-overlay" onClick={() => setShowHistory(false)}>
      <div className="lyra-chat-history-panel" onClick={e => e.stopPropagation()}>
        <div className="lyra-chat-history-header">
          <span>Chat History</span>
          <button className="lyra-chat-close-btn" onClick={() => setShowHistory(false)}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
            </svg>
          </button>
        </div>
        <div className="lyra-chat-history-list">
          {conversations.length === 0 ? (
            <div className="lyra-chat-history-empty">No conversations yet</div>
          ) : (
            conversations.map(c => (
              <div
                key={c.id}
                className={`lyra-chat-history-item${c.id === conversationId ? ' active' : ''}`}
                onClick={() => loadChat(c.id)}
              >
                <div className="lyra-chat-history-item-title">{c.title}</div>
                <div className="lyra-chat-history-item-date">
                  {formatRelativeDate(new Date(c.updatedAt).toISOString())}
                </div>
                <button
                  className="lyra-chat-history-item-delete"
                  onClick={e => { e.stopPropagation(); handleDeleteConversation(c.id) }}
                  title="Delete conversation"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )

  const modalContent = (
    <div className={`lyra-chat-modal${pipelineOpen ? ' lyra-chat-modal--with-pipeline' : ''}`}>
      {header}
      {historyPanel}

        {/* Auth gate or chat content */}
        {!isAuthenticated ? (
          <div className="lyra-chat-messages">
            <div className="lyra-auth-gate">
              <img src="/lyra.gif" alt="Lyra" className="lyra-auth-gate-avatar" />
              <div className="lyra-auth-gate-name">Lyra Whiskerbyte</div>
              <div className="lyra-auth-gate-subtitle">Sign in to chat</div>
              <button
                className="lyra-auth-discord-btn"
                onClick={() => { window.location.href = `${config.api.baseUrl}/auth/discord?return_to=${encodeURIComponent(window.location.pathname + window.location.search)}` }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.36-.698.772-1.362 1.225-1.993a.076.076 0 0 0-.041-.107 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.12-.094.246-.194.373-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
                </svg>
                Continue with Discord
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Body: chat + sidebar */}
            <div className="lyra-chat-body">
              {/* Left: chat messages */}
              <div className="lyra-chat-main">
                <div className="lyra-chat-messages" ref={messagesContainerRef} role="log" aria-live="polite">
                  {messages.length === 0 ? (
                    <LyraWelcome
                      mode={mode}
                      contextType={contextType}
                      onPromptClick={handleExampleClick}
                      disabled={isStreaming}
                    />
                  ) : (
                    messages.map(msg => (
                      <div key={msg.id}>
                        {/* Thinking bubble — separate from answer */}
                        {msg.role === 'assistant' && msg.statusLines && msg.statusLines.length > 0 && (
                          <div className="lyra-chat-msg lyra-chat-msg-assistant">
                            <img src="/lyra.gif" alt="Lyra" className="lyra-chat-msg-avatar" />
                            <div className="lyra-chat-thinking-bubble">
                              {msg.statusLines.map((s, i) => (
                                <p key={i}>{getToolIcon(s)}{s}</p>
                              ))}
                            </div>
                          </div>
                        )}
                        {/* Typing dots — before any tokens arrive */}
                        {msg.role === 'assistant' && msg.isStreaming && !msg.content && !msg.thinking && !lyraStatus && (
                          <div className="lyra-chat-msg lyra-chat-msg-assistant">
                            <img src="/lyra.gif" alt="Lyra" className="lyra-chat-msg-avatar" />
                            <div className="lyra-chat-typing-dots" role="status" aria-label="Lyra is typing">
                              <span /><span /><span />
                            </div>
                          </div>
                        )}
                        {/* Status narration — pipeline progress messages */}
                        {msg.role === 'assistant' && msg.isStreaming && !msg.content && lyraStatus && (
                          <div className="lyra-chat-msg lyra-chat-msg-assistant">
                            <img src="/lyra.gif" alt="Lyra" className="lyra-chat-msg-avatar" />
                            <div className="lyra-chat-status-narration" role="status">
                              <span className="lyra-status-dot" />
                              <span>{lyraStatus}</span>
                            </div>
                          </div>
                        )}
                        {/* Model thinking/reasoning (collapsible) */}
                        {msg.role === 'assistant' && msg.thinking && (
                          <div className="lyra-chat-msg lyra-chat-msg-assistant">
                            <img src="/lyra.gif" alt="Lyra" className="lyra-chat-msg-avatar" />
                            <details className="lyra-thinking-block" open={msg.isStreaming && !msg.content}>
                              <summary className="lyra-thinking-summary">
                                {msg.isStreaming && !msg.content ? 'Thinking...' : 'Thought process'}
                              </summary>
                              <div className="lyra-thinking-content">{msg.thinking}</div>
                            </details>
                          </div>
                        )}
                        {/* Main message bubble */}
                        {(msg.role === 'user' || msg.content) && (
                          <div className={`lyra-chat-msg lyra-chat-msg-${msg.role}`}>
                            {msg.role === 'assistant' && (
                              <img src="/lyra.gif" alt="Lyra" className="lyra-chat-msg-avatar" />
                            )}
                            <div className="lyra-chat-msg-content">
                              {msg.role === 'assistant' ? (
                                <div className="lyra-chat-msg-text">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents} urlTransform={lyraUrlTransform}>
                                    {(() => {
                                      let text = enrichLyraContent(msg.content)
                                      // Convert [N] web citations to clickable links
                                      const links = msg.structuredOutput?.links as Array<{ citation?: number; text?: string; url?: string }> | undefined
                                      if (links?.length) {
                                        const urlMap = new Map(links.map(l => [l.citation ?? 0, l.url ?? '']))
                                        text = text.replace(/(?<!\[)\[(\d+)\](?!\()/g, (_m, n) => {
                                          const url = urlMap.get(Number(n))
                                          return url ? `[\\[${n}\\]](${url})` : `[${n}]`
                                        })
                                      }
                                      return text
                                    })()}
                                  </ReactMarkdown>
                                </div>
                              ) : (
                                <>
                                  <div className="lyra-chat-msg-text">
                                    {msg.content}
                                  </div>
                                  <div className="lyra-chat-msg-time">
                                    {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                  </div>
                                </>
                              )}
                              {msg.role === 'assistant' && !msg.isStreaming && msg.content && (
                                <button
                                  className="lyra-chat-copy-btn"
                                  title="Copy message"
                                  onClick={(e) => {
                                    navigator.clipboard.writeText(msg.content).catch(() => {})
                                    const btn = e.currentTarget
                                    btn.classList.add('copied')
                                    setTimeout(() => btn.classList.remove('copied'), 2000)
                                  }}
                                >
                                  <svg className="lyra-copy-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                                  </svg>
                                  <svg className="lyra-check-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <polyline points="20 6 9 17 4 12" />
                                  </svg>
                                </button>
                              )}
                              {msg.role === 'assistant' && !msg.isStreaming && msg.structuredOutput && (
                                <details className="lyra-structured-output">
                                  <summary className="lyra-structured-output-toggle">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                      <path d="M4 7h16M4 12h16M4 17h10" />
                                    </svg>
                                    Structured data
                                    <span className="lyra-so-count">
                                      {(() => {
                                        const so = msg.structuredOutput!
                                        const counts: string[] = []
                                        if (so.sites?.length) counts.push(`${so.sites.length} site${so.sites.length > 1 ? 's' : ''}`)
                                        if (so.coords?.length) counts.push(`${so.coords.length} coord${so.coords.length > 1 ? 's' : ''}`)
                                        if (so.videos?.length) counts.push(`${so.videos.length} video${so.videos.length > 1 ? 's' : ''}`)
                                        if (so.empires?.length) counts.push(`${so.empires.length} empire${so.empires.length > 1 ? 's' : ''}`)
                                        if (so.images?.length) counts.push(`${so.images.length} image${so.images.length > 1 ? 's' : ''}`)
                                        if (so.links?.length) counts.push(`${so.links.length} link${so.links.length > 1 ? 's' : ''}`)
                                        if (so.countries?.length) counts.push(`${so.countries.length} flag${so.countries.length > 1 ? 's' : ''}`)
                                        return counts.join(' · ')
                                      })()}
                                    </span>
                                  </summary>
                                  <div className="lyra-so-content">
                                    {msg.structuredOutput.sites?.length ? (
                                      <div className="lyra-so-section">
                                        <div className="lyra-so-label">Sites</div>
                                        {msg.structuredOutput.sites.map((s, i) => (
                                          <div key={i} className="lyra-so-item">
                                            <span className="lyra-so-marker">{s.marker}</span>
                                            <span className="lyra-so-name">{s.name}</span>
                                            <span className="lyra-so-id" title={s.id}>{s.id.slice(0, 8)}</span>
                                          </div>
                                        ))}
                                      </div>
                                    ) : null}
                                    {msg.structuredOutput.coords?.length ? (
                                      <div className="lyra-so-section">
                                        <div className="lyra-so-label">Coordinates</div>
                                        {msg.structuredOutput.coords.map((c, i) => (
                                          <div key={i} className="lyra-so-item">
                                            <span className="lyra-so-marker">{c.marker}</span>
                                            <span className="lyra-so-name">{c.lat.toFixed(4)}, {c.lon.toFixed(4)}</span>
                                          </div>
                                        ))}
                                      </div>
                                    ) : null}
                                    {msg.structuredOutput.videos?.length ? (
                                      <div className="lyra-so-section">
                                        <div className="lyra-so-label">Videos</div>
                                        {msg.structuredOutput.videos.map((v, i) => {
                                          const ytUrl = v.timestamp_seconds
                                            ? `https://www.youtube.com/watch?v=${v.video_id}&t=${v.timestamp_seconds}`
                                            : `https://www.youtube.com/watch?v=${v.video_id}`
                                          return (
                                            <div key={i} className="lyra-so-item">
                                              <span className="lyra-so-marker">{v.marker}</span>
                                              <a className="lyra-so-link" href={ytUrl} target="_blank" rel="noopener noreferrer">{v.channel}</a>
                                              <span className="lyra-so-id" title={v.video_id}>{v.video_id.slice(0, 8)}</span>
                                            </div>
                                          )
                                        })}
                                      </div>
                                    ) : null}
                                    {msg.structuredOutput.empires?.length ? (
                                      <div className="lyra-so-section">
                                        <div className="lyra-so-label">Empires</div>
                                        {msg.structuredOutput.empires.map((e, i) => (
                                          <div key={i} className="lyra-so-item">
                                            <span className="lyra-so-marker">{e.marker}</span>
                                            <span className="lyra-so-name">{e.name}</span>
                                            <span className="lyra-so-id">{e.polity_id}</span>
                                          </div>
                                        ))}
                                      </div>
                                    ) : null}
                                    {msg.structuredOutput.images?.length ? (
                                      <div className="lyra-so-section">
                                        <div className="lyra-so-label">Images</div>
                                        {msg.structuredOutput.images.map((im, i) => (
                                          <div key={i} className="lyra-so-item">
                                            <span className="lyra-so-marker">{im.marker}</span>
                                            <span className="lyra-so-name">{im.title}</span>
                                          </div>
                                        ))}
                                      </div>
                                    ) : null}
                                    {msg.structuredOutput.links?.length ? (
                                      <div className="lyra-so-section">
                                        <div className="lyra-so-label">Sources</div>
                                        {msg.structuredOutput.links.map((l, i) => (
                                          <div key={i} className="lyra-so-item">
                                            <span className="lyra-so-marker">[{String((l as Record<string, unknown>).citation ?? l.marker)}]</span>
                                            <a className="lyra-so-link" href={lyraUrlTransform(l.url)} target="_blank" rel="noopener noreferrer">{l.text}</a>
                                          </div>
                                        ))}
                                      </div>
                                    ) : null}
                                    {msg.structuredOutput.countries?.length ? (
                                      <div className="lyra-so-section">
                                        <div className="lyra-so-label">Countries</div>
                                        {msg.structuredOutput.countries.map((f, i) => (
                                          <div key={i} className="lyra-so-item">
                                            <span className="lyra-so-marker">{f.marker}</span>
                                            <span className="lyra-so-name">{f.name}</span>
                                            <span className="lyra-so-id">{f.code}</span>
                                          </div>
                                        ))}
                                      </div>
                                    ) : null}
                                  </div>
                                </details>
                              )}
                              {msg.role === 'assistant' && !msg.isStreaming && msg.tokens && (msg.tokens.input > 0 || msg.tokens.output > 0 || (msg.tokens.voyage ?? 0) > 0) && (
                                <div className="lyra-chat-msg-footer">
                                  <span className="lyra-chat-tokens">
                                    LLM: {msg.tokens.input + msg.tokens.output}
                                    {(msg.tokens.voyage ?? 0) > 0 && ` · Embed: ${msg.tokens.voyage}`}
                                    {(msg.tokens.web_search_requests ?? 0) > 0 && ` · Web: ${msg.tokens.web_search_requests}`}
                                  </span>
                                  {msg.pipelineTrace && (() => {
                                    const totalMs = msg.pipelineTrace.nodes
                                      .filter(n => n.stageId !== 'tool_call' && n.stageId !== 'done_credits' && n.duration_ms != null)
                                      .reduce((s, n) => s + (n.duration_ms ?? 0), 0)
                                    return (
                                      <button
                                        className="lp-msg-badge"
                                        title="View pipeline trace"
                                        onClick={() => { setViewingPipelineFor(msg.id); setPipelineOpen(true); localStorage.setItem('lyra_pipeline_open', 'true'); setSearchOpen(false) }}
                                      >
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                          <circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" />
                                          <circle cx="12" cy="18" r="2.5" />
                                          <line x1="6" y1="8.5" x2="12" y2="15.5" /><line x1="18" y1="8.5" x2="12" y2="15.5" />
                                        </svg>
                                        {totalMs < 1000 ? `${totalMs}ms` : `${(totalMs / 1000).toFixed(1)}s`}
                                      </button>
                                    )
                                  })()}
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                        {/* Discovery notification */}
                        {msg.role === 'assistant' && !msg.isStreaming && msg.discoveries && msg.discoveries.newCount > 0 && (
                          <div className="lyra-discovery-bar">
                            <span>\uD83D\uDD0D Discovered <span className="lyra-discovery-count">{msg.discoveries.newCount}</span> new site{msg.discoveries.newCount !== 1 ? 's' : ''}</span>
                            <span className="lyra-discovery-sep">|</span>
                            <span>{msg.discoveries.total} total explored</span>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                  <div ref={messagesEndRef} />
                </div>
                <button
                  className={`lyra-chat-scroll-fab${showScrollFab ? ' visible' : ''}`}
                  onClick={() => {
                    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
                    userScrolledUpRef.current = false
                  }}
                  aria-label="Scroll to bottom"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>
                {isStreaming && (
                  <div className="lyra-chat-inline-stop">
                    <button onClick={() => abortRef.current?.abort()}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                        <rect x="4" y="4" width="16" height="16" rx="2" />
                      </svg>
                      Stop generating
                    </button>
                  </div>
                )}
              </div>

              {/* Search panel — slides in from right */}
              {searchOpen && (
                <div className="lyra-chat-search-panel">
                  <div className="lyra-chat-search-header">
                    <input
                      className="lyra-chat-search-input"
                      type="text"
                      placeholder="Search sites..."
                      value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)}
                      autoFocus
                    />
                    <button className="lyra-chat-close-btn" onClick={() => { setSearchOpen(false); setSearchQuery(''); setSearchResults([]) }}>
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
                      </svg>
                    </button>
                  </div>
                  <div className="lyra-chat-search-results">
                    {searchLoading && (
                      <div className="lyra-chat-search-status">Searching...</div>
                    )}
                    {!searchLoading && searchQuery.trim().length >= 3 && searchResults.length === 0 && (
                      <div className="lyra-chat-search-status">No sites found</div>
                    )}
                    {!searchLoading && searchQuery.trim().length < 3 && searchQuery.trim().length > 0 && (
                      <div className="lyra-chat-search-status">Type at least 3 characters</div>
                    )}
                    {searchResults.map(site => (
                      <SiteResultItem
                        key={site.id}
                        id={site.id}
                        title={site.title}
                        category={site.category}
                        categoryColor={getCategoryColor(site.category)}
                        location={site.location}
                        period={site.period}
                        periodColor={getPeriodColor(site.period)}
                        showInfoBtn={false}
                        onMainClick={async () => {
                          try {
                            if (onFlyToSite && site.coordinates) {
                              onHighlightSites?.([site.id])
                              onFlyToSite(site.coordinates)
                            }
                            const res = await fetch(`${config.api.baseUrl}/sites/${site.id}`)
                            if (res.ok) {
                              const detail = await res.json()
                              const sd = apiDetailToSiteData(detail)
                              if (onOpenSitePopup) { onOpenSitePopup(sd); onClose() }
                              else setSelectedSite(sd)
                            }
                          } catch (err) {
                            console.error('Failed to fetch site detail:', err)
                          }
                        }}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Pipeline panel — slides in from right */}
              {pipelineOpen && (() => {
                const activePipelineMsg = viewingPipelineFor
                  ? messages.find(m => m.id === viewingPipelineFor)
                  : ((arr) => arr[arr.length - 1])(messages.filter(m => m.pipelineTrace))
                return (
                  <PipelinePanel
                    trace={activePipelineMsg?.pipelineTrace ?? null}
                    isLive={isStreaming && viewingPipelineFor === null}
                    onClose={() => { setPipelineOpen(false); localStorage.setItem('lyra_pipeline_open', 'false') }}
                  />
                )
              })()}
            </div>

            {/* Error */}
            {error && (
              <div className="lyra-chat-error" role="alert">
                <span>{error}</span>
                <div className="lyra-chat-error-actions">
                  {lastUserMsgRef.current && (
                    <button className="lyra-chat-retry-btn" onClick={() => { setError(null); sendMessage(lastUserMsgRef.current) }}>
                      Retry
                    </button>
                  )}
                  <button onClick={() => setError(null)}>Dismiss</button>
                </div>
              </div>
            )}

            {/* Input area */}
            <div className="lyra-chat-input-area">
              <div className="lyra-chat-input-toggles">
                <button
                  className={`lyra-web-search-toggle${webSearchEnabled ? ' active' : ''}`}
                  onClick={() => setWebSearchEnabled(prev => !prev)}
                  onMouseDown={(e) => e.preventDefault()}
                  title={webSearchEnabled ? 'Web search enabled (costs extra credits)' : 'Enable web search'}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                  Web
                  {webSearchEnabled && <span className="lyra-web-search-cost">+credits</span>}
                </button>
              </div>
              <div className="lyra-chat-input-row">
                <textarea
                  ref={inputRef}
                  className="lyra-chat-input"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onInput={(e) => {
                    const el = e.currentTarget
                    el.style.height = 'auto'
                    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask Lyra..."
                  rows={1}
                />
                <button
                  className="lyra-chat-send-btn"
                  onClick={() => sendMessage()}
                  disabled={isStreaming || !input.trim()}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </div>
            </div>
          </>
        )}
      </div>
  )

  const dossierModal = showDossier && (
    <Suspense fallback={null}>
      <LyraProfileModal onClose={() => setShowDossier(false)} />
    </Suspense>
  )

  if (isPage) {
    return (
      <div className="lyra-chat-page">
        {modalContent}
        {selectedSite && !onOpenSitePopup && (
          <SitePopupOverlay site={selectedSite} onClose={() => setSelectedSite(null)} />
        )}
        {dossierModal}
      </div>
    )
  }

  return createPortal(
    <div ref={focusTrapRef} className="lyra-chat-overlay" role="dialog" aria-modal="true" aria-label="Chat with Lyra" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      {modalContent}
      {selectedSite && !onOpenSitePopup && (
        <SitePopupOverlay site={selectedSite} onClose={() => setSelectedSite(null)} />
      )}
      {dossierModal}
    </div>,
    document.body
  )
}
