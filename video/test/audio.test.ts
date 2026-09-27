import { describe, expect, it } from 'vitest'

import { dbToGain, duckAmount, musicVolume, narrationSpans } from '../src/audio'

const music = { src: 'music/bed.wav', gainDb: -8, duck: { underNarrationDb: -12, attackFrames: 6, releaseFrames: 24 } }

describe('narrationSpans', () => {
  it('turns clip starts and measured seconds into frame spans (rounded up)', () => {
    expect(narrationSpans([{ src: 'voice/b01.mp3', from: 0 }, { src: 'voice/b02.mp3', from: 300 }], [2.01, 3], 60)).toEqual([
      { from: 0, to: 121 },
      { from: 300, to: 480 },
    ])
  })
  it('refuses a missing or zero duration', () => {
    expect(() => narrationSpans([{ src: 'voice/b01.mp3', from: 0 }], [0], 60)).toThrow(/has no duration/)
    expect(() => narrationSpans([{ src: 'voice/b01.mp3', from: 0 }], [], 60)).toThrow(/1 clips but 0 durations/)
  })
})

describe('ducking', () => {
  const spans = [{ from: 100, to: 200 }]
  it('ramps down over attackFrames, holds, then releases over releaseFrames', () => {
    expect(duckAmount(50, spans, 6, 24)).toBe(0)
    expect(duckAmount(97, spans, 6, 24)).toBeCloseTo(0.5)
    expect(duckAmount(150, spans, 6, 24)).toBe(1)
    expect(duckAmount(211, spans, 6, 24)).toBeCloseTo(0.5)
    expect(duckAmount(224, spans, 6, 24)).toBe(0)
  })
  it('sits at gainDb in pauses and gainDb + underNarrationDb under speech', () => {
    expect(dbToGain(-20)).toBeCloseTo(0.1)
    expect(musicVolume(0, music, spans)).toBeCloseTo(dbToGain(-8))
    expect(musicVolume(150, music, spans)).toBeCloseTo(dbToGain(-20))
  })
})
