/**
 * LyraChatModal — Chat with Lyra Wiskerbyte.
 *
 * Features:
 * - Admin auth gate (Bearer key + Turnstile)
 * - Text input + image upload (drag & drop + file picker)
 * - SSE streaming with token-by-token display
 * - Conversation history (client-side)
 * - Context-aware: receives contextType, contextId, contextYear props
 * - Site highlighting on globe from tool results
 * - Confidence badge on responses
 * - Markdown rendering for assistant messages
 * - Three-column layout with sites & news sidebar
 * - Token usage display
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import { config } from '../config'
import type { LyraContextType, LyraMessage, SiteHighlight, NewsHighlight } from '../types/ai'
import { getCategoryColor, getPeriodColor } from '../constants/colors'
import { enrichLyraContent } from '../utils/lyraContentEnricher'
import { formatRelativeDate, formatDuration } from '../utils/formatters'
import { getSignificanceColor, getSignificanceLabel, getSignificanceCardStyle, getNewsCategoryLabel } from './news/significance'
import { SiteBadges, CountryFlag } from './metadata'
import SiteResultItem from './SiteResultItem'
import { SitePopupOverlay } from './SitePopupOverlay'
import LazyImage from './LazyImage'
import LyraAuthGate from './LyraAuthGate'
import { apiDetailToSiteData } from '../utils/siteApi'
import type { SiteData } from '../data/sites'
import './news/news-cards.css'

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
  const [pendingImages, setPendingImages] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sidebarSites, setSidebarSites] = useState<SiteHighlight[]>([])
  const [sidebarNews, setSidebarNews] = useState<NewsHighlight[]>([])
  const [selectedSite, setSelectedSite] = useState<SiteData | null>(null)
  const [mobilePanelOpen, setMobilePanelOpen] = useState<'sites' | 'news' | null>(null)

  // Auth state — hydrate from sessionStorage
  const [adminKey, setAdminKey] = useState<string | null>(() =>
    sessionStorage.getItem('lyra_admin_key')
  )
  const isAuthenticated = !!adminKey

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Derive unique video sources from news items
  const sidebarSources = sidebarNews.reduce<{ video_id: string; channel: string; video_title?: string }[]>((acc, n) => {
    if (n.video_id && !acc.some(s => s.video_id === n.video_id)) {
      acc.push({ video_id: n.video_id, channel: n.channel, video_title: n.video_title })
    }
    return acc
  }, [])

  // Sort news by relevance (highest first)
  const sortedNews = [...sidebarNews].sort((a, b) => (b.relevance ?? 0) - (a.relevance ?? 0))

  const hasSiteSidebar = sidebarSites.length > 0 || sidebarSources.length > 0
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
        return (
          <button
            className="lyra-inline-site"
            onClick={async () => {
              if (onFlyToSite) {
                onHighlightSites?.([siteId])
                if (!isNaN(lon) && !isNaN(lat)) onFlyToSite([lon, lat])
              } else {
                // Page mode: open SitePopupOverlay
                const res = await fetch(`${config.api.baseUrl}/sites/${siteId}`)
                if (res.ok) {
                  const detail = await res.json()
                  setSelectedSite(apiDetailToSiteData(detail))
                }
              }
            }}
          >
            {children}
          </button>
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

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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

  const handleImageUpload = useCallback((files: FileList | null) => {
    if (!files) return
    Array.from(files).forEach(file => {
      if (!file.type.startsWith('image/')) return
      if (file.size > 5 * 1024 * 1024) {
        setError('Image must be under 5MB')
        return
      }
      const reader = new FileReader()
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          setPendingImages(prev => [...prev, reader.result as string])
        }
      }
      reader.readAsDataURL(file)
    })
  }, [])

  // Drag & drop
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    handleImageUpload(e.dataTransfer.files)
  }, [handleImageUpload])

  const sendMessage = useCallback(async (text?: string) => {
    const messageText = text || input.trim()
    if (!messageText && pendingImages.length === 0) return
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
      images: pendingImages.length > 0 ? [...pendingImages] : undefined,
    }
    setMessages(prev => [...prev, userMsg])
    setPendingImages([])

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
      images: userMsg.images?.map(data => ({ data })),
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
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? { ...m, isStreaming: false, confidence: avgRelevance, tokens }
                    : m
                ))
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
  }, [input, adminKey, pendingImages, messages, contextType, contextId, contextYear, onHighlightSites, clearAuth])

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
      <a href="/" className="news-page-brand">
        <img src="/an-logo.svg" alt="" className="news-page-logo" />
        <span className="news-page-brand-text">ANCIENT NERDS</span>
      </a>
      <div className="news-page-divider" />
      <img src="/lyra.png" alt="Lyra" className="news-page-avatar" />
      <span className="lyra-chat-page-label">Lyra</span>
      {isStreaming && (
        <button className="lyra-chat-stop-btn" onClick={() => abortRef.current?.abort()}>
          Stop
        </button>
      )}
    </header>
  ) : (
    <div className="lyra-chat-header">
      <div className="lyra-chat-header-left">
        <img src="/lyra.gif" alt="Lyra" className="lyra-chat-avatar" />
        <div>
          <div className="lyra-chat-header-name">Lyra Wiskerbyte</div>
          <div className="lyra-chat-header-status">Archaeological Agent</div>
        </div>
      </div>
      <div className="lyra-chat-header-right">
        {isStreaming && (
          <button className="lyra-chat-stop-btn" onClick={() => abortRef.current?.abort()}>
            Stop
          </button>
        )}
        <button className="lyra-chat-close-btn" onClick={onClose}>
          <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
          </svg>
        </button>
      </div>
    </div>
  )

  const modalContent = (
    <div className={`lyra-chat-modal${hasSiteSidebar ? ' has-sidebar' : ''}${hasNews ? ' has-news' : ''}`}>
      {header}

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
                <div
                  className="lyra-chat-messages"
                  onDragOver={e => e.preventDefault()}
                  onDrop={handleDrop}
                >
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
                          {msg.images && msg.images.length > 0 && (
                            <div className="lyra-chat-msg-images">
                              {msg.images.map((img, i) => (
                                <img key={i} src={img} alt="Upload" className="lyra-chat-msg-image" />
                              ))}
                            </div>
                          )}
                          {msg.role === 'assistant' && msg.statusLines && msg.statusLines.length > 0 && (
                            <div className="lyra-chat-status-lines">
                              {msg.statusLines.map((s, i) => (
                                <p key={i}>{s}</p>
                              ))}
                            </div>
                          )}
                          <div className="lyra-chat-msg-text">
                            {msg.role === 'assistant' ? (
                              <>
                                <ReactMarkdown components={mdComponents}>
                                  {msg.isStreaming ? msg.content : enrichLyraContent(msg.content, sidebarSites)}
                                </ReactMarkdown>
                                {msg.isStreaming && <span className="lyra-chat-cursor" />}
                              </>
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

              {/* Middle: sidebar with sites & sources */}
              {hasSiteSidebar && (
                <div className="lyra-chat-sidebar">
                  {sidebarSites.length > 0 && (
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
                  )}
                  {sidebarSources.length > 0 && (
                    <div className="lyra-chat-sidebar-panel">
                      <div className="lyra-chat-sidebar-header">
                        Sources ({sidebarSources.length})
                      </div>
                      <div className="lyra-chat-sidebar-list">
                        {sidebarSources.map((src) => (
                          <a
                            key={src.video_id}
                            className="lyra-sidebar-source"
                            href={`https://youtu.be/${src.video_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <img
                              className="lyra-sidebar-source-thumb"
                              src={`https://img.youtube.com/vi/${src.video_id}/mqdefault.jpg`}
                              alt=""
                            />
                            <div className="lyra-sidebar-source-body">
                              <div className="lyra-sidebar-source-title">
                                {src.video_title || src.channel}
                              </div>
                              <div className="lyra-sidebar-source-channel">{src.channel}</div>
                            </div>
                          </a>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Right: news column (full height) */}
              {hasNews && (
                <div className="lyra-chat-news-column lyra-chat-news-panel">
                  <div className="lyra-chat-sidebar-header">
                    News ({sortedNews.length})
                  </div>
                  <div className="lyra-chat-news-scroll">
                    {sortedNews.map((news, i) => {
                      const deepLink = news.timestamp_seconds
                        ? `https://youtu.be/${news.video_id}?t=${news.timestamp_seconds}`
                        : `https://youtu.be/${news.video_id}`
                      const thumbSrc = news.screenshot_url
                        ? `${config.api.baseUrl}${news.screenshot_url.replace('/api', '')}`
                        : `https://img.youtube.com/vi/${news.video_id}/mqdefault.jpg`

                      return (
                        <div
                          key={`${news.video_id}-${i}`}
                          className={`news-feed-item${news.site_name ? ' has-site' : ''}`}
                          style={news.significance ? getSignificanceCardStyle(news.significance) : undefined}
                        >
                          {news.category && news.category !== 'general' && (
                            <span className="news-category-badge">{getNewsCategoryLabel(news.category)}</span>
                          )}
                          <div className="news-card-meta">
                            <span className="news-card-channel">{news.channel}</span>
                            {news.date && <span className="news-feed-date">{formatRelativeDate(news.date)}</span>}
                          </div>
                          {news.significance != null && news.significance >= 6 && (
                            <div className="news-significance-stamp" style={{ color: getSignificanceColor(news.significance) }}>
                              {getSignificanceLabel(news.significance)}
                            </div>
                          )}
                          <div className="news-card-post-text">{news.post_text || news.headline}</div>

                          {news.site_name && (
                            <div className="news-feed-site-block">
                              <div className="news-feed-site-row">
                                {news.site_country && <CountryFlag country={news.site_country} size="sm" showName />}
                                <span className="lyra-news-site-name">
                                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                                    <circle cx="12" cy="10" r="3"></circle>
                                  </svg>
                                  {news.site_name}
                                </span>
                              </div>
                              <SiteBadges category={news.site_type} period={news.site_period_name} periodStart={news.site_period_start} size="sm" />
                            </div>
                          )}

                          {thumbSrc && (
                            <a
                              className="news-card-thumb"
                              href={deepLink}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                            >
                              <LazyImage src={thumbSrc} alt="" />
                              <svg className="news-card-play" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                              </svg>
                              {news.timestamp_seconds != null && (
                                <span className="news-card-timestamp">&#9654; {formatDuration(news.timestamp_seconds / 60)}</span>
                              )}
                            </a>
                          )}
                        </div>
                      )
                    })}
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
                      <span>Sites ({sidebarSites.length}){sidebarSources.length > 0 ? ` · Sources (${sidebarSources.length})` : ''}</span>
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
                        {sidebarSources.map((src) => (
                          <a
                            key={src.video_id}
                            className="lyra-sidebar-source"
                            href={`https://youtu.be/${src.video_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <img
                              className="lyra-sidebar-source-thumb"
                              src={`https://img.youtube.com/vi/${src.video_id}/mqdefault.jpg`}
                              alt=""
                            />
                            <div className="lyra-sidebar-source-body">
                              <div className="lyra-sidebar-source-title">{src.video_title || src.channel}</div>
                              <div className="lyra-sidebar-source-channel">{src.channel}</div>
                            </div>
                          </a>
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
                        {sortedNews.map((news, i) => {
                          const deepLink = news.timestamp_seconds
                            ? `https://youtu.be/${news.video_id}?t=${news.timestamp_seconds}`
                            : `https://youtu.be/${news.video_id}`
                          return (
                            <div key={`${news.video_id}-${i}`} className="news-feed-item compact">
                              <div className="news-card-meta">
                                <span className="news-card-channel">{news.channel}</span>
                                {news.date && <span className="news-feed-date">{formatRelativeDate(news.date)}</span>}
                              </div>
                              <div className="news-card-post-text">{news.post_text || news.headline}</div>
                              {news.site_name && (
                                <div className="news-feed-site-block">
                                  <span className="lyra-news-site-name">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                                      <circle cx="12" cy="10" r="3"></circle>
                                    </svg>
                                    {news.site_name}
                                  </span>
                                </div>
                              )}
                              <a className="news-card-thumb" href={deepLink} target="_blank" rel="noopener noreferrer">
                                <LazyImage
                                  src={news.screenshot_url
                                    ? `${config.api.baseUrl}${news.screenshot_url.replace('/api', '')}`
                                    : `https://img.youtube.com/vi/${news.video_id}/mqdefault.jpg`}
                                  alt=""
                                />
                                <svg className="news-card-play" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                                  <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                                </svg>
                              </a>
                            </div>
                          )
                        })}
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

            {/* Image preview */}
            {pendingImages.length > 0 && (
              <div className="lyra-chat-image-preview">
                {pendingImages.map((img, i) => (
                  <div key={i} className="lyra-chat-image-preview-item">
                    <img src={img} alt="Preview" />
                    <button onClick={() => setPendingImages(prev => prev.filter((_, j) => j !== i))}>
                      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Input area */}
            <div className="lyra-chat-input-area">
              <div className="lyra-chat-input-row">
                <button
                  className="lyra-chat-attach-btn"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isStreaming}
                  title="Attach image"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
                  </svg>
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  style={{ display: 'none' }}
                  onChange={e => handleImageUpload(e.target.files)}
                />
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
                  disabled={isStreaming || (!input.trim() && pendingImages.length === 0)}
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

  if (isPage) {
    return (
      <div className="lyra-chat-page">
        {modalContent}
        {selectedSite && (
          <SitePopupOverlay site={selectedSite} onClose={() => setSelectedSite(null)} />
        )}
      </div>
    )
  }

  return createPortal(
    <div className="lyra-chat-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      {modalContent}
    </div>,
    document.body
  )
}
