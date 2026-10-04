import { describe, expect, it } from 'vitest'

import { imageSize } from '../src/context'
import { Registry } from '../src/layout/LayoutBox'
import { VIOLATION_TYPE, violationLine } from '../src/layout/LayoutGuard'

describe('LayoutBox registry (lint mode)', () => {
  it('keeps the latest box per id and tracks clipped text', () => {
    const registry = new Registry(true)
    registry.set({ id: 'b01:title', kind: 'text', rect: { x: 0, y: 0, w: 10, h: 10 }, allow: [] }, true)
    registry.set({ id: 'b01:title', kind: 'text', rect: { x: 5, y: 5, w: 10, h: 10 }, allow: [] }, false)
    expect(registry.boxes.get('b01:title')?.rect.x).toBe(5)
    expect(registry.overflow.size).toBe(0)
    registry.set({ id: 'b01:quote', kind: 'text', rect: { x: 0, y: 0, w: 1, h: 1 }, allow: [] }, true)
    expect([...registry.overflow]).toEqual(['b01:quote'])
    registry.remove('b01:quote')
    expect(registry.boxes.has('b01:quote') || registry.overflow.has('b01:quote')).toBe(false)
  })
  it('refuses a box outside lint mode and keeps nothing', () => {
    const registry = new Registry(false)
    expect(() => registry.set({ id: 'b01:title', kind: 'text', rect: { x: 0, y: 0, w: 10, h: 10 }, allow: [] }, true)).toThrow(
      'LayoutBox b01:title was measured outside lint mode',
    )
    expect(registry.boxes.size + registry.overflow.size).toBe(0)
  })
})

describe('LayoutGuard lines', () => {
  it('writes one JSON line per violation: {type, frame, a, b, reason}', () => {
    expect(JSON.parse(violationLine(123, { a: 'captions', b: 'b01:lt', reason: 'overlap' }))).toEqual({
      type: VIOLATION_TYPE,
      frame: 123,
      a: 'captions',
      b: 'b01:lt',
      reason: 'overlap',
    })
    expect(violationLine(7, { a: 'b03:statement', b: null, reason: 'overflow' })).toBe(
      '{"type":"layout-violation","frame":7,"a":"b03:statement","b":null,"reason":"overflow"}',
    )
  })
})

describe('imageSize', () => {
  it('returns the measured size and refuses an unmeasured image', () => {
    expect(imageSize({ 'media/a.jpg': [1600, 1200] }, 'media/a.jpg')).toEqual([1600, 1200])
    expect(() => imageSize({}, 'media/b.jpg')).toThrow(/media\/b.jpg was not measured/)
  })
})
