/**
 * Tests for pipeline.ts — applyPipelineEvent pure function and stage/tool definitions.
 *
 * Verifies:
 * - State transitions (idle → active → done/error/skip)
 * - Repeatable stages (llm_round, tool_call) create new instances
 * - Non-repeatable stages transition existing instances
 * - PIPELINE_STAGES has all required stage definitions
 * - TOOL_REGISTRY has all tools with correct backends
 * - Edge cases (unknown stages, missing instances)
 */

import { describe, it, expect } from 'vitest'
import {
  applyPipelineEvent,
  PIPELINE_STAGES,
  TOOL_REGISTRY,
  type PipelineEvent,
  type PipelineNodeInstance,
} from './pipeline'

// ── Helpers ──

function makeEvent(stage: string, status: 'start' | 'done' | 'error' | 'skip', meta: Record<string, unknown> | null = null, duration_ms: number | null = null): PipelineEvent {
  return { stage, status, duration_ms, meta }
}

function makeNode(stageId: string, status: 'idle' | 'active' | 'done' | 'error' | 'skip' = 'idle', instanceId?: string): PipelineNodeInstance {
  return {
    instanceId: instanceId ?? stageId,
    stageId,
    status,
    duration_ms: null,
    meta: null,
    startedAt: null,
  }
}

// ── PIPELINE_STAGES definitions ──

describe('PIPELINE_STAGES', () => {
  it('contains all required stage IDs', () => {
    const ids = PIPELINE_STAGES.map(s => s.id)
    const required = [
      'pipeline_init', 'auto_retrieve', 'filter_extraction',
      'news_augmentation', 'context_assembly', 'pre_stream_emit',
      'llm_round', 'tool_call', 'done_credits',
    ]
    for (const id of required) {
      expect(ids).toContain(id)
    }
  })

  it('has no duplicate IDs', () => {
    const ids = PIPELINE_STAGES.map(s => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('marks llm_round and tool_call as repeatable', () => {
    const llm = PIPELINE_STAGES.find(s => s.id === 'llm_round')
    const tool = PIPELINE_STAGES.find(s => s.id === 'tool_call')
    expect(llm?.isRepeatable).toBe(true)
    expect(tool?.isRepeatable).toBe(true)
  })

  it('marks tool_call with parentId llm_round', () => {
    const tool = PIPELINE_STAGES.find(s => s.id === 'tool_call')
    expect(tool?.parentId).toBe('llm_round')
  })

  it('phase1 stages are in parallel group', () => {
    const autoRetrieve = PIPELINE_STAGES.find(s => s.id === 'auto_retrieve')
    const filterExtract = PIPELINE_STAGES.find(s => s.id === 'filter_extraction')
    expect(autoRetrieve?.parallelGroup).toBe('phase1')
    expect(filterExtract?.parallelGroup).toBe('phase1')
  })

  it('all stages have labels', () => {
    for (const stage of PIPELINE_STAGES) {
      expect(stage.label).toBeTruthy()
    }
  })
})

// ── TOOL_REGISTRY ──

describe('TOOL_REGISTRY', () => {
  it('has 11 tools', () => {
    expect(TOOL_REGISTRY).toHaveLength(11)
  })

  it('has correct backend assignments', () => {
    const pgTools = TOOL_REGISTRY.filter(t => t.backend === 'PostgreSQL')
    const qdTools = TOOL_REGISTRY.filter(t => t.backend === 'Qdrant')
    const sesTools = TOOL_REGISTRY.filter(t => t.backend === 'Seshat')

    expect(pgTools.length).toBe(6) // search_sites, get_site_details, search_news, search_radar, list_channels, get_site_images
    expect(qdTools.length).toBe(4) // vector_search, search_transcripts, search_articles, search_empires
    expect(sesTools.length).toBe(1) // get_empire_data
  })

  it('has unique tool names', () => {
    const names = TOOL_REGISTRY.map(t => t.name)
    expect(new Set(names).size).toBe(names.length)
  })
})

// ── applyPipelineEvent — non-repeatable stages ──

describe('applyPipelineEvent — non-repeatable stages', () => {
  it('creates new node on start event', () => {
    const nodes: PipelineNodeInstance[] = []
    const result = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'start'))
    expect(result).toHaveLength(1)
    expect(result[0].stageId).toBe('auto_retrieve')
    expect(result[0].status).toBe('active')
    expect(result[0].startedAt).not.toBeNull()
  })

  it('transitions existing node on start', () => {
    const nodes = [makeNode('auto_retrieve', 'idle')]
    const result = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'start'))
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('active')
  })

  it('transitions to done status', () => {
    const nodes = [makeNode('auto_retrieve', 'active')]
    const result = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'done', null, 150))
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('done')
    expect(result[0].duration_ms).toBe(150)
  })

  it('transitions to error status', () => {
    const nodes = [makeNode('auto_retrieve', 'active')]
    const result = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'error', { error: 'failed' }))
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('error')
  })

  it('transitions to skip status', () => {
    const nodes: PipelineNodeInstance[] = []
    const result = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'skip'))
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('skip')
  })

  it('preserves other nodes', () => {
    const nodes = [makeNode('pipeline_init', 'done'), makeNode('auto_retrieve', 'active')]
    const result = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'done'))
    expect(result).toHaveLength(2)
    expect(result[0].status).toBe('done') // pipeline_init unchanged
    expect(result[1].status).toBe('done') // auto_retrieve updated
  })

  it('preserves meta from start when done has no meta', () => {
    const nodes = [{ ...makeNode('auto_retrieve', 'active'), meta: { sites: 5 } }]
    const result = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'done', null, 100))
    expect(result[0].meta).toEqual({ sites: 5 })
  })

  it('overrides meta on done when provided', () => {
    const nodes = [{ ...makeNode('auto_retrieve', 'active'), meta: { old: true } }]
    const result = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'done', { new: true }, 100))
    expect(result[0].meta).toEqual({ new: true })
  })
})

// ── applyPipelineEvent — repeatable stages ──

describe('applyPipelineEvent — repeatable stages', () => {
  it('creates new instance on each start', () => {
    let nodes: PipelineNodeInstance[] = []
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'start', { round: 1 }))
    expect(nodes).toHaveLength(1)
    expect(nodes[0].instanceId).toBe('llm_round_0')

    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'done', null, 500))
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'start', { round: 2 }))
    expect(nodes).toHaveLength(2)
    expect(nodes[1].instanceId).toBe('llm_round_1')
  })

  it('finishes the last active instance', () => {
    let nodes: PipelineNodeInstance[] = []
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'start', { round: 1 }))
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'done', null, 300))
    expect(nodes[0].status).toBe('done')
    expect(nodes[0].duration_ms).toBe(300)
  })

  it('creates completed instance when no active instance exists', () => {
    const nodes: PipelineNodeInstance[] = []
    const result = applyPipelineEvent(nodes, makeEvent('llm_round', 'done', null, 100))
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('done')
    expect(result[0].startedAt).toBeNull()
  })

  it('merges meta on repeatable done', () => {
    let nodes: PipelineNodeInstance[] = []
    nodes = applyPipelineEvent(nodes, makeEvent('tool_call', 'start', { tool: 'search_sites' }))
    nodes = applyPipelineEvent(nodes, makeEvent('tool_call', 'done', { result_len: 5 }, 200))
    expect(nodes[0].meta).toEqual({ tool: 'search_sites', result_len: 5 })
  })

  it('handles interleaved tool calls within rounds', () => {
    let nodes: PipelineNodeInstance[] = []
    // Round 1 starts
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'start', { round: 1 }))
    // Tool call 1 starts and finishes
    nodes = applyPipelineEvent(nodes, makeEvent('tool_call', 'start', { tool: 'search_sites' }))
    nodes = applyPipelineEvent(nodes, makeEvent('tool_call', 'done', { result_len: 3 }, 100))
    // Tool call 2 starts and finishes
    nodes = applyPipelineEvent(nodes, makeEvent('tool_call', 'start', { tool: 'vector_search' }))
    nodes = applyPipelineEvent(nodes, makeEvent('tool_call', 'done', { result_len: 5 }, 200))
    // Round 1 finishes
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'done', null, 1000))

    expect(nodes).toHaveLength(3) // 1 round + 2 tool calls
    expect(nodes.filter(n => n.stageId === 'tool_call')).toHaveLength(2)
    expect(nodes.filter(n => n.stageId === 'llm_round')).toHaveLength(1)
    expect(nodes.every(n => n.status === 'done')).toBe(true)
  })
})

// ── applyPipelineEvent — edge cases ──

describe('applyPipelineEvent — edge cases', () => {
  it('ignores unknown stage IDs', () => {
    const nodes: PipelineNodeInstance[] = []
    const result = applyPipelineEvent(nodes, makeEvent('unknown_stage', 'start'))
    expect(result).toHaveLength(0) // No change
  })

  it('handles empty nodes array', () => {
    const result = applyPipelineEvent([], makeEvent('pipeline_init', 'done', { model: 'test' }))
    expect(result).toHaveLength(1)
  })

  it('handles full pipeline sequence', () => {
    let nodes: PipelineNodeInstance[] = []

    // Full pipeline flow
    nodes = applyPipelineEvent(nodes, makeEvent('pipeline_init', 'done', { model: 'qwen3.5:4b' }))
    nodes = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'start'))
    nodes = applyPipelineEvent(nodes, makeEvent('filter_extraction', 'start'))
    nodes = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'done', { sites_count: 5 }, 200))
    nodes = applyPipelineEvent(nodes, makeEvent('filter_extraction', 'done', { filters: {} }, 300))
    nodes = applyPipelineEvent(nodes, makeEvent('news_augmentation', 'start'))
    nodes = applyPipelineEvent(nodes, makeEvent('news_augmentation', 'done', { count: 3 }, 50))
    nodes = applyPipelineEvent(nodes, makeEvent('context_assembly', 'done', null, 5))
    nodes = applyPipelineEvent(nodes, makeEvent('pre_stream_emit', 'done', { sites: 5, news: 3 }))
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'start', { round: 1 }))
    nodes = applyPipelineEvent(nodes, makeEvent('tool_call', 'start', { tool: 'search_sites' }))
    nodes = applyPipelineEvent(nodes, makeEvent('tool_call', 'done', { result_len: 10 }, 150))
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'done', null, 2000))
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'start', { round: 2 }))
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'done', null, 1500))
    nodes = applyPipelineEvent(nodes, makeEvent('done_credits', 'done', { total_tokens: 500 }))

    // Verify counts
    const nonRepeatables = nodes.filter(n => !['llm_round', 'tool_call'].includes(n.stageId))
    const rounds = nodes.filter(n => n.stageId === 'llm_round')
    const tools = nodes.filter(n => n.stageId === 'tool_call')

    expect(nonRepeatables).toHaveLength(7) // init, auto, filter, news, ctx, pre, done
    expect(rounds).toHaveLength(2)
    expect(tools).toHaveLength(1)
    expect(nodes.every(n => n.status === 'done')).toBe(true)
  })

  it('handles skip-only pipeline (fast tier)', () => {
    let nodes: PipelineNodeInstance[] = []
    nodes = applyPipelineEvent(nodes, makeEvent('pipeline_init', 'done'))
    nodes = applyPipelineEvent(nodes, makeEvent('auto_retrieve', 'skip'))
    nodes = applyPipelineEvent(nodes, makeEvent('filter_extraction', 'skip'))
    nodes = applyPipelineEvent(nodes, makeEvent('news_augmentation', 'skip'))
    nodes = applyPipelineEvent(nodes, makeEvent('context_assembly', 'done'))
    nodes = applyPipelineEvent(nodes, makeEvent('pre_stream_emit', 'done'))
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'start'))
    nodes = applyPipelineEvent(nodes, makeEvent('llm_round', 'done'))
    nodes = applyPipelineEvent(nodes, makeEvent('done_credits', 'done'))

    const skipped = nodes.filter(n => n.status === 'skip')
    expect(skipped).toHaveLength(3)
  })
})
