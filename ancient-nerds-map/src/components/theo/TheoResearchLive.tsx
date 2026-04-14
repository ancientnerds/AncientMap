/**
 * TheoResearchLive — Full-screen overlay for live research streaming.
 * Connects to SSE stream and renders markdown in real-time with throttled updates.
 * Features NERV-style progress bar, heartbeat LEDs, and pipeline trace with LED indicators.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { config } from '../../config'
import type { PipelineEvent, PipelineNodeInstance } from '../../types/pipeline'
import { applyPipelineEvent, PIPELINE_STAGES } from '../../types/pipeline'
import { formatDurationMs } from '../../utils/formatters'
import { NervLoadingBar } from '../NervLoadingBar'

// ---------------------------------------------------------------------------
// Theo pipeline progress — weighted stages
// ---------------------------------------------------------------------------

const THEO_STAGE_WEIGHTS: Record<string, number> = {
  question_analysis: 5,
  web_search: 15,
  source_audit: 5,
  specialist_analysis: 30,
  synthesis: 10,
  debate: 10,
  moderator: 5,
  paper_assembly: 10,
  quality_judge: 5,
  image_generation: 5,
}

const THEO_STAGE_ORDER = Object.keys(THEO_STAGE_WEIGHTS)

function computeTheoProgress(nodes: PipelineNodeInstance[]) {
  let progress = 0
  let activeLabel = ''
  let doneCount = 0
  const totalCount = THEO_STAGE_ORDER.length

  for (const stageId of THEO_STAGE_ORDER) {
    const weight = THEO_STAGE_WEIGHTS[stageId]
    const instances = nodes.filter(n => n.stageId === stageId)

    if (stageId === 'specialist_analysis' && instances.length > 0) {
      // Repeatable — proportional progress
      const doneInstances = instances.filter(n => n.status === 'done' || n.status === 'skip')
      const activeInstances = instances.filter(n => n.status === 'active')
      const total = Math.max(instances.length, 1)
      const completed = doneInstances.length + activeInstances.length * 0.5
      progress += weight * (completed / total)
      if (doneInstances.length === instances.length && instances.length > 0) {
        doneCount++
      } else if (activeInstances.length > 0) {
        const def = PIPELINE_STAGES.find(s => s.id === stageId)
        activeLabel = def?.label?.toUpperCase() || stageId.replace(/_/g, ' ').toUpperCase()
      }
    } else if (instances.length > 0) {
      const node = instances[0]
      if (node.status === 'done' || node.status === 'skip') {
        progress += weight
        doneCount++
      } else if (node.status === 'active') {
        progress += weight * 0.5
        const def = PIPELINE_STAGES.find(s => s.id === stageId)
        activeLabel = def?.label?.toUpperCase() || stageId.replace(/_/g, ' ').toUpperCase()
      }
    }
  }

  return { progress: Math.min(Math.round(progress), 100), activeLabel, doneCount, totalCount }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface TheoResearchLiveProps {
  requestId: string
  question: string
  startedAt?: string
  onClose: () => void
}

export default function TheoResearchLive({ requestId, question, startedAt, onClose }: TheoResearchLiveProps) {
  const [nodes, setNodes] = useState<PipelineNodeInstance[]>([])
  const [displayText, setDisplayText] = useState('')
  const [displayThinking, setDisplayThinking] = useState('')
  const [statusMsg, setStatusMsg] = useState('')
  const [elapsedMs, setElapsedMs] = useState(0)
  const [done, setDone] = useState(false)
  const [showThinking, setShowThinking] = useState(true)
  const [showTrace, setShowTrace] = useState(true)
  const [hasError, setHasError] = useState(false)
  const [llmCalls, setLlmCalls] = useState(0)
  const [sourcesFound, setSourcesFound] = useState(0)
  const [specialistInfo, setSpecialistInfo] = useState('')
  const [debateRound, setDebateRound] = useState('')
  const [qualityFlash, setQualityFlash] = useState<{ score: number; badge: string } | null>(null)
  const [subtaskProgress, setSubtaskProgress] = useState<{ done: number; total: number }>({ done: 0, total: 1 })

  // V2 angle tracking
  const [angles, setAngles] = useState<Record<string, { topic: string; status: string; claims: number; sources: number; round: number; saturated: boolean }>>({})

  const reportTextRef = useRef('')
  const thinkingRef = useRef('')
  const bodyRef = useRef<HTMLDivElement>(null)

  // Elapsed timer — uses the actual request creation time so it persists across open/close
  const startIso = startedAt && !startedAt.endsWith('Z') ? startedAt + 'Z' : startedAt
  const startEpoch = startIso ? new Date(startIso).getTime() : Date.now()
  useEffect(() => {
    if (done) return
    const iv = setInterval(() => {
      setElapsedMs(Date.now() - startEpoch)
    }, 500)
    return () => clearInterval(iv)
  }, [done, startEpoch])

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

  // Escape key to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

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

        // Extract enriched metadata from pipeline events
        const meta = data.meta as Record<string, unknown> | undefined
        if (meta) {
          if (typeof meta.llm_calls === 'number') setLlmCalls(meta.llm_calls)
          if (data.stage === 'web_search' && data.status === 'done' && typeof meta.sources_found === 'number') {
            setSourcesFound(meta.sources_found)
          }
          if (data.stage === 'quality_judge' && data.status === 'done' && typeof meta.score === 'number') {
            setQualityFlash({ score: meta.score as number, badge: (meta.badge as string) || '' })
            setTimeout(() => setQualityFlash(null), 5000)
          }
        }

        // Subtask LED tracking — reset on stage start, fill on stage done
        if (data.status === 'start') {
          const subtaskTotal = (meta?.subtask_total as number) || 1
          setSubtaskProgress({ done: 0, total: subtaskTotal })
        } else if (data.status === 'done' || data.status === 'skip') {
          setSubtaskProgress(prev => ({ ...prev, done: prev.total }))
        }

        // V2 angle tracking — extract from stage names like search_XXXX, audit_XXXX, specialist_XXXX
        const stage = data.stage as string
        if (meta?.angle && typeof meta.angle === 'string') {
          const angleId = stage.includes('_') ? stage.split('_').slice(1).join('_') : ''
          if (angleId) {
            setAngles(prev => {
              const existing = prev[angleId] || { topic: meta.angle as string, status: 'queued', claims: 0, sources: 0, round: 0, saturated: false }
              const updated = { ...existing, topic: meta.angle as string }

              if (stage.startsWith('search_') && data.status === 'done') {
                updated.status = 'searched'
                updated.sources = (meta.total_sources as number) || existing.sources
                updated.round = (meta.round as number) || existing.round
              } else if (stage.startsWith('audit_') && data.status === 'start') {
                updated.status = 'auditing'
              } else if (stage.startsWith('audit_') && data.status === 'done') {
                updated.status = 'audited'
              } else if (stage.startsWith('specialist_') && data.status === 'start') {
                updated.status = 'analyzing'
              } else if (stage.startsWith('specialist_') && data.status === 'done') {
                updated.status = 'analyzed'
                updated.claims = (meta.total_claims as number) || existing.claims
              }

              return { ...prev, [angleId]: updated }
            })
          }
        }

        // Detect saturation from status messages
        if (stage === 'synthesis' && data.status === 'start') {
          // All angles saturated — mark them
          setAngles(prev => {
            const next = { ...prev }
            for (const id of Object.keys(next)) {
              next[id] = { ...next[id], saturated: true, status: 'saturated' }
            }
            return next
          })
        }
        break
      }
      case 'token':
        reportTextRef.current += (data.content as string || '')
        break
      case 'thinking':
        thinkingRef.current += (data.content as string || '')
        break
      case 'status': {
        setStatusMsg(data.content as string || '')
        // Specialist progress
        if (data.specialist_name) {
          setSpecialistInfo(`${data.specialist_name} (${data.specialist_index}/${data.specialist_total})`)
        }
        // Debate round
        if (typeof data.round === 'number') {
          setDebateRound(`ROUND ${data.round}/${data.total_rounds}`)
        }
        // Subtask progress from status events
        if (typeof data.subtask_done === 'number' && typeof data.subtask_total === 'number') {
          setSubtaskProgress({ done: data.subtask_done as number, total: data.subtask_total as number })
        }
        break
      }
      case 'sites':
        break
      case 'done':
        // Final sync to ensure complete text
        setDisplayText(reportTextRef.current)
        setDisplayThinking(thinkingRef.current)
        setDone(true)
        break
      case 'error':
      case 'timeout':
        setDisplayText(reportTextRef.current)
        setDisplayThinking(thinkingRef.current)
        setHasError(true)
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

  // Progress computation
  const { progress, activeLabel, doneCount, totalCount } = useMemo(
    () => computeTheoProgress(nodes), [nodes]
  )

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
                <span className="theo-heartbeat-leds">
                  {Array.from({ length: 5 }, (_, i) => (
                    <span
                      key={i}
                      className={`theo-hb-led ${
                        done && !hasError ? 'theo-hb-led--done' :
                        hasError ? 'theo-hb-led--dead' :
                        'theo-hb-led--alive'
                      }`}
                      style={{ animationDelay: `${i * 0.3}s` }}
                    />
                  ))}
                </span>
                {formatDurationMs(elapsedMs)}
              </span>
              {llmCalls > 0 && (
                <span className="theo-live-counter theo-live-counter--nerv">{llmCalls} LLM calls</span>
              )}
              {sourcesFound > 0 && (
                <span className="theo-live-counter theo-live-counter--nerv">{sourcesFound} sources</span>
              )}
              {activeNode && !done && (
                <span className="theo-live-stage-readout">
                  {activeNode.meta?.tool as string || activeNode.stageId.replace(/_/g, ' ').toUpperCase()}
                </span>
              )}
            </div>
          </div>
          <button className="theo-live-close" onClick={onClose} aria-label="Close live view">
            ✕
          </button>
        </div>

        {/* NERV Progress Bar */}
        <div className="theo-live-progress">
          {done ? (
            <NervLoadingBar label="COMPLETE" sublabel="RESEARCH FINISHED" progress={100} counter={`${doneNodes.length} stages`} ledsDone={totalCount} ledsTotal={totalCount} />
          ) : nodes.length > 0 ? (
            <NervLoadingBar label="RESEARCH" sublabel={specialistInfo.toUpperCase() || debateRound || activeLabel || 'PROCESSING'} progress={progress} counter={`${doneCount} / ${totalCount}`} ledsDone={subtaskProgress.done} ledsTotal={subtaskProgress.total} />
          ) : (
            <NervLoadingBar label="CONNECTING" sublabel="AWAITING PIPELINE" />
          )}
        </div>

        {/* V2 Angle Progress Table */}
        {Object.keys(angles).length > 0 && (
          <div className="theo-angles-table">
            {Object.entries(angles).map(([id, angle]) => (
              <div key={id} className={`theo-angle-row theo-angle-row--${angle.saturated ? 'saturated' : angle.status}`}>
                <span className={`theo-angle-led ${angle.saturated ? 'theo-angle-led--done' : angle.status === 'analyzing' || angle.status === 'auditing' ? 'theo-angle-led--active' : angle.claims > 0 ? 'theo-angle-led--has-claims' : ''}`} />
                <span className="theo-angle-topic">{angle.topic}</span>
                <span className="theo-angle-stats">
                  {angle.claims > 0 && <span>{angle.claims} claims</span>}
                  {angle.round > 0 && <span>R{angle.round}</span>}
                </span>
                {angle.saturated && <span className="theo-angle-check">&#10003;</span>}
              </div>
            ))}
          </div>
        )}

        {qualityFlash && (
          <div className="theo-quality-flash">
            Quality: {qualityFlash.score}/100 — {qualityFlash.badge}
          </div>
        )}

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

          {/* Pipeline trace — LED indicators */}
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
                  {nodes.map(node => (
                    <div key={node.instanceId} className="theo-trace-entry">
                      <span className="theo-trace-stage">
                        <span className={`theo-trace-led theo-trace-led--${node.status}`} />
                        {node.meta?.tool as string || node.stageId.replace(/_/g, ' ')}
                      </span>
                      <span className="theo-trace-dur">
                        {node.duration_ms != null ? formatDurationMs(node.duration_ms) : node.status === 'active' ? '...' : ''}
                      </span>
                      {node.status === 'error' && node.meta?.error ? (
                        <div className="theo-trace-error">{String(node.meta.error)}</div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
