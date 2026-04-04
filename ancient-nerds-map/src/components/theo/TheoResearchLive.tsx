/**
 * TheoResearchLive — Full-screen overlay for live research streaming.
 * Connects to SSE stream and renders markdown in real-time with throttled updates.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { config } from '../../config'
import type { PipelineEvent, PipelineNodeInstance } from '../../types/pipeline'
import { applyPipelineEvent } from '../../types/pipeline'
import { formatDurationMs } from '../../utils/formatters'

interface TheoResearchLiveProps {
  requestId: string
  question: string
  onClose: () => void
}

export default function TheoResearchLive({ requestId, question, onClose }: TheoResearchLiveProps) {
  const [nodes, setNodes] = useState<PipelineNodeInstance[]>([])
  const [displayText, setDisplayText] = useState('')
  const [displayThinking, setDisplayThinking] = useState('')
  const [statusMsg, setStatusMsg] = useState('')
  const [sitesFound, setSitesFound] = useState(0)
  const [toolsUsed, setToolsUsed] = useState(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [done, setDone] = useState(false)
  const [showThinking, setShowThinking] = useState(true)
  const [showTrace, setShowTrace] = useState(false)

  const reportTextRef = useRef('')
  const thinkingRef = useRef('')
  const startRef = useRef(performance.now())
  const bodyRef = useRef<HTMLDivElement>(null)

  // Elapsed timer
  useEffect(() => {
    if (done) return
    const iv = setInterval(() => {
      setElapsedMs(performance.now() - startRef.current)
    }, 500)
    return () => clearInterval(iv)
  }, [done])

  // Throttled display sync — max 5 renders/sec
  useEffect(() => {
    if (done) return
    const iv = setInterval(() => {
      setDisplayText(reportTextRef.current)
      setDisplayThinking(thinkingRef.current)
    }, 200)
    return () => clearInterval(iv)
  }, [done])

  // Auto-scroll body (only if near bottom)
  useEffect(() => {
    const el = bodyRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100
    if (nearBottom) el.scrollTop = el.scrollHeight
  }, [displayText])

  // SSE connection
  useEffect(() => {
    const controller = new AbortController()
    const token = localStorage.getItem('an_auth_token')

    async function connectSSE() {
      try {
        const headers: Record<string, string> = { Accept: 'text/event-stream' }
        if (token) headers.Authorization = `Bearer ${token}`

        const resp = await fetch(
          `${config.api.baseUrl}/theo/research/${requestId}/stream`,
          { headers, signal: controller.signal }
        )

        if (!resp.ok || !resp.body) return

        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done: readerDone, value } = await reader.read()
          if (readerDone) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let currentEventType = ''
          for (const line of lines) {
            if (line === '') {
              currentEventType = ''
            } else if (line.startsWith('event: ')) {
              currentEventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                handleEvent(currentEventType || data.type, data)
              } catch {
                // ignore parse errors
              }
            }
          }
        }
      } catch {
        // abort or network error — ignore
      }
    }

    connectSSE()
    return () => controller.abort()
  }, [requestId])

  const handleEvent = useCallback((eventType: string, data: Record<string, unknown>) => {
    switch (eventType) {
      case 'pipeline': {
        const pEvent: PipelineEvent = {
          stage: data.stage as string,
          status: data.status as PipelineEvent['status'],
          duration_ms: (data.duration_ms as number) ?? null,
          meta: (data.meta as Record<string, unknown>) ?? null,
        }
        setNodes(prev => applyPipelineEvent(prev, pEvent))

        if (pEvent.stage === 'tool_call' && pEvent.status === 'done') {
          setToolsUsed(prev => prev + 1)
        }
        break
      }
      case 'token':
        reportTextRef.current += (data.content as string || '')
        break
      case 'thinking':
        thinkingRef.current += (data.content as string || '')
        break
      case 'status':
        setStatusMsg(data.content as string || '')
        break
      case 'sites': {
        const sites = data.sites as unknown[]
        if (sites) setSitesFound(prev => prev + sites.length)
        break
      }
      case 'done':
      case 'error':
      case 'timeout':
        // Final sync to ensure complete text
        setDisplayText(reportTextRef.current)
        setDisplayThinking(thinkingRef.current)
        setDone(true)
        break
    }
  }, [])

  const mdComponents = useMemo(() => ({
    a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
      if (href?.startsWith('site:')) {
        const siteId = href.slice(5)
        return (
          <a
            {...props}
            href={`/site.html?id=${siteId}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--accent-secondary)' }}
          >
            {children}
          </a>
        )
      }
      if (href?.startsWith('lyra-video:') || href?.startsWith('youtube:')) {
        const videoId = href.includes(':') ? href.split(':')[1] : href
        return (
          <a
            {...props}
            href={`https://youtube.com/watch?v=${videoId}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        )
      }
      return <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    },
  }), [])

  const urlTransform = useCallback((url: string) => {
    const colonIndex = url.indexOf(':')
    if (colonIndex === -1) return url
    const protocol = url.trim().slice(0, colonIndex)
    if (['http', 'https', 'mailto', 'lyra-video', 'lyra-site', 'lyra-coord', 'site', 'youtube'].includes(protocol.toLowerCase())) return url
    return ''
  }, [])

  const doneNodes = nodes.filter(n => n.status === 'done')
  const activeNode = nodes.find(n => n.status === 'active')

  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }, [onClose])

  return (
    <div className="theo-overlay" onClick={handleBackdropClick}>
      <div className="theo-overlay-inner" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="theo-live-header">
          <img src="/images/theo.png" alt="Theo" className="theo-avatar" style={{ width: 40, height: 40, flexShrink: 0 }} />
          <div className="theo-live-header-text">
            <div className="theo-live-question">{question}</div>
            <div className="theo-live-counters" style={{ marginTop: 6 }}>
              <span className="theo-live-counter">
                <span className="theo-live-dot" />
                {formatDurationMs(elapsedMs)}
              </span>
              {doneNodes.length > 0 && (
                <span className="theo-live-counter">{doneNodes.length} stages</span>
              )}
              {toolsUsed > 0 && (
                <span className="theo-live-counter">{toolsUsed} tools</span>
              )}
              {sitesFound > 0 && (
                <span className="theo-live-counter">{sitesFound} sites</span>
              )}
            </div>
          </div>
          <button className="theo-live-close" onClick={onClose} aria-label="Close live view">
            ✕
          </button>
        </div>

        {!done && (
          <div style={{ textAlign: 'center', padding: '4px 12px', fontSize: 11, color: 'var(--text-dimmed)', borderBottom: '1px solid var(--border-default)' }}>
            You can close this window — research continues in the background. Come back anytime.
          </div>
        )}

        {/* Body — scrollable markdown area */}
        <div className="theo-live-body theo-md-body" ref={bodyRef}>
          {displayText ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents} urlTransform={urlTransform}>
              {displayText}
            </ReactMarkdown>
          ) : statusMsg ? (
            <div className="theo-live-status">{statusMsg}</div>
          ) : activeNode ? (
            <div className="theo-live-status">
              {activeNode.meta?.tool as string || activeNode.stageId.replace(/_/g, ' ')}...
            </div>
          ) : (
            <div className="theo-live-status">Connecting to research stream...</div>
          )}
        </div>

        {/* Footer — collapsible thinking + pipeline trace */}
        <div className="theo-live-footer">
          {/* Thinking section */}
          {displayThinking && (
            <div className="theo-live-thinking" style={{ border: 'none', borderRadius: 0 }}>
              <div
                className="theo-live-thinking-label"
                onClick={() => setShowThinking(!showThinking)}
              >
                {showThinking ? '▾' : '▸'} Thinking
              </div>
              {showThinking && (
                <div className="theo-live-thinking-text">{displayThinking}</div>
              )}
            </div>
          )}

          {/* Pipeline trace */}
          {nodes.length > 0 && (
            <>
              <button
                className="theo-trace-toggle"
                onClick={() => setShowTrace(!showTrace)}
              >
                {showTrace ? '▾' : '▸'} Pipeline trace ({doneNodes.length} stages)
              </button>
              {showTrace && (
                <div className="theo-trace-body">
                  {(() => {
                    let cumulative = 0
                    return nodes.map(node => {
                      if (node.duration_ms != null) cumulative += node.duration_ms
                      return (
                        <div key={node.instanceId} className="theo-trace-entry">
                          <span className="theo-trace-stage">
                            {node.status === 'active' ? '◉ ' :
                             node.status === 'done' ? '✓ ' :
                             node.status === 'error' ? '✗ ' : '○ '}
                            {node.meta?.tool as string || node.stageId.replace(/_/g, ' ')}
                          </span>
                          <span className="theo-trace-dur">
                            {node.duration_ms != null ? formatDurationMs(cumulative) : node.status === 'active' ? '...' : ''}
                          </span>
                          {node.status === 'error' && node.meta?.error ? (
                            <div className="theo-trace-error">{String(node.meta.error)}</div>
                          ) : null}
                        </div>
                      )
                    })
                  })()}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
