import { describe, expect, it } from 'vitest'

import { bootIn, borderTrace, crtOpen, digitRoll, progress, ringPulse, stampSlam, sweep, typeOn } from '../src/motion'

describe('NERV motion is a pure function of the frame', () => {
  it('progress clamps to 0..1', () => {
    expect(progress(-5, 0, 10)).toBe(0)
    expect(progress(10, 0, 10)).toBe(1)
    expect(progress(99, 0, 10)).toBe(1)
  })
  it('crt-open stays a line for 40 % of its 24 frames, then opens fully', () => {
    expect(crtOpen(0, 10)).toEqual({ opacity: 0 })
    expect(String(crtOpen(15, 10).transform)).toBe('scaleY(0.002)')
    expect(crtOpen(40, 10)).toEqual({ opacity: 1, transform: 'scaleY(1)', filter: 'brightness(1)' })
  })
  it('boot-in fades, rises and settles its brightness', () => {
    expect(bootIn(0, 0, 30).opacity).toBe(0)
    expect(bootIn(30, 0, 30)).toEqual({ opacity: 1, transform: 'translateY(0px)', filter: 'brightness(1)' })
    expect(bootIn(30, 0, 30, 'translateX(-50%)').transform).toBe('translateX(-50%) translateY(0px)')
  })
  it('border-trace draws the outline in', () => {
    expect(borderTrace(0, 0, 20, 400)).toBe(400)
    expect(borderTrace(20, 0, 20, 400)).toBe(0)
  })
  it('type-on reveals characters at the set rate', () => {
    expect(typeOn('EVIDENCE', 4, 5)).toBe('')
    expect(typeOn('EVIDENCE', 5, 5, 2)).toBe('EV')
    expect(typeOn('EVIDENCE', 50, 5, 2)).toBe('EVIDENCE')
  })
  it('digit-roll lands exactly on the target', () => {
    expect(digitRoll(0, 80, 0, 0, 30)).toBe(0)
    expect(digitRoll(0, 80, 30, 0, 30)).toBe(80)
    expect(digitRoll(50, 15, 100, 0, 30)).toBe(15)
  })
  it('the stamp settles at scale 1', () => {
    expect(stampSlam(0, 10, 60)).toEqual({ opacity: 0 })
    const settled = String(stampSlam(200, 10, 60).transform)
    expect(settled.startsWith('rotate(-6deg) scale(')).toBe(true)
    expect(Number(settled.slice('rotate(-6deg) scale('.length, -1))).toBeCloseTo(1, 6)
  })
  it('ring-pulse repeats every period and fades out, never blinks', () => {
    expect(ringPulse(10, 10, 60)).toEqual(ringPulse(70, 10, 60))
    expect(ringPulse(10, 10, 60)).toEqual({ scale: 0.8, opacity: 0.6 })
    expect(ringPulse(40, 10, 60).opacity).toBeCloseTo(0.3)
  })
  it('sweep crosses once', () => {
    expect(sweep(0, 0, 40)).toBe(0)
    expect(sweep(40, 0, 40)).toBe(1)
  })
})
