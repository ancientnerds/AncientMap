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
import { config } from '../config'
import type { LyraContextType, LyraMessage, SiteHighlight, NewsHighlight, ConversationSummary } from '../types/ai'
import { getCategoryColor, getPeriodColor } from '../constants/colors'
import { enrichLyraContent } from '../utils/lyraContentEnricher'
import { formatRelativeDate } from '../utils/formatters'
import NewsCard, { newsHighlightToCardProps } from './news/NewsCard'
import SiteResultItem from './SiteResultItem'
import { SitePopupOverlay } from './SitePopupOverlay'
import LyraAuthGate from './LyraAuthGate'
import { apiDetailToSiteData } from '../utils/siteApi'
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

interface ExamplePrompt {
  text: string
  level?: 'EASY' | 'MEDIUM' | 'HARD' | 'NEWS'
}

const EXAMPLE_QUESTIONS: Record<LyraContextType, ExamplePrompt[]> = {
  global: [
    { text: 'Tell me about Gobekli Tepe', level: 'EASY' },
    { text: 'Show me pyramids in Egypt', level: 'MEDIUM' },
    { text: 'What megalithic sites are in France?', level: 'MEDIUM' },
    { text: 'Ancient temples older than the Egyptian pyramids', level: 'HARD' },
    { text: 'Cave paintings and rock art in Europe', level: 'HARD' },
    { text: 'Recent discoveries about Karahantepe', level: 'NEWS' },
  ],
  site: [
    { text: 'Tell me more about this site' },
    { text: 'What other sites are nearby?' },
    { text: 'What period does this belong to?' },
    { text: 'Any recent news about this site?' },
  ],
  empire: [
    { text: 'What weapons did this empire use?' },
    { text: 'How large was their territory?' },
    { text: 'Who were their main rivals?' },
    { text: 'What caused their decline?' },
  ],
  news: [
    { text: 'Summarize this discovery' },
    { text: 'Where exactly was this found?' },
    { text: 'How significant is this finding?' },
    { text: 'Are there similar discoveries?' },
  ],
}

const LEVEL_LABELS: Record<string, string> = {
  EASY: 'Easy',
  MEDIUM: 'Medium',
  HARD: 'Hard',
  NEWS: 'News',
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

  // Auth state — hydrate from sessionStorage
  const [adminKey, setAdminKey] = useState<string | null>(() =>
    sessionStorage.getItem('lyra_admin_key')
  )
  const isAuthenticated = !!adminKey

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Abort in-flight SSE stream on unmount
  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  // Sort news by relevance (highest first)
  const sortedNews = useMemo(
    () => [...sidebarNews].sort((a, b) => (b.relevance ?? 0) - (a.relevance ?? 0)),
    [sidebarNews],
  )

  const hasSiteSidebar = sidebarSites.length > 0
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
                if (onFlyToSite) {
                  onHighlightSites?.([siteId])
                  if (!isNaN(lon) && !isNaN(lat)) onFlyToSite([lon, lat])
                }
                const res = await fetch(`${config.api.baseUrl}/sites/${siteId}`)
                if (res.ok) {
                  const detail = await res.json()
                  setSelectedSite(apiDetailToSiteData(detail))
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
                  navigator.clipboard.writeText(text)
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
                navigator.clipboard.writeText(`${lat}, ${lon}`)
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

  // Auto-scroll: instant during streaming (tokens fire rapidly), smooth otherwise
  const lastMsg = messages[messages.length - 1]
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: isStreaming ? 'instant' : 'smooth' })
  }, [messages.length, isStreaming, lastMsg?.content.length])

  // Focus input when opening (if authenticated)
  useEffect(() => {
    if (isOpen && isAuthenticated) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen, isAuthenticated])

  // Close on Escape (modal mode) / stop streaming (page mode)
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isStreaming) {
          abortRef.current?.abort()
        } else if (mode === 'modal') {
          onClose()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, isStreaming, onClose, mode])

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
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: m.content + data.content }
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
    <header className="lyra-chat-page-header">
      <a href="/globe.html" className="news-page-brand">
        <img src="/an-logo.svg" alt="" className="news-page-logo" />
        <span className="news-page-brand-text">ANCIENT NERDS</span>
      </a>
      <div className="news-page-divider" />
      <img
        src="/lyra.png"
        alt="Lyra"
        className="news-page-avatar lyra-avatar-clickable"
        onClick={() => setShowDossier(true)}
      />
      <span className="lyra-chat-page-label">Lyra</span>
      {messages.length === 0 && (
        <div className="lyra-chat-speech-bubble">
          I can search 800K+ sites, find news, and answer archaeology questions!
        </div>
      )}
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
        {isStreaming && (
          <button className="lyra-chat-stop-btn" onClick={() => abortRef.current?.abort()}>
            Stop
          </button>
        )}
      </div>
    </header>
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
              I can search 800K+ sites, find news, and answer archaeology questions!
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
    <div className={`lyra-chat-modal${hasSiteSidebar ? ' has-sidebar' : ''}${hasNews ? ' has-news' : ''}`}>
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
                            onClick={() => handleExampleClick(q.text)}
                            disabled={isStreaming}
                          >
                            {q.level && (
                              <span className={`lyra-example-level lyra-example-level-${q.level.toLowerCase()}`}>
                                {LEVEL_LABELS[q.level]}
                              </span>
                            )}
                            {q.text}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    messages.map(msg => (
                      <div key={msg.id} className={`lyra-chat-msg lyra-chat-msg-${msg.role}`}>
                        {msg.role === 'assistant' && (
                          <img src="/lyra.gif" alt="Lyra" className="lyra-chat-msg-avatar" />
                        )}
                        <div className="lyra-chat-msg-content">
                          {msg.role === 'assistant' && msg.statusLines && msg.statusLines.length > 0 && (
                            <div className="lyra-chat-status-lines">
                              {msg.statusLines.map((s, i) => (
                                <p key={i}>{s}</p>
                              ))}
                            </div>
                          )}
                          <div className="lyra-chat-msg-text">
                            {msg.role === 'assistant' ? (
                              msg.isStreaming ? (
                                msg.content
                              ) : (
                                <ReactMarkdown components={mdComponents}>
                                  {enrichLyraContent(msg.content, sidebarSites)}
                                </ReactMarkdown>
                              )
                            ) : (
                              msg.content
                            )}
                          </div>
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
                    ))
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </div>

              {/* Middle: sidebar with sites */}
              {hasSiteSidebar && (
                <div className="lyra-chat-sidebar">
                  <div className="lyra-chat-sidebar-panel">
                    <div className="lyra-chat-sidebar-header">
                      Sites ({sidebarSites.length})
                    </div>
                    <div className="lyra-chat-sidebar-list">
                      {sidebarSites.map((site, i) => (
                        <SiteResultItem
                          key={site.id || i}
                          id={site.id}
                          title={site.name}
                          category={site.site_type}
                          categoryColor={site.site_type ? getCategoryColor(site.site_type) : undefined}
                          location={site.country}
                          period={site.period_name}
                          periodColor={site.period_name ? getPeriodColor(site.period_name) : undefined}
                          thumbnailUrl={site.thumbnail_url}
                          showInfoBtn={false}
                          onMainClick={async () => {
                            if (onFlyToSite) {
                              onHighlightSites?.([site.id])
                              onFlyToSite([site.lon, site.lat])
                            } else {
                              const res = await fetch(`${config.api.baseUrl}/sites/${site.id}`)
                              if (res.ok) {
                                const detail = await res.json()
                                setSelectedSite(apiDetailToSiteData(detail))
                              }
                            }
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}

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
            </div>

            {/* Mobile collapsible panels (page mode only, hidden on desktop via CSS) */}
            {isPage && (hasSiteSidebar || hasNews) && (
              <div className="lyra-mobile-panels">
                {hasSiteSidebar && (
                  <div className={`lyra-mobile-panel${mobilePanelOpen === 'sites' ? ' open' : ''}`}>
                    <button
                      className="lyra-mobile-panel-header"
                      onClick={() => setMobilePanelOpen(mobilePanelOpen === 'sites' ? null : 'sites')}
                    >
                      <span>Sites ({sidebarSites.length})</span>
                      <svg className="lyra-mobile-panel-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                    {mobilePanelOpen === 'sites' && (
                      <div className="lyra-mobile-panel-content">
                        {sidebarSites.map((site, i) => (
                          <SiteResultItem
                            key={site.id || i}
                            id={site.id}
                            title={site.name}
                            category={site.site_type}
                            categoryColor={site.site_type ? getCategoryColor(site.site_type) : undefined}
                            location={site.country}
                            period={site.period_name}
                            periodColor={site.period_name ? getPeriodColor(site.period_name) : undefined}
                            thumbnailUrl={site.thumbnail_url}
                            showInfoBtn={false}
                            onMainClick={async () => {
                              const res = await fetch(`${config.api.baseUrl}/sites/${site.id}`)
                              if (res.ok) {
                                const detail = await res.json()
                                setSelectedSite(apiDetailToSiteData(detail))
                              }
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}
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
