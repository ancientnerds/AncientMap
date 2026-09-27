import { describe, expect, it } from 'vitest'

import { METER_ROLL_FRAMES, buildState, claimStatusAt, meterAt } from '../src/state'
import type { Scene } from '../src/timeline'

const scene = (id: string, from: number, cues: Scene['cues']): Scene => ({ id, from, durationInFrames: 100, block: 'ListCard', props: {}, cues })

const STATE = buildState([
  scene('b01', 0, [
    { frame: 20, do: 'introduce', target: 'c1' },
    { frame: 50, do: 'meter', target: 'meter', value: [60, 40] },
  ]),
  scene('b02', 100, [
    { frame: 150, do: 'status', target: 'c1', value: 'weakened' },
    { frame: 120, do: 'introduce', target: 'c1' },
  ]),
  scene('b03', 200, [
    { frame: 250, do: 'status', target: 'c1', value: 'refuted' },
    { frame: 260, do: 'meter', target: 'meter', value: [90, 10] },
  ]),
])

describe('episode-wide cue state', () => {
  it('keeps the first introduce cue of a claim', () => {
    expect(STATE.introduced.get('c1')).toBe(20)
    expect(STATE.introduced.has('c2')).toBe(false)
  })
  it('gives a claim the latest status at or before a frame, whichever scene set it', () => {
    expect(claimStatusAt(STATE, 'c1', 'pending', 100)).toEqual({ status: 'pending', since: null })
    expect(claimStatusAt(STATE, 'c1', 'pending', 150)).toEqual({ status: 'weakened', since: 150 })
    expect(claimStatusAt(STATE, 'c1', 'pending', 999)).toEqual({ status: 'refuted', since: 250 })
  })
  it('rolls the meter from the start split through every move', () => {
    expect(meterAt(STATE, [50, 50], 10)).toEqual({ a: 50, since: null })
    expect(meterAt(STATE, [50, 50], 50 + METER_ROLL_FRAMES)).toEqual({ a: 60, since: 50 })
    const rolling = meterAt(STATE, [50, 50], 270)
    expect(rolling.since).toBe(260)
    expect(rolling.a).toBeGreaterThan(60)
    expect(rolling.a).toBeLessThan(90)
    expect(meterAt(STATE, [50, 50], 400).a).toBeCloseTo(90)
  })
})
