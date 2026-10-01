import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { checkBlocks, drawnStrings } from '../src/blocks'
import { REGISTRY_BLOCKS } from '../src/blocks/schemas'
import { type Timeline, parseTimeline, sceneHasCaptions } from '../src/timeline'
import { HOOK_LIMITS, capacityTimeline, drawnLimits, fill, solidPng, variantKey } from './capacity'
import { schemaAt } from './registryHelpers'

/** Built on first use: an unbounded drawn string makes it throw, and the test that names it must still run. */
let built: { capacity: ReturnType<typeof capacityTimeline>; timeline: Timeline } | undefined
function episode() {
  if (!built) {
    const capacity = capacityTimeline()
    built = { capacity, timeline: parseTimeline(capacity.timeline) }
  }
  return built
}

describe('the capacity episode (the lint input of test/gpu/capacity.gpu.ts)', () => {
  it('is a valid timeline whose blocks pass their own checks', () => {
    expect(() => checkBlocks(episode().timeline)).not.toThrow()
  })
  it('shows every registry block on the full stage and on the hook stage, the end card on the full stage as the last scene', () => {
    const { timeline } = episode()
    for (const block of Object.keys(REGISTRY_BLOCKS)) {
      const scenes = timeline.scenes.filter((s) => s.block === block)
      expect(scenes.filter((s) => !sceneHasCaptions(timeline, s)).length, `${block} on the full stage`).toBeGreaterThan(0)
      // hook beats come first in a script, so the end card is never one
      expect(scenes.filter((s) => sceneHasCaptions(timeline, s)).length > 0, `${block} under hook captions`).toBe(block !== 'ShareCard')
    }
    expect(timeline.scenes[timeline.scenes.length - 1].block).toBe('ShareCard')
  })
  it('draws every string at its maxLength, and reaches every drawn pattern of every block', () => {
    const { timeline, capacity } = episode()
    for (const [block, entry] of Object.entries(REGISTRY_BLOCKS)) {
      const scenes = timeline.scenes.filter((s) => s.block === block)
      for (const pattern of entry.drawn) {
        const reached = scenes.flatMap((s) => drawnStrings(s.props, [pattern], `${s.id}.props`))
        expect(reached.length, `${block}: ${pattern} is in no scene`).toBeGreaterThan(0)
        const schema = schemaAt(entry.props, pattern)
        for (const scene of scenes) {
          const stage = capacity.cases.find((c) => c.id === scene.id) as { block: string; variant: string; hook: boolean }
          const limit = stage.hook ? HOOK_LIMITS[variantKey(block, stage.variant)]?.[pattern] : undefined
          for (const [path, text] of drawnStrings(scene.props, [pattern], `${scene.id}.props`)) {
            if (schema?.enum) expect(schema.enum, path).toContain(text)
            else expect(text.length, path).toBe(limit ?? schema?.maxLength)
          }
        }
      }
    }
  })
  it('gives every drawn string a maxLength: text with no limit cannot be proved to fit (an enum has a longest value)', () => {
    for (const [block, entry] of Object.entries(REGISTRY_BLOCKS)) {
      for (const pattern of entry.drawn) {
        const schema = schemaAt(entry.props, pattern)
        expect(schema?.enum !== undefined || schema?.maxLength !== undefined, `${block}: ${pattern}`).toBe(true)
      }
    }
  })
  it('widens the layouts that change with their content: the most claims, the most list items, the card with its image', () => {
    const { timeline } = episode()
    const ids = (block: string) => timeline.scenes.filter((s) => s.block === block).map((s) => s.id)
    expect(ids('ClaimBoard').filter((id) => id.includes('mostclaims')).length).toBe(2)
    expect(ids('ListCard').filter((id) => id.includes('mostitems')).length).toBe(2)
    expect(ids('EvidenceCard').filter((id) => id.includes('withimage')).length).toBe(2)
  })
  it('names the images and clips it needs, and every image is a PNG that exists in the lint run', () => {
    const { assets } = episode().capacity
    expect(assets.length).toBeGreaterThan(0)
    for (const asset of assets) expect(asset, 'an image the browser decodes is generated as PNG').toMatch(/\.(png|mp4)$/)
    expect(solidPng(8, 4).subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
  })
})

describe('the limits of the registry', () => {
  /**
   * CI cannot run test/gpu/capacity.gpu.ts, the proof that every drawn string fits its box at its
   * maxLength. This pins the limits the proof last held for (2026-10-01): a limit raised without a
   * green `npm run test:gpu` is a promise the layout may not keep, and `episode check` would make
   * it. After a green GPU run, record the new limits in test/fixtures/capacity-limits.json.
   */
  it('are the limits the real-browser capacity proof held for', () => {
    const proven = JSON.parse(readFileSync(fileURLToPath(new URL('./fixtures/capacity-limits.json', import.meta.url)), 'utf-8'))
    expect(drawnLimits()).toEqual(proven)
  })
  it('are never above the hook-stage capacities that the proof records, which hold less than the schema limit', () => {
    const limits = drawnLimits()
    for (const [key, patterns] of Object.entries(HOOK_LIMITS)) {
      const block = key.split('.')[0]
      for (const [pattern, hookLimit] of Object.entries(patterns)) expect(hookLimit, `${key} ${pattern}`).toBeLessThan(limits[block][pattern] as number)
    }
  })
})

describe('fill', () => {
  it('is exactly n characters of words, never ending in a space', () => {
    for (const n of [1, 2, 24, 49, 50, 51, 60, 160, 260, 320]) {
      const text = fill(n)
      expect(text).toHaveLength(n)
      expect(text.endsWith(' ')).toBe(false)
      expect(text).not.toMatch(/ {2}/)
    }
  })
})
