/**
 * TheoResearchLive — Live progress view for a running research request.
 * Connects to SSE stream and shows pipeline stages, thinking, and streaming text.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { config } from '../../config'
import type { PipelineEvent, PipelineNodeInstance } from '../../types/pipeline'
import { applyPipelineEvent } from '../../types/pipeline'
import { formatDurationMs } from '../../utils/formatters'

interface TheoResearchLiveProps {
  requestId: string
}

export default function TheoResearchLive({ requestId }: TheoResearchLiveProps) {
  const [nodes, setNodes] = useState<PipelineNodeInstance[]>([])
  const [thinkingText, setThinkingText] = useState('')
  const [reportText, setReportText] = useState('')
  const [statusMsg, setStatusMsg] = useState('')
  const [sitesFound, setSitesFound] = useState(0)
  const [toolsUsed, setToolsUsed] = useState(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [done, setDone] = useState(false)
  const startRef = useRef(performance.now())
  const textRef = useRef<HTMLDivElement>(null)

  // Elapsed timer
  useEffect(() => {
    if (done) return
    const iv = setInterval(() => {
      setElapsedMs(performance.now() - startRef.current)
    }, 500)
    return () => clearInterval(iv)
  }, [done])

  // Auto-scroll report text
  useEffect(() => {
    if (textRef.current) {
      textRef.current.scrollTop = textRef.current.scrollHeight
    }
  }, [reportText, thinkingText])

  // SSE connection
  useEffect(() => {
    // EventSource doesn't support custom headers, so fall back to fetch-based SSE
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
            if (line.startsWith('event: ')) {
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

        // Track tool calls
        if (pEvent.stage === 'tool_call' && pEvent.status === 'done') {
          setToolsUsed(prev => prev + 1)
        }
        break
      }
      case 'token':
        setReportText(prev => prev + (data.content as string || ''))
        break
      case 'thinking':
        setThinkingText(prev => prev + (data.content as string || ''))
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
        setDone(true)
        break
    }
  }, [])

  // Count active/done stages for the progress indicator
  const doneNodes = nodes.filter(n => n.status === 'done')
  const activeNode = nodes.find(n => n.status === 'active')

  return (
    <div className="theo-live">
      {/* Counters bar */}
      <div className="theo-live-counters">
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

      {/* Pipeline stages */}
      {nodes.length > 0 && (
        <div className="theo-live-pipeline">
          {nodes.map(node => (
            <div key={node.instanceId} className={`theo-live-stage theo-live-st-${node.status}`}>
              <span className="theo-live-stage-icon">
                {node.status === 'active' ? '◉' :
                 node.status === 'done' ? '✓' :
                 node.status === 'error' ? '✗' : '○'}
              </span>
              <span className="theo-live-stage-name">
                {node.meta?.tool as string || node.stageId.replace(/_/g, ' ')}
              </span>
              {node.duration_ms != null && (
                <span className="theo-live-stage-dur">{node.duration_ms}ms</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Status message */}
      {statusMsg && !reportText && (
        <div className="theo-live-status">{statusMsg}</div>
      )}

      {/* Active stage indicator */}
      {activeNode && !reportText && !thinkingText && (
        <div className="theo-live-status">
          {activeNode.meta?.tool as string || activeNode.stageId.replace(/_/g, ' ')}...
        </div>
      )}

      {/* Thinking block */}
      {thinkingText && (
        <div className="theo-live-thinking">
          <div className="theo-live-thinking-label">Thinking</div>
          <div className="theo-live-thinking-text" ref={!reportText ? textRef : undefined}>
            {thinkingText}
          </div>
        </div>
      )}

      {/* Streaming report text */}
      {reportText && (
        <div className="theo-live-report" ref={textRef}>
          {reportText}
        </div>
      )}
    </div>
  )
}
