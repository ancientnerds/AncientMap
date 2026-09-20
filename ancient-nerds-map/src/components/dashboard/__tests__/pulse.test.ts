import { describe, expect, it } from 'vitest'

import { type HourStack, stackHour } from '../Pulse'
import type { HourBucket } from '../types'

const hour = (over: Partial<HourBucket>): HourBucket => ({
  hour: '2026-09-19T12:00:00+00:00',
  sessions: 10,
  human: 4,
  ai: 0,
  ...over,
})

/** The strip's viewBox height. STRIP_HEIGHT is module-private, so the tests
 *  pass it explicitly and pin the default with the same number. */
const H = 20

describe('Pulse stackHour', () => {
  it('sits the human segment on the baseline and the rest directly on top', () => {
    const s: HourStack = stackHour(hour({ sessions: 10, human: 4 }), 10, H)
    expect(s.humanY + s.humanH).toBe(H)
    expect(s.restY + s.restH).toBe(s.humanY)
    expect(s.humanH).toBe(8)
    expect(s.restH).toBe(12)
  })

  it('uses the same height when none is given', () => {
    expect(stackHour(hour({ sessions: 10, human: 4 }), 10)).toEqual(
      stackHour(hour({ sessions: 10, human: 4 }), 10, H)
    )
  })

  it('draws an all-human hour with no second segment', () => {
    const s = stackHour(hour({ sessions: 6, human: 6 }), 6, H)
    expect(s.restH).toBe(0)
    expect(s.restY).toBe(s.humanY)
    expect(s.humanH).toBe(H)
  })

  it('survives an empty strip instead of dividing by zero', () => {
    // Every bucket of an empty window is zero, so `max` is zero too. Without
    // the Math.max(max, 1) floor every field here would be NaN and the whole
    // svg would vanish — the empty screenshot pass is what catches that.
    const s = stackHour(hour({ sessions: 0, human: 0 }), 0, H)
    expect(Object.values(s).every(Number.isFinite)).toBe(true)
    expect(s).toEqual({ humanY: H, humanH: 0, restY: H, restH: 0 })
  })
})
