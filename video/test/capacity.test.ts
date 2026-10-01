import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { checkBlocks, drawnStrings } from '../src/blocks'
import { REGISTRY_BLOCKS } from '../src/blocks/schemas'
import { type Timeline, parseTimeline, sceneHasCaptions } from '../src/timeline'
import { capacityTimeline, drawnLimits, fill, hookLimits, solidPng } from './capacity'
import { schemaAt, schemaNodes } from './registryHelpers'

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
          const limit = stage.hook ? schema?.hookMaxLength : undefined
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
   * it. After a green GPU run, record the new limits in test/fixtures/capacity-limits.json, and the
   * hook-stage capacities (hookMaxLength, hookMaxItems) in test/fixtures/capacity-hook-limits.json.
   */
  it('are the limits the real-browser capacity proof held for', () => {
    const proven = JSON.parse(readFileSync(fileURLToPath(new URL('./fixtures/capacity-limits.json', import.meta.url)), 'utf-8'))
    expect(drawnLimits()).toEqual(proven)
  })
  it('are the hook-stage capacities the real-browser proof held for (hookMaxLength, hookMaxItems: what `episode check` refuses on a hook beat)', () => {
    const proven = JSON.parse(readFileSync(fileURLToPath(new URL('./fixtures/capacity-hook-limits.json', import.meta.url)), 'utf-8'))
    expect(hookLimits()).toEqual(proven)
  })
  it('never put a hook capacity above the limit of the full stage', () => {
    for (const [block, entry] of Object.entries(REGISTRY_BLOCKS)) {
      for (const [path, schema] of schemaNodes(entry.props)) {
        if (schema.hookMaxLength !== undefined) expect(schema.hookMaxLength, `${block} ${path}`).toBeLessThanOrEqual(schema.maxLength ?? -1)
        if (schema.hookMaxItems !== undefined) expect(schema.hookMaxItems, `${block} ${path}`).toBeLessThanOrEqual(schema.maxItems ?? -1)
      }
    }
  })
})

describe('the hook stage of the capacity episode', () => {
  it('draws every box that has a hook capacity at exactly that capacity, and a box that has none at its limit of the full stage', () => {
    const { timeline, capacity } = episode()
    for (const [block, limits] of Object.entries(hookLimits())) {
      const hookScenes = timeline.scenes.filter((s) => s.block === block && capacity.cases.find((c) => c.id === s.id)?.hook)
      expect(hookScenes.length, `${block} has a hook scene`).toBeGreaterThan(0)
      for (const scene of hookScenes) {
        for (const [path, n] of Object.entries(limits)) {
          if (path.endsWith(' (items)')) {
            const key = path.replace(' (items)', '')
            expect(key, `${block}: only an array of the props has hookMaxItems`).not.toMatch(/[.[]/)
            const items = scene.props[key] as unknown[]
            // the widest layout is a variant of the block; the narrow one has fewer items
            if (!scene.id.includes('most')) expect(items.length, `${scene.id} ${key}`).toBeLessThanOrEqual(n)
            else expect(items.length, `${scene.id} ${key}`).toBe(n)
          } else {
            const texts = drawnStrings(scene.props, [path], `${scene.id}.props`)
            if (n === 0) expect(texts, `${scene.id} ${path} cannot be shown under hook captions`).toEqual([])
            else for (const [at, text] of texts) expect(text.length, at).toBe(n)
          }
        }
      }
    }
  })
  it('is refused by the block checks one step above its capacity on a hook scene, and accepted on the full stage', () => {
    const { timeline } = episode()
    const check = (id: string, edit: (props: Record<string, unknown>) => void) => () => {
      const copy: Timeline = JSON.parse(JSON.stringify(timeline))
      const scene = copy.scenes.find((s) => s.id === id)
      if (!scene) throw new Error(`no scene ${id}`)
      edit(scene.props)
      checkBlocks(copy)
    }
    const statement = (props: Record<string, unknown>) => props.evidence as { statement: string }
    // the same 69 characters: over the hook capacity of 68, inside the full stage's 100
    expect(check('EvidenceCard.noimage.hook', (p) => (statement(p).statement = fill(69)))).toThrow(/props\.evidence\.statement: longer than 68 on a hook beat/)
    expect(check('EvidenceCard.noimage.full', (p) => (statement(p).statement = fill(69)))).not.toThrow()
    const another = (p: Record<string, unknown>) => (p.claims as unknown[]).push({ ...(p.claims as object[])[0], id: 'c-extra' })
    expect(check('ClaimBoard.mostclaims.hook', another)).toThrow(/props\.claims: more than 5 items on a hook beat/)
    expect(check('Meter.hook', (p) => (p.note = 'a note'))).toThrow(/props\.note: not allowed on a hook beat/)
    expect(check('Meter.full', (p) => (p.note = 'a note'))).not.toThrow()
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
