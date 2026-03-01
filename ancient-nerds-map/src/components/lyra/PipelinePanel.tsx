/**
 * PipelinePanel — Terminal/matrix-style pipeline trace viewer.
 *
 * Shows all pipeline stages as an ASCII tree with section headers,
 * and all 11 tools pre-rendered in grey, lighting up as they're used.
 * Used tools show their args (WHY Lyra chose them) and result counts.
 */

import { useMemo, useRef, useEffect, useState } from 'react'
import type { PipelineTrace, PipelineNodeInstance, PipelineNodeStatus, ToolDef } from '../../types/pipeline'
import { PIPELINE_STAGES, TOOL_REGISTRY } from '../../types/pipeline'

interface PipelinePanelProps {
  trace: PipelineTrace | null
  isLive: boolean
  onClose: () => void
}

interface ToolView {
  def: ToolDef
  status: PipelineNodeStatus
  duration_ms: number | null
  args: Record<string, unknown> | null
  resultLen: number | null
  error: string | null
}

interface RoundInfo {
  node: PipelineNodeInstance
  toolNames: string[]
}

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

function formatMs(ms: number | null): string {
  if (ms === null) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function metaSummary(node: PipelineNodeInstance): string {
  const m = node.meta
  if (!m) return ''
  const parts: string[] = []
  if (m.sites_count != null) parts.push(`${m.sites_count} sites`)
  if (m.news_count != null) parts.push(`${m.news_count} news`)
  if (m.voyage_tokens != null && (m.voyage_tokens as number) > 0) parts.push(`${m.voyage_tokens} embed`)
  if (m.filters != null) {
    const f = m.filters as Record<string, unknown>
    parts.push(`${Object.keys(f).length} filter${Object.keys(f).length !== 1 ? 's' : ''}`)
  }
  if (m.count != null) parts.push(`${m.count} items`)
  if (m.message_count != null) parts.push(`${m.message_count} msgs`)
  if (m.sites != null && m.news != null) parts.push(`${m.sites}s ${m.news}n`)
  if (m.round_tokens != null) parts.push(`${(m.round_tokens as number).toLocaleString()} tok`)
  if (m.total_tokens != null) parts.push(`${(m.total_tokens as number).toLocaleString()} tok`)
  return parts.join(' \u00b7 ')
}

/** Map each LLM round to the tool names called within it */
function buildRoundInfos(nodes: PipelineNodeInstance[]): RoundInfo[] {
  const rounds = nodes.filter(n => n.stageId === 'llm_round')
  return rounds.map((round, ri) => {
    const roundIdx = nodes.indexOf(round)
    const nextRoundIdx = ri + 1 < rounds.length ? nodes.indexOf(rounds[ri + 1]) : nodes.length
    const toolNames: string[] = []
    for (let i = roundIdx + 1; i < nextRoundIdx; i++) {
      if (nodes[i].stageId === 'tool_call' && nodes[i].meta?.tool) {
        toolNames.push(String(nodes[i].meta!.tool))
      }
    }
    return { node: round, toolNames }
  })
}

function buildToolViews(nodes: PipelineNodeInstance[]): ToolView[] {
  return TOOL_REGISTRY.map(def => {
    const matching = nodes.filter(n => n.stageId === 'tool_call' && n.meta?.tool === def.name)
    if (matching.length === 0) {
      return { def, status: 'idle', duration_ms: null, args: null, resultLen: null, error: null }
    }
    const node = matching[matching.length - 1]
    const args = (node.meta?.args as Record<string, unknown>) ?? null
    const resultLen = node.meta?.result_len != null ? Number(node.meta.result_len) : null
    const error = node.meta?.error ? String(node.meta.error) : null
    return { def, status: node.status, duration_ms: node.duration_ms, args, resultLen, error }
  })
}

// ── Sub-components ──

function SectionHeader({ label }: { label: string }) {
  const dashes = '\u2500'.repeat(Math.max(1, 34 - label.length))
  return <div className="lp-section">{'\u2500\u2500'} {label} {dashes}</div>
}

function TreeLine({ name, status, timing, isLast }: {
  name: string; status: PipelineNodeStatus; timing: string; isLast: boolean
}) {
  const connector = isLast ? '\u2514\u2500' : '\u251c\u2500'
  const icon = statusIcon(status)
  return (
    <div className={`lp-line lp-line-${status}`}>
      <span className="lp-connector">{connector}</span>
      <span className="lp-name">{name}</span>
      <span className="lp-status">{icon}</span>
      <span className="lp-timing">{timing}</span>
    </div>
  )
}

function MetaLine({ text, isLast }: { text: string; isLast: boolean }) {
  const connector = isLast ? '   ' : '\u2502  '
  return <div className="lp-meta"><span className="lp-connector">{connector}</span>{text}</div>
}

function ArgsLine({ args, isLast }: { args: Record<string, unknown>; isLast: boolean }) {
  const connector = isLast ? '   ' : '\u2502  '
  const text = Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' ')
  return <div className="lp-meta lp-args"><span className="lp-connector">{connector}</span>{text}</div>
}

function ResultLine({ count, isLast }: { count: number; isLast: boolean }) {
  const connector = isLast ? '   ' : '\u2502  '
  return <div className="lp-meta lp-result"><span className="lp-connector">{connector}</span>{'\u2192'} {count} result{count !== 1 ? 's' : ''}</div>
}

/** Live elapsed timer for active nodes */
function useElapsedTimer(nodes: PipelineNodeInstance[], isLive: boolean) {
  const [, setTick] = useState(0)
  const hasActive = isLive && nodes.some(n => n.status === 'active')
  useEffect(() => {
    if (!hasActive) return
    const id = setInterval(() => setTick(t => t + 1), 200)
    return () => clearInterval(id)
  }, [hasActive])
}

function activeElapsed(node: PipelineNodeInstance): string {
  if (node.status !== 'active' || !node.startedAt) return '...'
  const ms = Math.round(performance.now() - node.startedAt)
  return formatMs(ms)
}

// ── Stage grouping ──

interface StageGroup {
  label: string
  stageIds: string[]
}

const STAGE_GROUPS: StageGroup[] = [
  { label: 'RETRIEVAL', stageIds: ['auto_retrieve', 'filter_extraction'] },
  { label: 'AUGMENTATION', stageIds: ['news_augmentation', 'context_assembly', 'pre_stream_emit'] },
  { label: 'LLM REASONING', stageIds: ['llm_round'] },
]

const BACKENDS = ['PostgreSQL', 'Qdrant', 'Seshat']

export default function PipelinePanel({ trace, isLive, onClose }: PipelinePanelProps) {
  const nodes = trace?.nodes ?? []
  const bodyRef = useRef<HTMLDivElement>(null)

  const toolViews = useMemo(() => buildToolViews(nodes), [nodes])
  const roundInfos = useMemo(() => buildRoundInfos(nodes), [nodes])

  // #4: Live elapsed timer — re-renders every 200ms while nodes are active
  useElapsedTimer(nodes, isLive)

  const totalMs = useMemo(() => {
    const durations = nodes.filter(n => n.stageId !== 'tool_call' && n.stageId !== 'done_credits' && n.duration_ms != null)
    if (durations.length === 0) return null
    return durations.reduce((sum, n) => sum + (n.duration_ms ?? 0), 0)
  }, [nodes])

  const doneNode = nodes.find(n => n.stageId === 'done_credits')

  // #1: Auto-scroll to bottom during live streaming
  useEffect(() => {
    if (isLive && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [isLive, nodes])

  return (
    <div className="lp-panel">

      <div className="lp-header">
        <div className="lp-header-left">
          {'>'} PIPELINE TRACE
          {isLive && (
            <span className="lp-live-badge">
              LIVE <span className="lp-live-dot" />
            </span>
          )}
        </div>
        <button className="lyra-chat-close-btn" onClick={onClose} title="Close pipeline">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
          </svg>
        </button>
      </div>

      <div className="lp-body" ref={bodyRef}>
        {/* Pipeline stage groups */}
        {STAGE_GROUPS.map(group => {
          // For LLM rounds, use the repeatable instances with tool names
          if (group.stageIds[0] === 'llm_round') {
            return (
              <div key={group.label}>
                <SectionHeader label={group.label} />
                {roundInfos.length === 0 ? (
                  <TreeLine name="llm_round" status="idle" timing="idle" isLast={true} />
                ) : (
                  roundInfos.map((ri, idx) => {
                    const { node: round, toolNames } = ri
                    const isLast = idx === roundInfos.length - 1
                    const roundNum = round.meta?.round ?? idx + 1
                    // #4: Live elapsed for active rounds
                    const timing = round.status === 'active' ? activeElapsed(round) : formatMs(round.duration_ms)
                    const meta = metaSummary(round)
                    // #3 + #6: Show tool count and names
                    const hasTools = round.meta?.has_tools
                    const toolLine = hasTools === false
                      ? 'no tools'
                      : toolNames.length > 0
                        ? `${toolNames.length} tool${toolNames.length !== 1 ? 's' : ''}: ${toolNames.join(', ')}`
                        : round.status === 'active' ? 'calling tools...' : null
                    // Filter out the old "tool calls" / "no tools" from meta since we show it separately
                    const metaClean = meta.replace(/\btool calls\b/, '').replace(/\bno tools\b/, '').replace(/\u00b7\s*\u00b7/g, '\u00b7').replace(/^\s*\u00b7\s*/, '').replace(/\s*\u00b7\s*$/, '').trim()
                    return (
                      <div key={round.instanceId}>
                        <TreeLine
                          name={`llm_round #${roundNum}`}
                          status={round.status}
                          timing={timing}
                          isLast={isLast}
                        />
                        {metaClean && <MetaLine text={metaClean} isLast={isLast} />}
                        {toolLine && <MetaLine text={toolLine} isLast={isLast} />}
                      </div>
                    )
                  })
                )}
              </div>
            )
          }

          // Regular sequential stages
          const stageNodes = group.stageIds.map(id => {
            const existing = nodes.find(n => n.stageId === id)
            const def = PIPELINE_STAGES.find(s => s.id === id)
            return { id, node: existing, label: def?.label ?? id }
          })

          return (
            <div key={group.label}>
              <SectionHeader label={group.label} />
              {stageNodes.map((s, i) => {
                const isLast = i === stageNodes.length - 1
                const status: PipelineNodeStatus = s.node?.status ?? 'idle'
                // #4: Live elapsed for active stages
                const timing = status === 'active' ? activeElapsed(s.node!) : status === 'idle' ? 'idle' : formatMs(s.node?.duration_ms ?? null)
                const meta = s.node ? metaSummary(s.node) : ''
                const error = s.node?.meta?.error ? String(s.node.meta.error) : null
                return (
                  <div key={s.id}>
                    <TreeLine name={s.id} status={status} timing={timing} isLast={isLast} />
                    {meta && <MetaLine text={meta} isLast={isLast} />}
                    {error && <MetaLine text={`\u2717 ${error}`} isLast={isLast} />}
                  </div>
                )
              })}
            </div>
          )
        })}

        {/* Tool calls section — collapse idle backends (#2), show used tools */}
        <SectionHeader label="TOOL CALLS" />
        {BACKENDS.map(backend => {
          const tools = toolViews.filter(t => t.def.backend === backend)
          const allIdle = tools.every(t => t.status === 'idle')

          // #2: Collapse idle backends to a single dim line
          if (allIdle) {
            return (
              <div key={backend} className="lp-backend-group">
                <div className="lp-backend-label lp-backend-idle">{backend} <span className="lp-idle-count">{'\u00b7'} {tools.length} tools idle</span></div>
              </div>
            )
          }

          return (
            <div key={backend} className="lp-backend-group">
              <div className="lp-backend-label">{backend}</div>
              {tools.map((tool, i) => {
                const isLast = i === tools.length - 1
                // #4: Live elapsed for active tools
                const timing = tool.status === 'done' ? formatMs(tool.duration_ms)
                  : tool.status === 'active' ? '...'
                  : tool.status === 'error' ? formatMs(tool.duration_ms)
                  : 'idle'
                return (
                  <div key={tool.def.name}>
                    <TreeLine
                      name={tool.def.label}
                      status={tool.status}
                      timing={timing}
                      isLast={isLast}
                    />
                    {tool.args && Object.keys(tool.args).length > 0 && (
                      <ArgsLine args={tool.args} isLast={isLast} />
                    )}
                    {tool.resultLen != null && (
                      <ResultLine count={tool.resultLen} isLast={isLast} />
                    )}
                    {tool.error && (
                      <MetaLine text={`\u2717 ${tool.error}`} isLast={isLast} />
                    )}
                  </div>
                )
              })}
            </div>
          )
        })}

        {/* Done section */}
        <SectionHeader label="DONE" />
        <TreeLine
          name="done"
          status={doneNode?.status ?? 'idle'}
          timing={doneNode?.meta?.total_tokens ? `${(doneNode.meta.total_tokens as number).toLocaleString()} tok` : doneNode?.status === 'done' ? '\u2713' : 'idle'}
          isLast={true}
        />
      </div>

      {totalMs !== null && (
        <div className="lp-footer">
          {'\u2500'.repeat(38)}<br />
          total: {formatMs(totalMs)}
        </div>
      )}
    </div>
  )
}
