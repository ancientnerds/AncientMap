import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { checkBlocks } from '../src/blocks'
import { parseTimeline } from '../src/timeline'

/**
 * Plan C's compiler output for its fixture episode (plan C Task 21, kept current by its
 * test_golden_timeline_is_current): the renderer must read it exactly as committed.
 */
const GOLDEN = new URL('../../tests/pipeline/studio/golden_timeline.json', import.meta.url)

describe("plan C's compiled timeline.json (contracts C8 and D3)", () => {
  it('parses, passes every block check, runs at 60 fps and keeps its hook captions uppercase', () => {
    const raw: unknown = JSON.parse(readFileSync(GOLDEN, 'utf-8'))
    expect(() => checkBlocks(parseTimeline(raw))).not.toThrow()
    const timeline = parseTimeline(raw)
    expect(timeline.fps).toBe(60)
    for (const caption of timeline.captions) expect(caption.text).toBe(caption.text.toUpperCase())
  })
})
