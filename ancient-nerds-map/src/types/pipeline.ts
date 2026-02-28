/**
 * Pipeline visualization types — single source of truth for Lyra pipeline tracing.
 */

export type PipelineNodeStatus = 'idle' | 'active' | 'done' | 'error' | 'skip'

export interface PipelineEvent {
  stage: string
  status: 'start' | 'done' | 'error' | 'skip'
  duration_ms: number | null
  meta: Record<string, unknown> | null
}

export interface PipelineNodeInstance {
  instanceId: string
  stageId: string
  status: PipelineNodeStatus
  duration_ms: number | null
  meta: Record<string, unknown> | null
  startedAt: number | null
}

export interface PipelineTrace {
  nodes: PipelineNodeInstance[]
  isLive: boolean
}

export interface PipelineNodeDef {
  id: string
  label: string
  sublabel?: string
  parallelGroup?: string
  isRepeatable?: boolean
  parentId?: string
}

export const PIPELINE_STAGES: PipelineNodeDef[] = [
  { id: 'auto_retrieve', label: 'Auto-Retrieve', sublabel: 'Qdrant hybrid search', parallelGroup: 'phase1' },
  { id: 'filter_extraction', label: 'Filter Extraction', sublabel: 'LLM-structured filters', parallelGroup: 'phase1' },
  { id: 'news_augmentation', label: 'News Augmentation', sublabel: 'SQL + deduplication' },
  { id: 'context_assembly', label: 'Context Assembly', sublabel: 'System prompt + history' },
  { id: 'pre_stream_emit', label: 'Pre-emit Sites/News', sublabel: 'Map highlights' },
  { id: 'llm_round', label: 'LLM Round', sublabel: 'Streaming + reasoning', isRepeatable: true },
  { id: 'tool_call', label: 'Tool Call', parentId: 'llm_round', isRepeatable: true },
  { id: 'done_credits', label: 'Done', sublabel: 'Credits + achievements' },
]

/**
 * Pure function: apply a backend pipeline event to the node list.
 * Repeatable stages (llm_round, tool_call) create new instances on each "start".
 * Non-repeatable stages transition idle → active → done/error/skip.
 */
export function applyPipelineEvent(
  nodes: PipelineNodeInstance[],
  event: PipelineEvent,
): PipelineNodeInstance[] {
  const stageDef = PIPELINE_STAGES.find(s => s.id === event.stage)
  if (!stageDef) return nodes

  if (event.status === 'start') {
    if (stageDef.isRepeatable) {
      // Count existing instances of this stage to generate unique ID
      const count = nodes.filter(n => n.stageId === event.stage).length
      const instanceId = `${event.stage}_${count}`
      return [
        ...nodes,
        {
          instanceId,
          stageId: event.stage,
          status: 'active',
          duration_ms: null,
          meta: event.meta,
          startedAt: performance.now(),
        },
      ]
    }
    // Non-repeatable: find existing or create
    const existing = nodes.find(n => n.stageId === event.stage)
    if (existing) {
      return nodes.map(n =>
        n === existing
          ? { ...n, status: 'active' as const, startedAt: performance.now(), meta: event.meta }
          : n,
      )
    }
    return [
      ...nodes,
      {
        instanceId: event.stage,
        stageId: event.stage,
        status: 'active',
        duration_ms: null,
        meta: event.meta,
        startedAt: performance.now(),
      },
    ]
  }

  // done / error / skip
  const status: PipelineNodeStatus =
    event.status === 'done' ? 'done' : event.status === 'error' ? 'error' : 'skip'

  if (stageDef.isRepeatable) {
    // Find the last active instance of this stage
    let idx = -1
    for (let i = nodes.length - 1; i >= 0; i--) {
      if (nodes[i].stageId === event.stage && nodes[i].status === 'active') { idx = i; break }
    }
    if (idx >= 0) {
      const updated = [...nodes]
      updated[idx] = {
        ...updated[idx],
        status,
        duration_ms: event.duration_ms,
        meta: event.meta ?? updated[idx].meta,
      }
      return updated
    }
    // No active instance — create a completed one
    const count = nodes.filter(n => n.stageId === event.stage).length
    return [
      ...nodes,
      {
        instanceId: `${event.stage}_${count}`,
        stageId: event.stage,
        status,
        duration_ms: event.duration_ms,
        meta: event.meta,
        startedAt: null,
      },
    ]
  }

  // Non-repeatable: update or create
  const existing = nodes.find(n => n.stageId === event.stage)
  if (existing) {
    return nodes.map(n =>
      n === existing
        ? { ...n, status, duration_ms: event.duration_ms, meta: event.meta ?? n.meta }
        : n,
    )
  }
  return [
    ...nodes,
    {
      instanceId: event.stage,
      stageId: event.stage,
      status,
      duration_ms: event.duration_ms,
      meta: event.meta,
      startedAt: null,
    },
  ]
}
