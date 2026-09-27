import { describe, expect, it } from 'vitest'

import { type Box, contains, findViolations, overlapArea } from '../src/layout/geometry'
import { SAFE, ZONES, stageFor } from '../src/layout/zones'

const text = (id: string, x: number, y: number, w: number, h: number, allow: string[] = []): Box => ({ id, kind: 'text', rect: { x, y, w, h }, allow })
const mark = (id: string, x: number, y: number, w: number, h: number, allow: string[] = []): Box => ({ id, kind: 'mark', rect: { x, y, w, h }, allow })

describe('overlapArea / contains', () => {
  it('measures the shared area and ignores touching edges', () => {
    expect(overlapArea({ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 5, w: 10, h: 10 })).toBe(25)
    expect(overlapArea({ x: 0, y: 0, w: 10, h: 10 }, { x: 10, y: 0, w: 10, h: 10 })).toBe(0)
  })
  it('contains with half a pixel of tolerance', () => {
    expect(contains(SAFE, { x: 95.6, y: 54, w: 10, h: 10 })).toBe(true)
    expect(contains(SAFE, { x: 90, y: 54, w: 10, h: 10 })).toBe(false)
  })
})

describe('zones', () => {
  it('keeps every overlay zone apart and inside the safe area', () => {
    const boxes = Object.entries(ZONES)
      .filter(([name]) => name !== 'stage' && name !== 'stageHook')
      .map(([name, z]) => text(name, z.x, z.y, z.w, z.h))
    expect(findViolations(boxes)).toEqual([])
  })
  it('keeps the hook stage above the captions', () => {
    const s = stageFor(true)
    expect(s.y + s.h).toBeLessThanOrEqual(ZONES.caption.y)
    expect(stageFor(false)).toEqual(ZONES.stage)
  })
})

describe('findViolations', () => {
  it('reports two overlapping text boxes once, with both ids', () => {
    expect(findViolations([text('a', 200, 200, 300, 60), text('b', 400, 220, 300, 60)])).toEqual([{ a: 'a', b: 'b', reason: 'overlap' }])
  })
  it('lets a marker label touch its own ring but not a foreign ring', () => {
    const ring = mark('ring1', 500, 500, 100, 100, ['label1'])
    expect(findViolations([ring, text('label1', 520, 560, 200, 40, ['ring1'])])).toEqual([])
    expect(findViolations([ring, text('label2', 520, 560, 200, 40)])).toEqual([{ a: 'ring1', b: 'label2', reason: 'overlap' }])
  })
  it('flags text outside the safe area and text under the player controls', () => {
    expect(findViolations([text('edge', 20, 300, 200, 40)])).toEqual([{ a: 'edge', b: null, reason: 'outside-safe' }])
    expect(findViolations([text('low', 300, 950, 200, 40)])).toEqual([{ a: 'low', b: null, reason: 'controls' }])
  })
  it('flags a marker that leaves the frame, never two markers touching', () => {
    expect(findViolations([mark('m', 1880, 500, 80, 80)])).toEqual([{ a: 'm', b: null, reason: 'offscreen' }])
    expect(findViolations([mark('m1', 500, 500, 80, 80), mark('m2', 520, 520, 80, 80)])).toEqual([])
  })
  it('flags a marker under the player controls (nothing important in the control zone)', () => {
    expect(findViolations([mark('m', 500, 980, 60, 60)])).toEqual([{ a: 'm', b: null, reason: 'controls' }])
  })
  it('reports clipped text boxes as overflow', () => {
    expect(findViolations([], ['b03:statement'])).toEqual([{ a: 'b03:statement', b: null, reason: 'overflow' }])
  })
})
