/**
 * PipelinePanel — RAG Pipeline Flowchart Visualization.
 *
 * CRT-aesthetic flowchart showing all Lyra pipeline stages:
 * R (Retrieval) → A (Augmentation) → G (Generation)
 *
 * Features:
 * - Maximizable full-screen overlay
 * - Model info bar (model, tier, embedding, reranker)
 * - Flowchart boxes with status, timing, metadata
 * - Knowledge sources grid (PostgreSQL, Qdrant, Seshat)
 * - LLM rounds with inline tool calls
 * - Live elapsed timer for active stages
 * - Summary footer with totals
 */

import { useMemo, useRef, useEffect, useState } from 'react'
import type { PipelineTrace, PipelineNodeInstance, PipelineNodeStatus, ToolDef } from '../../types/pipeline'
import { TOOL_REGISTRY } from '../../types/pipeline'

interface PipelinePanelProps {
  trace: PipelineTrace | null
  isLive: boolean
  onClose: () => void
}

// ── Helpers ──

function statusIcon(status: PipelineNodeStatus): string {
  switch (status) {
    case 'done': return '\u2713'
    case 'error': return '\u2717'
    case 'skip': return '\u2013'
    case 'active': return '\u25b8'
    case 'idle': return '\u00b7'
    default: return '\u00b7'
  }
}

function statusClass(status: PipelineNodeStatus): string {
  return `lp-st-${status}`
}

function formatMs(ms: number | null): string {
  if (ms === null) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function activeElapsed(node: PipelineNodeInstance): string {
  if (node.status !== 'active' || !node.startedAt) return '...'
  const ms = Math.round(performance.now() - node.startedAt)
  return formatMs(ms)
}

function getTiming(node: PipelineNodeInstance | undefined): string {
  if (!node) return ''
  if (node.status === 'active') return activeElapsed(node)
  if (node.status === 'idle') return ''
  return formatMs(node.duration_ms)
}

// ── Tool view building ──

interface ToolCallInfo {
  name: string
  args: Record<string, unknown> | null
  resultLen: number | null
  resultPreview: string | null
  status: PipelineNodeStatus
  duration_ms: number | null
  error: string | null
}

interface RoundInfo {
  node: PipelineNodeInstance
  tools: ToolCallInfo[]
}

function buildRounds(nodes: PipelineNodeInstance[]): RoundInfo[] {
  const rounds = nodes.filter(n => n.stageId === 'llm_round')
  return rounds.map((round, ri) => {
    const roundIdx = nodes.indexOf(round)
    const nextRoundIdx = ri + 1 < rounds.length ? nodes.indexOf(rounds[ri + 1]) : nodes.length
    const tools: ToolCallInfo[] = []
    for (let i = roundIdx + 1; i < nextRoundIdx; i++) {
      const n = nodes[i]
      if (n.stageId === 'tool_call') {
        tools.push({
          name: String(n.meta?.tool ?? 'unknown'),
          args: (n.meta?.args as Record<string, unknown>) ?? null,
          resultLen: n.meta?.result_len != null ? Number(n.meta.result_len) : null,
          resultPreview: n.meta?.result_preview ? String(n.meta.result_preview) : null,
          status: n.status,
          duration_ms: n.duration_ms,
          error: n.meta?.error ? String(n.meta.error) : null,
        })
      }
    }
    return { node: round, tools }
  })
}

interface ToolSourceView {
  def: ToolDef
  status: PipelineNodeStatus
  callCount: number
}

function buildSourceViews(nodes: PipelineNodeInstance[]): ToolSourceView[] {
  return TOOL_REGISTRY.map(def => {
    const matching = nodes.filter(n => n.stageId === 'tool_call' && n.meta?.tool === def.name)
    const callCount = matching.length
    const status: PipelineNodeStatus = callCount === 0 ? 'idle'
      : matching.some(n => n.status === 'active') ? 'active'
      : matching.some(n => n.status === 'error') ? 'error'
      : matching.every(n => n.status === 'done') ? 'done'
      : 'idle'
    return { def, status, callCount }
  })
}

// ── Live elapsed timer hook ──

function useElapsedTimer(nodes: PipelineNodeInstance[], isLive: boolean) {
  const [, setTick] = useState(0)
  const hasActive = isLive && nodes.some(n => n.status === 'active')
  useEffect(() => {
    if (!hasActive) return
    const id = setInterval(() => setTick(t => t + 1), 200)
    return () => clearInterval(id)
  }, [hasActive])
}

// ── Sub-components ──

function SectionTag({ letter, label, status }: { letter: string; label: string; status: PipelineNodeStatus }) {
  return (
    <div className={`lp-rag-tag ${statusClass(status)}`}>
      <span className="lp-rag-letter">{letter}</span>
      <span className="lp-rag-label">{label}</span>
    </div>
  )
}

function FlowBox({ name, sublabel, status, timing, meta, error, children }: {
  name: string
  sublabel?: string
  status: PipelineNodeStatus
  timing: string
  meta?: string
  error?: string | null
  children?: React.ReactNode
}) {
  return (
    <div className={`lp-box ${statusClass(status)}`}>
      <div className="lp-box-header">
        <span className="lp-box-icon">{statusIcon(status)}</span>
        <span className="lp-box-name">{name}</span>
        {timing && <span className="lp-box-time">{timing}</span>}
      </div>
      {sublabel && <div className="lp-box-sub">{sublabel}</div>}
      {meta && <div className="lp-box-meta">{meta}</div>}
      {error && <div className="lp-box-error">{'\u2717'} {error}</div>}
      {children}
    </div>
  )
}

function FlowArrow() {
  return <div className="lp-flow-arrow">{'\u2502'}<br />{'\u25bc'}</div>
}

function FlowArrowH() {
  return <span className="lp-flow-arrow-h">{'\u2500\u25b6'}</span>
}

// ── Main component ──

export default function PipelinePanel({ trace, isLive, onClose }: PipelinePanelProps) {
  const [maximized, setMaximized] = useState(false)
  const nodes = trace?.nodes ?? []
  const bodyRef = useRef<HTMLDivElement>(null)

  useElapsedTimer(nodes, isLive)

  // Extract model info from pipeline_init node
  const initNode = nodes.find(n => n.stageId === 'pipeline_init')
  const modelInfo = initNode?.meta as {
    model?: string; tier?: string; backend?: string
    embedding?: string; reranker?: string; classification?: string
  } | null

  // Stage nodes
  const getNode = (id: string) => nodes.find(n => n.stageId === id)
  const autoRetrieve = getNode('auto_retrieve')
  const filterExtract = getNode('filter_extraction')
  const newsAugment = getNode('news_augmentation')
  const ctxAssembly = getNode('context_assembly')
  const preEmit = getNode('pre_stream_emit')
  const doneNode = getNode('done_credits')

  // Build round & tool data
  const rounds = useMemo(() => buildRounds(nodes), [nodes])
  const sourceViews = useMemo(() => buildSourceViews(nodes), [nodes])

  // Compute totals
  const totalMs = useMemo(() => {
    const durations = nodes.filter(n =>
      n.stageId !== 'tool_call' && n.stageId !== 'done_credits' && n.stageId !== 'pipeline_init' && n.duration_ms != null
    )
    if (durations.length === 0) return null
    return durations.reduce((sum, n) => sum + (n.duration_ms ?? 0), 0)
  }, [nodes])

  const totalTokens = doneNode?.meta?.total_tokens as number | undefined
  const totalToolCalls = rounds.reduce((sum, r) => sum + r.tools.length, 0)
  const totalResults = rounds.reduce((sum, r) =>
    sum + r.tools.reduce((ts, t) => ts + (t.resultLen ?? 0), 0), 0
  )
  const totalWebSearches = rounds.reduce((sum, r) =>
    sum + r.tools.filter(t => t.name === 'web_search').reduce((ws, t) => ws + (t.resultLen ?? 0), 0), 0
  )

  // Retrieval section overall status
  const retrievalStatus: PipelineNodeStatus =
    (autoRetrieve?.status === 'active' || filterExtract?.status === 'active') ? 'active'
    : (autoRetrieve?.status === 'error' || filterExtract?.status === 'error') ? 'error'
    : (autoRetrieve?.status === 'done' || filterExtract?.status === 'done') ? 'done'
    : (autoRetrieve?.status === 'skip' && filterExtract?.status === 'skip') ? 'skip'
    : 'idle'

  // Augmentation section overall status
  const augNodes = [newsAugment, ctxAssembly, preEmit].filter(Boolean) as PipelineNodeInstance[]
  const augStatus: PipelineNodeStatus =
    augNodes.some(n => n.status === 'active') ? 'active'
    : augNodes.some(n => n.status === 'error') ? 'error'
    : augNodes.length > 0 && augNodes.every(n => n.status === 'done' || n.status === 'skip') ? 'done'
    : augNodes.length > 0 ? 'active'
    : 'idle'

  // Generation section overall status
  const genStatus: PipelineNodeStatus =
    rounds.some(r => r.node.status === 'active') ? 'active'
    : rounds.some(r => r.node.status === 'error') ? 'error'
    : rounds.length > 0 && rounds.every(r => r.node.status === 'done') ? 'done'
    : rounds.length > 0 ? 'active' : 'idle'

  // Group sources by backend
  const pgSources = sourceViews.filter(s => s.def.backend === 'PostgreSQL')
  const qdSources = sourceViews.filter(s => s.def.backend === 'Qdrant')
  const sesSources = sourceViews.filter(s => s.def.backend === 'Seshat')
  const anthropicSources = sourceViews.filter(s => s.def.backend === 'Anthropic')

  // Auto-scroll
  useEffect(() => {
    if (isLive && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [isLive, nodes])

  // Esc to close maximized
  useEffect(() => {
    if (!maximized) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setMaximized(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [maximized])

  const backendLabel = modelInfo?.backend === 'local' ? 'LOCAL' : 'CLOUD'
  const tierLabel = modelInfo?.tier?.toUpperCase() ?? ''

  return (
    <div className={`lp-panel ${maximized ? 'lp-maximized' : ''}`}>

      {/* Header */}
      <div className="lp-header">
        <div className="lp-header-left">
          {'>'} RAG PIPELINE
          {isLive && (
            <span className="lp-live-badge">
              LIVE <span className="lp-live-dot" />
            </span>
          )}
        </div>
        <div className="lp-header-actions">
          <button className="lp-hdr-btn" onClick={() => setMaximized(!maximized)} title={maximized ? 'Minimize' : 'Maximize'}>
            {maximized ? '\u25a3' : '\u25a1'}
          </button>
          <button className="lp-hdr-btn" onClick={() => { if (maximized) setMaximized(false); else onClose() }} title="Close">
            {'\u00d7'}
          </button>
        </div>
      </div>

      {/* Model info bar */}
      {modelInfo && (
        <div className="lp-model-bar">
          <div className="lp-model-row">
            <span className="lp-model-tag">{backendLabel}</span>
            <span className="lp-model-name">{modelInfo.model}</span>
            {tierLabel && <span className="lp-model-tier">{tierLabel}</span>}
          </div>
          <div className="lp-model-row lp-model-sub">
            <span>embed: {modelInfo.embedding}</span>
            <span className="lp-model-sep">{'\u00b7'}</span>
            <span>rerank: {modelInfo.reranker}</span>
          </div>
          {modelInfo.classification && (
            <div className="lp-model-row lp-model-sub lp-classification">
              <span>{modelInfo.classification}</span>
            </div>
          )}
        </div>
      )}

      <div className="lp-body" ref={bodyRef}>

        {/* ═══ RETRIEVAL ═══ */}
        <div className="lp-section-wrap">
          <SectionTag letter="R" label="RETRIEVAL" status={retrievalStatus} />
          <div className="lp-section-body">

            {/* Parallel retrieval boxes */}
            <div className="lp-parallel">
              <FlowBox
                name="auto_retrieve"
                sublabel="Qdrant hybrid search"
                status={autoRetrieve?.status ?? 'idle'}
                timing={getTiming(autoRetrieve)}
                meta={autoRetrieve?.meta ? [
                  autoRetrieve.meta.sites_count != null && `${autoRetrieve.meta.sites_count} sites`,
                  autoRetrieve.meta.news_count != null && `${autoRetrieve.meta.news_count} news`,
                  autoRetrieve.meta.voyage_tokens != null && (autoRetrieve.meta.voyage_tokens as number) > 0 && `${autoRetrieve.meta.voyage_tokens} embed`,
                ].filter(Boolean).join(' \u00b7 ') || undefined : undefined}
              />
              <FlowBox
                name="filter_extract"
                sublabel="LLM-structured filters"
                status={filterExtract?.status ?? 'idle'}
                timing={getTiming(filterExtract)}
                meta={filterExtract?.meta?.filters ? `${Object.keys(filterExtract.meta.filters as object).length} filters` : undefined}
                error={filterExtract?.meta?.error ? String(filterExtract.meta.error) : null}
              />
            </div>

            {/* Knowledge sources grid */}
            <div className="lp-sources">
              <div className="lp-sources-title">KNOWLEDGE SOURCES</div>
              <div className="lp-sources-grid">
                <div className="lp-source-col">
                  <div className="lp-source-hdr">PostgreSQL</div>
                  {pgSources.map(s => (
                    <div key={s.def.name} className={`lp-source-item ${statusClass(s.status)}`}>
                      {statusIcon(s.status)} {s.def.label}{s.callCount > 0 ? ` (${s.callCount})` : ''}
                    </div>
                  ))}
                </div>
                <div className="lp-source-col">
                  <div className="lp-source-hdr">Qdrant</div>
                  {qdSources.map(s => (
                    <div key={s.def.name} className={`lp-source-item ${statusClass(s.status)}`}>
                      {statusIcon(s.status)} {s.def.label}{s.callCount > 0 ? ` (${s.callCount})` : ''}
                    </div>
                  ))}
                </div>
                <div className="lp-source-col">
                  <div className="lp-source-hdr">Seshat</div>
                  {sesSources.map(s => (
                    <div key={s.def.name} className={`lp-source-item ${statusClass(s.status)}`}>
                      {statusIcon(s.status)} {s.def.label}{s.callCount > 0 ? ` (${s.callCount})` : ''}
                    </div>
                  ))}
                </div>
                {anthropicSources.length > 0 && (
                  <div className="lp-source-col">
                    <div className="lp-source-hdr">Anthropic</div>
                    {anthropicSources.map(s => (
                      <div key={s.def.name} className={`lp-source-item ${statusClass(s.status)}`}>
                        {statusIcon(s.status)} {s.def.label}{s.callCount > 0 ? ` (${s.callCount})` : ''}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <FlowArrow />

        {/* ═══ AUGMENTATION ═══ */}
        <div className="lp-section-wrap">
          <SectionTag letter="A" label="AUGMENTATION" status={augStatus} />
          <div className="lp-section-body">
            <div className="lp-flow-row">
              <FlowBox
                name="news_augment"
                sublabel="SQL + dedup"
                status={newsAugment?.status ?? 'idle'}
                timing={getTiming(newsAugment)}
                meta={newsAugment?.meta?.count != null ? `${newsAugment.meta.count} items` : undefined}
              />
              <FlowArrowH />
              <FlowBox
                name="context_asm"
                sublabel="System prompt"
                status={ctxAssembly?.status ?? 'idle'}
                timing={getTiming(ctxAssembly)}
                meta={ctxAssembly?.meta?.message_count != null ? `${ctxAssembly.meta.message_count} msgs` : undefined}
              />
              <FlowArrowH />
              <FlowBox
                name="pre_emit"
                sublabel="Map dots"
                status={preEmit?.status ?? 'idle'}
                timing={getTiming(preEmit)}
                meta={preEmit?.meta ? [
                  preEmit.meta.sites != null && `${preEmit.meta.sites}s`,
                  preEmit.meta.news != null && `${preEmit.meta.news}n`,
                ].filter(Boolean).join(' ') || undefined : undefined}
              />
            </div>
          </div>
        </div>

        <FlowArrow />

        {/* ═══ GENERATION ═══ */}
        <div className="lp-section-wrap">
          <SectionTag letter="G" label="GENERATION" status={genStatus} />
          <div className="lp-section-body">

            {rounds.length === 0 && (
              <div className="lp-box lp-st-idle">
                <div className="lp-box-header">
                  <span className="lp-box-icon">{'\u00b7'}</span>
                  <span className="lp-box-name">llm_round</span>
                </div>
                <div className="lp-box-sub">waiting...</div>
              </div>
            )}

            {rounds.map((round, idx) => {
              const roundNum = round.node.meta?.round ?? idx + 1
              const timing = getTiming(round.node)
              const tokens = round.node.meta?.round_tokens as number | undefined
              const hasTools = round.node.meta?.has_tools
              return (
                <div key={round.node.instanceId} className={`lp-round ${statusClass(round.node.status)}`}>
                  <div className="lp-round-header">
                    <span className="lp-round-icon">{statusIcon(round.node.status)}</span>
                    <span className="lp-round-name">Round #{String(roundNum)}</span>
                    {timing && <span className="lp-round-time">{timing}</span>}
                    {tokens != null && <span className="lp-round-tokens">{tokens.toLocaleString()} tok</span>}
                  </div>

                  {/* Tool calls within this round */}
                  {round.tools.length > 0 ? (
                    <div className="lp-round-tools">
                      {round.tools.map((tool, ti) => (
                        <div key={ti} className={`lp-tool-line ${statusClass(tool.status)}`}>
                          <span className="lp-tool-connector">{ti === round.tools.length - 1 ? '\u2514' : '\u251c'}\u2500</span>
                          <span className="lp-tool-name">{tool.name}</span>
                          {tool.args && Object.keys(tool.args).length > 0 && (
                            <span className="lp-tool-args">
                              ({Object.entries(tool.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})
                            </span>
                          )}
                          {tool.resultLen != null && (
                            <span className="lp-tool-result">{'\u2192'} {tool.resultLen}</span>
                          )}
                          {tool.duration_ms != null && (
                            <span className="lp-tool-time">{formatMs(tool.duration_ms)}</span>
                          )}
                          {tool.error && (
                            <span className="lp-tool-error">{'\u2717'} {tool.error}</span>
                          )}
                          {tool.resultPreview && (
                            <details className="lp-tool-preview">
                              <summary>response</summary>
                              <pre>{tool.resultPreview}</pre>
                            </details>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : hasTools === false ? (
                    <div className="lp-round-no-tools">no tools</div>
                  ) : round.node.status === 'active' ? (
                    <div className="lp-round-no-tools">streaming...</div>
                  ) : null}
                </div>
              )
            })}
          </div>
        </div>

        {/* ═══ SUMMARY ═══ */}
        {(totalMs !== null || totalTokens != null) && (
          <div className="lp-summary">
            <div className="lp-summary-title">{'\u2550'.repeat(3)} SUMMARY {'\u2550'.repeat(20)}</div>
            <div className="lp-summary-row">
              {totalMs !== null && <span>Total: {formatMs(totalMs)}</span>}
              {totalTokens != null && <span>{totalTokens.toLocaleString()} tok</span>}
              {totalToolCalls > 0 && <span>{totalToolCalls} tool{totalToolCalls !== 1 ? 's' : ''}</span>}
              {totalResults > 0 && <span>{totalResults} result{totalResults !== 1 ? 's' : ''}</span>}
              {totalWebSearches > 0 && <span>{totalWebSearches} web search{totalWebSearches !== 1 ? 'es' : ''}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
