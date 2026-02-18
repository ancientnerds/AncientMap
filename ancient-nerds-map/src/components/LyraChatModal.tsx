/**
 * LyraChatModal — Chat with Lyra Wiskerbyte.
 *
 * Features:
 * - Admin auth gate (Bearer key + Turnstile)
 * - Text input with streaming responses
 * - SSE streaming with token-by-token display
 * - Conversation history (client-side)
 * - Context-aware: receives contextType, contextId, contextYear props
 * - Site highlighting on globe from tool results
 * - Confidence badge on responses
 * - Markdown rendering for assistant messages
 * - Three-column layout with sites & news sidebar
 * - Token usage display
 */

import { useState, useEffect, useRef, useCallback, useMemo, lazy, Suspense } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { config } from '../config'
import type { LyraContextType, LyraMessage, SiteHighlight, NewsHighlight, ConversationSummary } from '../types/ai'
import { getCategoryColor, getPeriodColor } from '../constants/colors'
import { enrichLyraContent, siteNameInContent, extractUnlinkedSiteNames } from '../utils/lyraContentEnricher'
import { formatRelativeDate } from '../utils/formatters'
import PageHeader from './layout/PageHeader'
import NewsCard, { newsHighlightToCardProps } from './news/NewsCard'
import SiteResultItem from './SiteResultItem'
import { SitePopupOverlay } from './SitePopupOverlay'
import LyraAuthGate from './LyraAuthGate'
import { apiDetailToSiteData } from '../utils/siteApi'
import { resolvePeriod } from '../data/sites'
import type { SiteData } from '../data/sites'
import './news/news-cards.css'

const LyraProfileModal = lazy(() => import('./LyraProfileModal'))

interface Props {
  isOpen: boolean
  onClose: () => void
  contextType?: LyraContextType
  contextId?: string
  contextYear?: number
  onHighlightSites?: (siteIds: string[]) => void
  onFlyToSite?: (coords: [number, number]) => void
  mode?: 'modal' | 'page'
}

const EXAMPLE_QUESTIONS: Record<LyraContextType, string[]> = {
  global: [
    'What sites are older than the Egyptian pyramids?',
    'Show me underwater ruins in the Mediterranean',
    'What has Lyra discovered this week?',
    'Tell me about the Roman Empire\'s military technology',
    'Any recent discoveries about Göbekli Tepe?',
    'Compare Angkor Wat and Teotihuacan',
  ],
  site: [
    'Tell me more about this site',
    'What other sites are nearby?',
    'What period does this belong to?',
    'Any recent news about this site?',
  ],
  empire: [
    'What weapons did this empire use?',
    'How large was their territory?',
    'Who were their main rivals?',
    'What caused their decline?',
  ],
  news: [
    'Summarize this discovery',
    'Where exactly was this found?',
    'How significant is this finding?',
    'Are there similar discoveries?',
  ],
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
    })),
  }
  const idx = all.findIndex(c => c.id === id)
  if (idx >= 0) all[idx] = serialized
  else all.unshift(serialized)
  // Keep max 50 conversations
  if (all.length > 50) all.length = 50
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
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
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
}

function loadAllStored(): StoredConversation[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const tier = pct >= 80 ? 'high' : pct >= 60 ? 'medium' : 'low'
  return (
    <span className={`lyra-chat-confidence ${tier}`}>
      {pct}% confidence
    </span>
  )
}

/* ---- Typewriter: reveals content char-by-char like fast human typing ---- */

function TypewriterMessage({
  content,
  isStreaming,
  sidebarSites,
  mdComponents,
}: {
  content: string
  isStreaming: boolean
  sidebarSites: SiteHighlight[]
  mdComponents: React.ComponentProps<typeof ReactMarkdown>['components']
}) {
  // For already-complete messages (loaded from history), show everything immediately
  const [revealedLen, setRevealedLen] = useState(() => isStreaming ? 0 : content.length)
  const contentRef = useRef(content)
  const streamingRef = useRef(isStreaming)
  const revealedRef = useRef(revealedLen)
  const containerRef = useRef<HTMLDivElement>(null)

  contentRef.current = content
  streamingRef.current = isStreaming

  useEffect(() => { revealedRef.current = revealedLen }, [revealedLen])

  useEffect(() => {
    // Already fully revealed (e.g. loaded conversation) — nothing to animate
    if (!streamingRef.current && revealedRef.current >= contentRef.current.length) return

    let running = true
    let lastTime = 0
    let nextDelay = 0

    const tick = (now: number) => {
      if (!running) return

      const cur = contentRef.current
      const revealed = revealedRef.current

      // Fully done — stop
      if (!streamingRef.current && revealed >= cur.length) return

      if (!lastTime) lastTime = now
      const elapsed = now - lastTime

      if (revealed < cur.length && elapsed >= nextDelay) {
        lastTime = now

        // Adaptive speed: type faster when buffer is large
        const buffered = cur.length - revealed
        const speed = buffered > 200 ? 0.25 : buffered > 100 ? 0.4 : buffered > 50 ? 0.6 : 1.0

        // Type 1-4 chars at a time (bursts)
        const chunk = 1 + Math.floor(Math.random() * 3)
        const next = Math.min(revealed + chunk, cur.length)

        // Delay based on character — simulate human rhythm
        const char = cur[revealed] || ''
        let base: number
        if (char === '.' || char === '!' || char === '?') {
          base = 80 + Math.random() * 120 // sentence end — think pause
        } else if (char === ',' || char === ':' || char === ';') {
          base = 40 + Math.random() * 60
        } else if (char === '\n') {
          base = 50 + Math.random() * 80 // new line — brief pause
        } else {
          base = 12 + Math.random() * 20 // fast typing
        }
        // Random micro-pauses (~5% chance) to feel human
        if (Math.random() < 0.05) base += 100 + Math.random() * 150
        nextDelay = base * speed

        revealedRef.current = next
        setRevealedLen(next)

        // Re-trigger red fade animation on the last element
        const el = containerRef.current
        if (el) {
          const last = el.querySelector(':scope > :last-child > :last-child')
            || el.querySelector(':scope > :last-child')
          if (last instanceof HTMLElement) {
            last.style.animation = 'none'
            last.offsetHeight // force reflow
            last.style.animation = ''
          }
        }
      }

      requestAnimationFrame(tick)
    }

    requestAnimationFrame(tick)
    return () => { running = false }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const isTyping = isStreaming || revealedLen < content.length
  const partialContent = isTyping ? content.substring(0, revealedLen) : content
  const displayedContent = enrichLyraContent(partialContent, sidebarSites)

  return (
    <div ref={containerRef} className={`lyra-chat-msg-text${isTyping ? ' streaming' : ''}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents} urlTransform={(url) => {
        const colonIndex = url.indexOf(':');
        if (colonIndex === -1) return url;
        const protocol = url.trim().slice(0, colonIndex);
        if (['http', 'https', 'mailto'].includes(protocol.toLowerCase())) return url;
        return '';
      }}>
        {displayedContent || '\u200B'}
      </ReactMarkdown>
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
  mode = 'modal',
}: Props) {
  const [messages, setMessages] = useState<LyraMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sidebarSites, setSidebarSites] = useState<SiteHighlight[]>([])
  const [sidebarNews, setSidebarNews] = useState<NewsHighlight[]>([])
  const [selectedSite, setSelectedSite] = useState<SiteData | null>(null)
  const [mobilePanelOpen, setMobilePanelOpen] = useState<'sites' | 'news' | null>(null)
  const [showDossier, setShowDossier] = useState(false)
  const [conversationId, setConversationId] = useState<string>(() => crypto.randomUUID())
  const [conversations, setConversations] = useState<ConversationSummary[]>(() => listConversations())
  const [showHistory, setShowHistory] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SiteData[]>([])
  const [searchLoading, setSearchLoading] = useState(false)

  // Auth state — hydrate from sessionStorage
  const [adminKey, setAdminKey] = useState<string | null>(() =>
    sessionStorage.getItem('lyra_admin_key')
  )
  const isAuthenticated = !!adminKey

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const searchAbortRef = useRef<AbortController | null>(null)
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Abort in-flight SSE stream + search on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      searchAbortRef.current?.abort()
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)
    }
  }, [])

  // Sort news by relevance (highest first)
  const sortedNews = useMemo(
    () => [...sidebarNews].sort((a, b) => (b.relevance ?? 0) - (a.relevance ?? 0)),
    [sidebarNews],
  )

  const hasNews = sortedNews.length > 0

  // Custom react-markdown components for interactive content
  const mdComponents = useMemo(() => ({
    a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) => {
      // Site link: lyra-site:id:lon:lat
      if (href?.startsWith('lyra-site:')) {
        const parts = href.slice('lyra-site:'.length).split(':')
        const siteId = parts[0]
        const lon = parseFloat(parts[1])
        const lat = parseFloat(parts[2])
        // Extract plain text from children for copy
        const text = Array.isArray(children)
          ? children.map(c => (typeof c === 'string' ? c : '')).join('')
          : typeof children === 'string' ? children : ''
        return (
          <span className="lyra-inline-site-wrap">
            <button
              className="lyra-inline-site"
              onClick={async () => {
                try {
                  if (onFlyToSite) {
                    onHighlightSites?.([siteId])
                    if (!isNaN(lon) && !isNaN(lat)) onFlyToSite([lon, lat])
                  }
                  const res = await fetch(`${config.api.baseUrl}/sites/${siteId}`)
                  if (res.ok) {
                    const detail = await res.json()
                    setSelectedSite(apiDetailToSiteData(detail))
                  }
                } catch (err) {
                  console.error('Failed to fetch site detail:', err)
                }
              }}
            >
              {children}
            </button>
            {text && (
              <button
                className="lyra-inline-copy"
                title="Copy site name"
                onClick={(e) => {
                  const btn = e.currentTarget
                  navigator.clipboard.writeText(text).catch(() => {})
                  btn.classList.add('copied')
                  setTimeout(() => btn.classList.remove('copied'), 2000)
                }}
              >
                <svg className="lyra-inline-copy-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                <svg className="lyra-inline-check-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </button>
            )}
          </span>
        )
      }
      // Coordinate link: lyra-coord:lat,lon
      if (href?.startsWith('lyra-coord:')) {
        const coordStr = href.slice('lyra-coord:'.length)
        const [lat, lon] = coordStr.split(',')
        return (
          <span className="lyra-inline-coord">
            <svg className="lyra-inline-coord-pin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="2" y1="12" x2="22" y2="12" />
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
            <span className="lyra-inline-coord-text">{lat}, {lon}</span>
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
      // Normal link
      return <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    },
    img: ({ src, alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) => {
      // Inline country flag
      if (alt === 'flag' && src?.includes('/flags-flat/')) {
        return <img src={src} alt="" className="lyra-inline-flag" {...props} />
      }
      return <img src={src} alt={alt} {...props} />
    },
  }), [onHighlightSites, onFlyToSite])

  // Auto-scroll: always smooth — typewriter controls reveal speed
  const lastMsg = messages[messages.length - 1]
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, lastMsg?.content.length])

  // Focus input when opening (if authenticated)
  useEffect(() => {
    if (isOpen && isAuthenticated) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen, isAuthenticated])

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
          const parsed: SiteData[] = (data.sites || []).map((s: { id: string; n: string; la: number; lo: number; s: string; t?: string; p?: number; pn?: string; d?: string; c?: string; u?: string }) => ({
            id: s.id,
            title: s.n,
            coordinates: [s.lo, s.la] as [number, number],
            category: s.t || 'Unknown',
            period: resolvePeriod(s.pn, s.p),
            periodStart: s.p ?? null,
            location: s.c || '',
            description: s.d || '',
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

  // Close on Escape: search panel → stop streaming → close modal
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (searchOpen) {
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
  }, [isOpen, isStreaming, searchOpen, onClose, mode])

  const handleAuthenticated = useCallback((key: string) => {
    setAdminKey(key)
  }, [])

  const clearAuth = useCallback(() => {
    sessionStorage.removeItem('lyra_admin_key')
    setAdminKey(null)
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
    setSidebarSites([])
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
    setSidebarSites([])
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
      setSidebarSites([])
      setSidebarNews([])
    }
  }, [conversationId])

  const sendMessage = useCallback(async (text?: string) => {
    const messageText = text || input.trim()
    if (!messageText) return
    if (!adminKey) return

    setError(null)
    setInput('')
    // Reset sidebar for new query
    setSidebarSites([])
    setSidebarNews([])

    // Add user message
    const userMsg: LyraMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: messageText,
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, userMsg])

    // Create assistant placeholder
    const assistantId = `assistant-${Date.now()}`
    const assistantMsg: LyraMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    }
    setMessages(prev => [...prev, assistantMsg])
    setIsStreaming(true)

    // Build request
    const history = messages
      .filter(m => !m.isStreaming)
      .map(m => ({ role: m.role, content: m.content }))

    const body = {
      message: messageText,
      context_type: contextType,
      context_id: contextId,
      context_year: contextYear,
      history,
    }

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch(`${config.api.baseUrl}/lyra/admin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${adminKey}`,
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
        throw new Error(err.detail || `HTTP ${response.status}`)
      }

      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let collectedSites: SiteHighlight[] = []
      let eventType = ''
      let fullContent = ''

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

              if (type === 'token' && data.content) {
                fullContent += data.content
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: m.content + data.content }
                    : m
                ))
              } else if (type === 'status' && data.content) {
                // Pre-tool-call preamble: move streamed tokens to a status line
                // and reset content so the real answer starts clean
                fullContent = ''
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, statusLines: [...(m.statusLines || []), data.content], content: '' }
                    : m
                ))
              } else if (type === 'sites' && data.sites) {
                collectedSites = data.sites
                // Merge & deduplicate by id
                setSidebarSites(prev => {
                  const ids = new Set(prev.map(s => s.id))
                  const merged = [...prev]
                  for (const s of data.sites as SiteHighlight[]) {
                    if (!ids.has(s.id)) { merged.push(s); ids.add(s.id) }
                  }
                  return merged
                })
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, sites: data.sites }
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
                const avgRelevance = data.metadata?.avg_relevance ?? null
                const tokens = data.metadata?.tokens ?? undefined
                setMessages(prev => {
                  const updated = prev.map(m =>
                    m.id === assistantId
                      ? { ...m, isStreaming: false, confidence: avgRelevance, tokens }
                      : m
                  )
                  // Filter sidebar to sites Lyra actually mentioned (flexible variant matching)
                  const finalContent = updated.find(m => m.id === assistantId)?.content
                  if (finalContent) {
                    const lower = finalContent.toLowerCase()
                    setSidebarSites(prev => prev.filter(s => siteNameInContent(s.name, lower)))
                  }
                  // Auto-save conversation
                  const title = updated.find(m => m.role === 'user')?.content.slice(0, 50) || 'New conversation'
                  saveConversation(conversationId, title, updated)
                  setConversations(listConversations())
                  return updated
                })
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

      // Highlight sites on globe
      if (collectedSites.length > 0 && onHighlightSites) {
        onHighlightSites(collectedSites.map(s => s.id).filter(Boolean))
      }

      // Post-search: find site names Lyra mentioned that aren't in Qdrant results
      if (fullContent) {
        const candidates = extractUnlinkedSiteNames(fullContent, collectedSites)
        if (candidates.length > 0) {
          Promise.all(candidates.map(name =>
            fetch(`${config.api.baseUrl}/sites/search?q=${encodeURIComponent(name)}&limit=3`)
              .then(r => r.json())
              .then(data => {
                const sites = (data.sites || []) as { id: string; n: string; la: number; lo: number; t?: string; c?: string; pn?: string }[]
                const nameLower = name.toLowerCase()
                const match = sites.find(s => s.n.toLowerCase().startsWith(nameLower))
                  || sites.find(s => nameLower.startsWith(s.n.toLowerCase()))
                if (!match) return null
                return { id: match.id, name: match.n, lat: match.la, lon: match.lo, site_type: match.t, country: match.c, period_name: match.pn } as SiteHighlight
              })
              .catch(() => null)
          )).then(results => {
            const newSites = results.filter((s): s is SiteHighlight => s !== null)
            if (newSites.length > 0) {
              setSidebarSites(prev => {
                const ids = new Set(prev.map(s => s.id))
                return [...prev, ...newSites.filter(s => !ids.has(s.id))]
              })
            }
          }).catch((err) => console.error('Failed to prepare suggestions:', err))
        }
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
        setMessages(prev => prev.filter(m => m.id !== assistantId))
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }, [input, adminKey, messages, contextType, contextId, contextYear, onHighlightSites, clearAuth, conversationId])

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

  const examples = EXAMPLE_QUESTIONS[contextType] || EXAMPLE_QUESTIONS.global
  const isPage = mode === 'page'

  const header = isPage ? (
    <PageHeader
      speechBubble="I can search 750K+ sites, find news, and answer archaeology questions!"
      onAvatarClick={() => setShowDossier(true)}
      currentPage="lyra"
      rightSection={
        <div className="lyra-chat-header-actions">
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
          <button className={`lyra-chat-icon-btn${searchOpen ? ' active' : ''}`} onClick={() => { setSearchOpen(!searchOpen); if (searchOpen) { setSearchQuery(''); setSearchResults([]) } }} title="Search sites">
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
          <div className="lyra-chat-header-name">Lyra Wiskerbyte</div>
          {messages.length === 0 ? (
            <div className="lyra-chat-speech-bubble">
              I can search 750K+ sites, find news, and answer archaeology questions!
            </div>
          ) : (
            <div className="lyra-chat-header-status">Archaeological Agent</div>
          )}
        </div>
      </div>
      <div className="lyra-chat-header-right">
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
        <button className={`lyra-chat-icon-btn${searchOpen ? ' active' : ''}`} onClick={() => { setSearchOpen(!searchOpen); if (searchOpen) { setSearchQuery(''); setSearchResults([]) } }} title="Search sites">
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
    <div className={`lyra-chat-modal${hasNews ? ' has-news' : ''}`}>
      {header}
      {historyPanel}

        {/* Auth gate or chat content */}
        {!isAuthenticated ? (
          <div className="lyra-chat-messages">
            <LyraAuthGate onAuthenticated={handleAuthenticated} />
          </div>
        ) : (
          <>
            {/* Body: chat + sidebar */}
            <div className="lyra-chat-body">
              {/* Left: chat messages */}
              <div className="lyra-chat-main">
                <div className="lyra-chat-messages">
                  {messages.length === 0 ? (
                    <div className="lyra-chat-welcome">
                      <img src="/lyra.gif" alt="Lyra" className="lyra-chat-welcome-avatar" />
                      <div className="lyra-chat-welcome-text">
                        {contextType === 'global'
                          ? 'Ask me anything about archaeological sites, empires, or recent discoveries.'
                          : contextType === 'site'
                            ? 'Ask me about this site — its history, nearby sites, or recent news.'
                            : contextType === 'empire'
                              ? 'Ask me about this empire — warfare, economy, social structure, or rivals.'
                              : 'Ask me about this discovery — significance, location, or related findings.'}
                      </div>
                      <div className="lyra-chat-examples">
                        {examples.map((q, i) => (
                          <button
                            key={i}
                            className="lyra-chat-example-btn"
                            onClick={() => handleExampleClick(q)}
                            disabled={isStreaming}
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    messages.map(msg => (
                      <div key={msg.id}>
                        {/* Thinking bubble — separate from answer */}
                        {msg.role === 'assistant' && msg.statusLines && msg.statusLines.length > 0 && (
                          <div className="lyra-chat-msg lyra-chat-msg-assistant">
                            <img src="/lyra.gif" alt="Lyra" className="lyra-chat-msg-avatar" />
                            <div className="lyra-chat-thinking-bubble">
                              {msg.statusLines.map((s, i) => (
                                <p key={i}>{s}</p>
                              ))}
                            </div>
                          </div>
                        )}
                        {/* Typing dots — waiting for first token */}
                        {msg.role === 'assistant' && msg.isStreaming && !msg.content && (
                          <div className="lyra-chat-msg lyra-chat-msg-assistant">
                            <img src="/lyra.gif" alt="Lyra" className="lyra-chat-msg-avatar" />
                            <div className="lyra-chat-typing-dots">
                              <span /><span /><span />
                            </div>
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
                                <TypewriterMessage
                                  content={msg.content}
                                  isStreaming={!!msg.isStreaming}
                                  sidebarSites={sidebarSites}
                                  mdComponents={mdComponents}
                                />
                              ) : (
                                <div className="lyra-chat-msg-text">
                                  {msg.content}
                                </div>
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
                              {msg.role === 'assistant' && !msg.isStreaming && msg.confidence != null && (
                                <div className="lyra-chat-msg-footer">
                                  <ConfidenceBadge value={msg.confidence} />
                                  {msg.tokens && (msg.tokens.input > 0 || msg.tokens.output > 0 || (msg.tokens.voyage ?? 0) > 0) && (
                                    <span className="lyra-chat-tokens">
                                      Haiku: {msg.tokens.input + msg.tokens.output}
                                      {(msg.tokens.voyage ?? 0) > 0 && ` · Voyage: ${msg.tokens.voyage}`}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </div>

              {/* Right: news column (full height) */}
              {hasNews && (
                <div className="lyra-chat-news-column lyra-chat-news-panel">
                  <div className="lyra-chat-sidebar-header">
                    News ({sortedNews.length})
                  </div>
                  <div className="lyra-chat-news-scroll">
                    {sortedNews.map((news, i) => (
                      <NewsCard
                        key={`${news.video_id}-${i}`}
                        size="sm"
                        {...newsHighlightToCardProps(news)}
                        onSiteLoaded={setSelectedSite}
                      />
                    ))}
                  </div>
                </div>
              )}

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
                              setSelectedSite(apiDetailToSiteData(detail))
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
            </div>

            {/* Mobile collapsible panels (page mode only, hidden on desktop via CSS) */}
            {isPage && hasNews && (
              <div className="lyra-mobile-panels">
                {hasNews && (
                  <div className={`lyra-mobile-panel${mobilePanelOpen === 'news' ? ' open' : ''}`}>
                    <button
                      className="lyra-mobile-panel-header"
                      onClick={() => setMobilePanelOpen(mobilePanelOpen === 'news' ? null : 'news')}
                    >
                      <span>News ({sortedNews.length})</span>
                      <svg className="lyra-mobile-panel-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                    {mobilePanelOpen === 'news' && (
                      <div className="lyra-mobile-panel-content">
                        {sortedNews.map((news, i) => (
                          <NewsCard
                            key={`${news.video_id}-${i}`}
                            size="sm"
                            {...newsHighlightToCardProps(news)}
                            onSiteLoaded={setSelectedSite}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="lyra-chat-error">
                {error}
                <button onClick={() => setError(null)}>Dismiss</button>
              </div>
            )}

            {/* Input area */}
            <div className="lyra-chat-input-area">
              <div className="lyra-chat-input-row">
                <textarea
                  ref={inputRef}
                  className="lyra-chat-input"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask Lyra..."
                  disabled={isStreaming}
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
        {selectedSite && (
          <SitePopupOverlay site={selectedSite} onClose={() => setSelectedSite(null)} />
        )}
        {dossierModal}
      </div>
    )
  }

  return createPortal(
    <div className="lyra-chat-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      {modalContent}
      {selectedSite && (
        <SitePopupOverlay site={selectedSite} onClose={() => setSelectedSite(null)} />
      )}
      {dossierModal}
    </div>,
    document.body
  )
}
