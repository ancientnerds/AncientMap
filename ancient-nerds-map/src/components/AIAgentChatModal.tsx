import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { config } from '../config'
import type { AIMessage, SiteHighlight, ChatResponse, AIMode, AIModesResponse } from '../types/ai'

interface AIAgentChatModalProps {
  isOpen: boolean
  onClose: () => void
  sessionToken: string
  onHighlightSites: (siteIds: string[]) => void
  onFlyToSite: (coords: [number, number]) => void
  availableSources?: { id: string; name: string }[]
}

// Available data sources
const DEFAULT_SOURCES = [
  { id: 'ancient_nerds', name: 'Ancient Nerds Original' },
  { id: 'pleiades', name: 'Pleiades' },
  { id: 'wikidata', name: 'Wikidata' },
  { id: 'megalithic', name: 'Megalithic Portal' },
]

export default function AIAgentChatModal({
  isOpen,
  onClose,
  sessionToken,
  onHighlightSites,
  onFlyToSite,
  availableSources = DEFAULT_SOURCES
}: AIAgentChatModalProps) {
  // Separate message histories for each mode
  const [chatMessages, setChatMessages] = useState<AIMessage[]>([])
  const [researchMessages, setResearchMessages] = useState<AIMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [selectedSources, setSelectedSources] = useState<string[]>(['ancient_nerds'])
  const [showSourceSelector, setShowSourceSelector] = useState(false)
  const [mode, setMode] = useState<AIMode>('chat')
  const [modes, setModes] = useState<AIModesResponse | null>(null)
  const [, setCurrentModel] = useState<string>('')
  const [queuePosition, setQueuePosition] = useState<number | null>(null)

  // Get current mode's messages
  const messages = mode === 'chat' ? chatMessages : researchMessages
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Fetch available modes on mount
  useEffect(() => {
    fetch(`${config.api.baseUrl}/ai/modes`)
      .then(r => r.json())
      .then((data: AIModesResponse) => setModes(data))
      .catch(err => console.error('Failed to fetch AI modes:', err))
  }, [])

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen])

  // Auto-focus input when response completes (so user can keep typing)
  useEffect(() => {
    if (!isLoading && isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isLoading, isOpen])

  const handleSend = useCallback(async (messageText?: string) => {
    const text = messageText || input.trim()
    if (!text || isLoading) return

    // Capture the correct setter at call time to avoid closure issues
    const updateMessages = mode === 'chat' ? setChatMessages : setResearchMessages

    const userMessage: AIMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date()
    }

    updateMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    // Create placeholder assistant message for streaming
    const assistantId = crypto.randomUUID()
    updateMessages(prev => [...prev, {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true
    }])

    try {
      // Use SSE for streaming response with source filter
      const sourcesParam = selectedSources.join(',')
      const url = `${config.api.baseUrl}/ai/stream?session_token=${encodeURIComponent(sessionToken)}&message=${encodeURIComponent(text)}&sources=${encodeURIComponent(sourcesParam)}&mode=${mode}`
      const eventSource = new EventSource(url)

      let fullContent = ''
      let sites: SiteHighlight[] = []

      eventSource.addEventListener('token', (e) => {
        const data = JSON.parse(e.data)
        fullContent += data.content

        updateMessages(prev => prev.map(msg =>
          msg.id === assistantId
            ? { ...msg, content: fullContent }
            : msg
        ))
      })

      eventSource.addEventListener('sites', (e) => {
        const data = JSON.parse(e.data)
        sites = data.sites

        updateMessages(prev => prev.map(msg =>
          msg.id === assistantId
            ? { ...msg, sites }
            : msg
        ))
      })

      eventSource.addEventListener('done', (e) => {
        eventSource.close()
        setIsLoading(false)
        setQueuePosition(null)

        // Get model name from metadata
        try {
          const data = JSON.parse(e.data)
          if (data.metadata?.model) {
            setCurrentModel(data.metadata.model)
          }
        } catch {
          // Ignore parse errors
        }

        updateMessages(prev => prev.map(msg =>
          msg.id === assistantId
            ? { ...msg, isStreaming: false }
            : msg
        ))
      })

      eventSource.addEventListener('error', (e) => {
        eventSource.close()
        setIsLoading(false)
        setQueuePosition(null)

        // Try to parse error from event
        let errorMsg = 'Sorry, I encountered an error. Please try again.'
        try {
          const data = JSON.parse((e as MessageEvent).data)
          errorMsg = data.error || errorMsg
        } catch {
          // Use default error
        }

        updateMessages(prev => prev.map(msg =>
          msg.id === assistantId
            ? { ...msg, content: errorMsg, isStreaming: false }
            : msg
        ))
      })

      // Queue events
      eventSource.addEventListener('queued', (e) => {
        const data = JSON.parse(e.data)
        setQueuePosition(data.position)
      })

      eventSource.addEventListener('processing', () => {
        setQueuePosition(null)
      })

      eventSource.onerror = () => {
        eventSource.close()
        setIsLoading(false)
        setQueuePosition(null)

        // Check if we got any content
        if (!fullContent) {
          updateMessages(prev => prev.map(msg =>
            msg.id === assistantId
              ? {
                  ...msg,
                  content: 'Connection error. Please check if the AI service is running.',
                  isStreaming: false
                }
              : msg
          ))
        } else {
          // We have content, just mark as complete
          updateMessages(prev => prev.map(msg =>
            msg.id === assistantId
              ? { ...msg, isStreaming: false }
              : msg
          ))
        }
      }

    } catch (error) {
      setIsLoading(false)

      // Fallback to non-streaming endpoint
      try {
        const response = await fetch(`${config.api.baseUrl}/ai/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_token: sessionToken,
            message: text,
            include_sites: true
          })
        })

        if (!response.ok) {
          throw new Error('Request failed')
        }

        const data: ChatResponse = await response.json()

        updateMessages(prev => prev.map(msg =>
          msg.id === assistantId
            ? {
                ...msg,
                content: data.response,
                sites: data.sites,
                isStreaming: false
              }
            : msg
        ))
      } catch {
        updateMessages(prev => prev.map(msg =>
          msg.id === assistantId
            ? {
                ...msg,
                content: 'Sorry, I encountered an error. Please try again.',
                isStreaming: false
              }
            : msg
        ))
      }
    }
  }, [input, isLoading, sessionToken, selectedSources, mode, setChatMessages, setResearchMessages])

  const handleHighlight = useCallback((sites: SiteHighlight[]) => {
    if (!sites || sites.length === 0) return

    const siteIds = sites.map(s => s.id)
    onHighlightSites(siteIds)

    // Fly to first site
    if (sites[0]) {
      onFlyToSite([sites[0].lon, sites[0].lat])
    }
  }, [onHighlightSites, onFlyToSite])

  const handleExampleClick = useCallback((query: string) => {
    setInput(query)
    handleSend(query)
  }, [handleSend])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  const handleNewConversation = useCallback(() => {
    if (mode === 'chat') {
      setChatMessages([])
    } else {
      setResearchMessages([])
    }
    setCurrentModel('')
  }, [mode])

  // Handle close - disconnect from access control
  const handleClose = useCallback(() => {
    // Notify server we're leaving
    if (sessionToken) {
      fetch(`${config.api.baseUrl}/ai/disconnect?session_token=${encodeURIComponent(sessionToken)}`, {
        method: 'POST'
      }).catch(() => {
        // Ignore errors on disconnect
      })
    }
    onClose()
  }, [sessionToken, onClose])

  if (!isOpen) return null

  return createPortal(
    <div className="ai-chat-overlay" onClick={handleClose}>
      <div className="ai-chat-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="ai-chat-header">
          <div className="ai-chat-title">
            <img src="/lyra.png" alt="Lyra" className="lyra-header-icon" />
            <span>Lyra</span>
          </div>

          {/* Mode Toggle */}
          <div className="ai-mode-toggle">
            <button
              className={`mode-btn ${mode === 'chat' ? 'active' : ''}`}
              onClick={() => setMode('chat')}
              title="Quick answers and site lookups"
              disabled={messages.length > 0}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              Chat
            </button>
            <button
              className={`mode-btn ${mode === 'research' ? 'active' : ''}`}
              onClick={() => setMode('research')}
              title="In-depth analysis and detailed explanations"
              disabled={messages.length > 0}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"/>
                <path d="m21 21-4.35-4.35"/>
              </svg>
              Research
            </button>
          </div>

          <div className="ai-chat-header-actions">
            {/* Model Indicator - Always visible */}
            {modes && modes[mode] && (
              <div className="model-indicator" title={`Using model: ${modes[mode].model}`}>
                <span className="model-dot online" />
                <span className="model-name">{modes[mode].model}</span>
              </div>
            )}
            {/* New Conversation Button */}
            {messages.length > 0 && (
              <button
                className="new-conversation-btn"
                onClick={handleNewConversation}
                title="Start new conversation"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
                New
              </button>
            )}
            <button
              className={`source-toggle-btn ${showSourceSelector ? 'active' : ''}`}
              onClick={() => setShowSourceSelector(!showSourceSelector)}
              title="Select data sources"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
              <span>{selectedSources.length}</span>
            </button>
            <button className="popup-close" onClick={handleClose} title="Close">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>

        {/* Source Selector Dropdown */}
        {showSourceSelector && (
          <div className="source-selector">
            <div className="source-selector-title">Data Sources</div>
            {availableSources.map(source => (
              <label key={source.id} className="source-option">
                <input
                  type="checkbox"
                  checked={selectedSources.includes(source.id)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedSources(prev => [...prev, source.id])
                    } else {
                      // Ensure at least one source is selected
                      if (selectedSources.length > 1) {
                        setSelectedSources(prev => prev.filter(id => id !== source.id))
                      }
                    }
                  }}
                />
                <span>{source.name}</span>
                {source.id === 'ancient_nerds' && <span className="source-badge">Default</span>}
              </label>
            ))}
          </div>
        )}

        {/* Messages */}
        <div className="ai-chat-messages">
          {messages.length === 0 && (
            <div className="ai-chat-welcome">
              <div className="welcome-icon">
                <img src="/lyra.png" alt="Lyra" className="lyra-welcome-image" />
              </div>
              <h3>Hi, I'm Lyra!</h3>
              <p>I can help you explore 800,000+ archaeological sites.</p>
              {modes && modes[mode] && (
                <>
                  <p className="mode-description">
                    <strong>{modes[mode].display_name}:</strong> {modes[mode].description}
                  </p>
                  <p>Try asking:</p>
                  <div className="example-queries">
                    {modes[mode].examples.map((query, i) => (
                      <button
                        key={i}
                        className="example-query"
                        onClick={() => handleExampleClick(query)}
                      >
                        {query}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {messages.map(msg => (
            <div key={msg.id} className={`ai-chat-message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                  </svg>
                ) : (
                  <img src="/lyra.png" alt="Lyra" className="lyra-avatar" />
                )}
              </div>

              <div className="message-body">
                <div className="message-content">
                  {msg.content || (msg.isStreaming && <span className="cursor-blink">|</span>)}
                </div>

                {msg.sites && msg.sites.length > 0 && (
                  <div className="message-sites">
                    <div className="sites-header">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                        <circle cx="12" cy="10" r="3"/>
                      </svg>
                      <span>{msg.sites.length} site{msg.sites.length > 1 ? 's' : ''} found</span>
                    </div>
                    <button
                      className="highlight-sites-btn"
                      onClick={() => handleHighlight(msg.sites!)}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>
                      </svg>
                      Highlight on Map
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Queue waiting indicator */}
          {queuePosition !== null && queuePosition > 0 && (
            <div className="queue-waiting">
              <div className="queue-spinner" />
              <span>Lyra is busy...</span>
              <span className="queue-position">#{queuePosition} in line</span>
            </div>
          )}

          {/* Typing indicator - only show when processing (not queued) */}
          {isLoading && queuePosition === null && messages[messages.length - 1]?.role === 'assistant' && !messages[messages.length - 1]?.content && (
            <div className="ai-typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="ai-chat-input-container">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about ancient sites..."
            disabled={isLoading}
            className="ai-chat-input"
          />
          <button
            onClick={() => handleSend()}
            disabled={isLoading || !input.trim()}
            className="ai-chat-send"
            title="Send message"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}
