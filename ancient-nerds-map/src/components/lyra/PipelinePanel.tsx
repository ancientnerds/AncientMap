/**
 * PipelinePanel — Real-time SVG visualization of Lyra's RAG pipeline.
 *
 * Renders a vertical flow graph showing each pipeline stage as a node
 * with animated edges. Parallel stages render side-by-side, repeatable
 * stages (LLM rounds, tool calls) stack vertically with nesting.
 */

import { useMemo } from 'react'
import type { PipelineTrace, PipelineNodeInstance } from '../../types/pipeline'
import { PIPELINE_STAGES } from '../../types/pipeline'

interface PipelinePanelProps {
  trace: PipelineTrace | null
  isLive: boolean
  onClose: () => void
}

// Layout constants
const W = 284          // SVG viewBox width (300px panel - 16px padding)
const NODE_W = 120     // Node rect width
const NODE_H = 38      // Node rect height
const PAR_NODE_W = 110 // Parallel node width (narrower)
const PAR_GAP = 16     // Gap between parallel nodes
const ROW_GAP = 14     // Vertical gap between rows
const TOOL_W = 100     // Tool call node width
const TOOL_H = 28      // Tool call node height
const TOOL_INDENT = 24 // Tool call left indent inside LLM round
const TOOL_GAP = 6     // Vertical gap between tool calls

const CX = W / 2       // Center X

function statusIcon(status: string): string {
  switch (status) {
    case 'done': return '\u2713'
    case 'error': return '\u2717'
    case 'skip': return '\u2014'
    case 'active': return '\u25CF'
    default: return ''
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

  // Stage-specific meta summaries
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
  if (m.tool != null) parts.push(String(m.tool))
  if (m.round != null && node.stageId === 'llm_round') parts.push(`#${m.round}`)
  if (m.has_tools === false && node.stageId === 'llm_round') parts.push('no tools')
  if (m.total_tokens != null) parts.push(`${(m.total_tokens as number).toLocaleString()} tok`)

  return parts.join(' \u00b7 ')
}

/** Compute elapsed time string for an active node */
function activeElapsed(node: PipelineNodeInstance): string {
  if (node.status !== 'active' || !node.startedAt) return ''
  // We don't re-render on a timer, so just show "..." for active
  return '...'
}

interface LayoutNode {
  x: number
  y: number
  w: number
  h: number
  node: PipelineNodeInstance
  isToolChild: boolean
}

interface LayoutEdge {
  x1: number; y1: number
  x2: number; y2: number
  status: 'idle' | 'active' | 'done'
}

function buildLayout(nodes: PipelineNodeInstance[]): { lnodes: LayoutNode[]; edges: LayoutEdge[]; totalH: number } {
  const lnodes: LayoutNode[] = []
  const edges: LayoutEdge[] = []
  let y = 8

  // Helper: get node by stageId (first match for non-repeatable)
  const getNode = (stageId: string) => nodes.find(n => n.stageId === stageId)

  // 1. Parallel group (phase1): auto_retrieve + filter_extraction
  const parStages = PIPELINE_STAGES.filter(s => s.parallelGroup === 'phase1')
  const parNodes = parStages.map(s => getNode(s.id))

  if (parNodes.some(Boolean)) {
    const totalParW = parStages.length * PAR_NODE_W + (parStages.length - 1) * PAR_GAP
    const startX = (W - totalParW) / 2

    // Fork point
    const forkY = y
    y += 8

    parStages.forEach((_, i) => {
      const pn = parNodes[i]
      const x = startX + i * (PAR_NODE_W + PAR_GAP)
      if (pn) {
        lnodes.push({ x, y, w: PAR_NODE_W, h: NODE_H, node: pn, isToolChild: false })
      } else {
        // Create idle placeholder
        lnodes.push({
          x, y, w: PAR_NODE_W, h: NODE_H,
          node: { instanceId: parStages[i].id, stageId: parStages[i].id, status: 'idle', duration_ms: null, meta: null, startedAt: null },
          isToolChild: false,
        })
      }
      // Fork edge
      edges.push({
        x1: CX, y1: forkY,
        x2: x + PAR_NODE_W / 2, y2: y,
        status: pn ? (pn.status === 'active' ? 'active' : pn.status === 'done' || pn.status === 'skip' ? 'done' : 'idle') : 'idle',
      })
    })

    y += NODE_H + 8

    // Join point
    const joinY = y
    parStages.forEach((_, i) => {
      const x = startX + i * (PAR_NODE_W + PAR_GAP) + PAR_NODE_W / 2
      const pn = parNodes[i]
      edges.push({
        x1: x, y1: joinY - 8,
        x2: CX, y2: joinY,
        status: pn ? (pn.status === 'done' || pn.status === 'skip' ? 'done' : pn.status === 'active' ? 'active' : 'idle') : 'idle',
      })
    })

    y = joinY + ROW_GAP
  }

  // 2. Sequential stages (non-parallel, non-repeatable, non-child)
  const seqStages = PIPELINE_STAGES.filter(s => !s.parallelGroup && !s.parentId && !s.isRepeatable)
  for (const stageDef of seqStages) {
    const sn = getNode(stageDef.id)
    const prevNode = lnodes[lnodes.length - 1]

    if (prevNode && !prevNode.isToolChild) {
      edges.push({
        x1: prevNode.x + prevNode.w / 2, y1: prevNode.y + prevNode.h,
        x2: CX, y2: y,
        status: sn ? (sn.status === 'active' ? 'active' : sn.status === 'done' || sn.status === 'skip' ? 'done' : 'idle') : 'idle',
      })
    }

    if (sn) {
      lnodes.push({ x: CX - NODE_W / 2, y, w: NODE_W, h: NODE_H, node: sn, isToolChild: false })
    } else {
      lnodes.push({
        x: CX - NODE_W / 2, y, w: NODE_W, h: NODE_H,
        node: { instanceId: stageDef.id, stageId: stageDef.id, status: 'idle', duration_ms: null, meta: null, startedAt: null },
        isToolChild: false,
      })
    }
    y += NODE_H + ROW_GAP
  }

  // 3. Repeatable stages: LLM rounds with nested tool calls
  const roundInstances = nodes.filter(n => n.stageId === 'llm_round')
  const toolInstances = nodes.filter(n => n.stageId === 'tool_call')

  // Track which tools belong to which round (sequential — tools after round N start, before round N+1 start)
  let toolIdx = 0
  for (let ri = 0; ri < roundInstances.length; ri++) {
    const roundNode = roundInstances[ri]
    const prevNode = ((arr) => arr[arr.length - 1])(lnodes.filter(ln => !ln.isToolChild))

    if (prevNode) {
      edges.push({
        x1: prevNode.x + prevNode.w / 2, y1: prevNode.y + prevNode.h,
        x2: CX, y2: y,
        status: roundNode.status === 'active' ? 'active' : roundNode.status === 'done' ? 'done' : 'idle',
      })
    }

    // LLM round label includes round number
    const roundLabel = roundNode.meta?.round ? `LLM Round ${roundNode.meta.round}` : 'LLM Round'
    const displayNode: PipelineNodeInstance = {
      ...roundNode,
      meta: { ...roundNode.meta, _label: roundLabel },
    }
    lnodes.push({ x: CX - NODE_W / 2, y, w: NODE_W, h: NODE_H, node: displayNode, isToolChild: false })
    y += NODE_H + TOOL_GAP

    // Nested tool calls for this round
    // Find tools between this round's start and the next round's start
    const nextRoundStartIdx = ri + 1 < roundInstances.length
      ? nodes.indexOf(roundInstances[ri + 1])
      : nodes.length
    const thisRoundStartIdx = nodes.indexOf(roundNode)

    while (toolIdx < toolInstances.length) {
      const toolNode = toolInstances[toolIdx]
      const toolGlobalIdx = nodes.indexOf(toolNode)
      if (toolGlobalIdx > thisRoundStartIdx && toolGlobalIdx < nextRoundStartIdx) {
        const tx = CX - NODE_W / 2 + TOOL_INDENT
        lnodes.push({ x: tx, y, w: TOOL_W, h: TOOL_H, node: toolNode, isToolChild: true })
        y += TOOL_H + TOOL_GAP
        toolIdx++
      } else {
        break
      }
    }

    y += ROW_GAP - TOOL_GAP
  }

  // 4. Done node
  const doneDef = PIPELINE_STAGES.find(s => s.id === 'done_credits')
  if (doneDef) {
    const doneNode = getNode('done_credits')
    const prevNode = ((arr) => arr[arr.length - 1])(lnodes.filter(ln => !ln.isToolChild))

    if (prevNode) {
      edges.push({
        x1: prevNode.x + prevNode.w / 2, y1: prevNode.y + prevNode.h,
        x2: CX, y2: y,
        status: doneNode ? (doneNode.status === 'done' ? 'done' : 'idle') : 'idle',
      })
    }

    if (doneNode) {
      lnodes.push({ x: CX - NODE_W / 2, y, w: NODE_W, h: NODE_H, node: doneNode, isToolChild: false })
    } else {
      lnodes.push({
        x: CX - NODE_W / 2, y, w: NODE_W, h: NODE_H,
        node: { instanceId: 'done_credits', stageId: 'done_credits', status: 'idle', duration_ms: null, meta: null, startedAt: null },
        isToolChild: false,
      })
    }
    y += NODE_H + 8
  }

  return { lnodes, edges, totalH: y }
}

function getStageLabel(node: PipelineNodeInstance): string {
  if (node.meta && (node.meta as Record<string, unknown>)._label) {
    return String((node.meta as Record<string, unknown>)._label)
  }
  const def = PIPELINE_STAGES.find(s => s.id === node.stageId)
  return def?.label ?? node.stageId
}

function getStageSublabel(node: PipelineNodeInstance): string {
  const def = PIPELINE_STAGES.find(s => s.id === node.stageId)
  return def?.sublabel ?? ''
}

export default function PipelinePanel({ trace, isLive, onClose }: PipelinePanelProps) {
  const nodes = trace?.nodes ?? []

  const { lnodes, edges, totalH } = useMemo(() => buildLayout(nodes), [nodes])

  const totalMs = useMemo(() => {
    const durations = nodes.filter(n => n.stageId !== 'tool_call' && n.stageId !== 'done_credits' && n.duration_ms != null)
    if (durations.length === 0) return null
    return durations.reduce((sum, n) => sum + (n.duration_ms ?? 0), 0)
  }, [nodes])

  return (
    <div className="lp-panel">
      <div className="lp-header">
        <div className="lp-header-left">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="6" cy="6" r="3" /><circle cx="18" cy="6" r="3" />
            <circle cx="12" cy="18" r="3" />
            <line x1="6" y1="9" x2="12" y2="15" /><line x1="18" y1="9" x2="12" y2="15" />
          </svg>
          Pipeline
          {isLive && (
            <span className="lp-live-badge">
              <span className="lp-live-dot" />
              LIVE
            </span>
          )}
        </div>
        <button className="lyra-chat-close-btn" onClick={onClose}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
          </svg>
        </button>
      </div>

      <div className="lp-body">
        <svg className="lp-graph" viewBox={`0 0 ${W} ${totalH}`} width={W} height={totalH}>
          {/* Edges */}
          {edges.map((e, i) => (
            <line
              key={`e${i}`}
              x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
              className={`lp-edge${e.status === 'active' ? ' lp-edge-active' : e.status === 'done' ? ' lp-edge-done' : ''}`}
            />
          ))}

          {/* Nodes */}
          {lnodes.map((ln) => {
            const label = getStageLabel(ln.node)
            const sublabel = getStageSublabel(ln.node)
            const timing = ln.node.status === 'active'
              ? activeElapsed(ln.node)
              : formatMs(ln.node.duration_ms)
            const meta = metaSummary(ln.node)
            const badge = [timing, meta].filter(Boolean).join(' \u00b7 ')
            const icon = statusIcon(ln.node.status)

            return (
              <g
                key={ln.node.instanceId}
                className={`lp-node-${ln.node.status}${ln.isToolChild ? ' lp-tool-indent' : ''}`}
                transform={`translate(${ln.x}, ${ln.y})`}
              >
                <rect
                  className="lp-node-rect"
                  width={ln.w}
                  height={ln.h}
                  x={0} y={0}
                />
                {/* Status icon */}
                {icon && (
                  <text
                    className="lp-node-status-icon"
                    x={8} y={ln.h / 2}
                    dominantBaseline="central"
                    textAnchor="start"
                    fill="currentColor"
                  >
                    {icon}
                  </text>
                )}
                {/* Label */}
                <text
                  className="lp-node-label"
                  x={icon ? 20 : 8}
                  y={badge ? ln.h * 0.38 : ln.h / 2}
                  dominantBaseline="central"
                >
                  {label}
                </text>
                {/* Sublabel or badge */}
                {badge ? (
                  <text
                    className="lp-node-badge"
                    x={icon ? 20 : 8}
                    y={ln.h * 0.72}
                    dominantBaseline="central"
                  >
                    {badge}
                  </text>
                ) : sublabel && ln.node.status === 'idle' ? (
                  <text
                    className="lp-node-sublabel"
                    x={icon ? 20 : 8}
                    y={ln.h * 0.72}
                    dominantBaseline="central"
                  >
                    {sublabel}
                  </text>
                ) : null}
              </g>
            )
          })}
        </svg>
      </div>

      {totalMs !== null && (
        <div className="lp-footer">
          Total: {formatMs(totalMs)}
        </div>
      )}
    </div>
  )
}
