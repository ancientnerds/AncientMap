import { describe, expect, it } from 'vitest'

import { checkGlobeShot, globeDots, globePins, pinAt } from '../src/blocks/GlobeShot'
import { checkMapboxFlyover } from '../src/blocks/MapboxFlyover'
import { FOLLOW_LEAD_S, checkPlatformClip, followKeys, platformCamera } from '../src/blocks/PlatformClip'
import type { Capture } from '../src/blocks/types'

const capture = (over: Partial<Capture>): Capture => ({
  id: 'pf1',
  kind: 'platform',
  src: 'captures/pf1.mp4',
  fps: 60,
  duration_s: 10,
  width: 2880,
  height: 1620,
  events: [],
  credits: ['© Mapbox © OpenStreetMap © Maxar'],
  ...over,
})
const ctx = { fps: 60, durationInFrames: 180 }

describe('PlatformClip camera', () => {
  it('follows the events with a position, easing in before each', () => {
    const events = [{ t: 0.4, name: 'pause_rotation' }, { t: 1, name: 'search', x: 500, y: 700 }, { t: 3, name: 'click_result', x: 400, y: 1800 }]
    expect(followKeys(events, 1.6, 2880, 1620)).toEqual([
      { t: 0, cx: 1440, cy: 810, zoom: 1 },
      { t: 1 - FOLLOW_LEAD_S, cx: 1440, cy: 810, zoom: 1 },
      { t: 1, cx: 500, cy: 700, zoom: 1.6 },
      { t: 3 - FOLLOW_LEAD_S, cx: 500, cy: 700, zoom: 1.6 },
      { t: 3, cx: 400, cy: 1800, zoom: 1.6 },
    ])
  })
  it('interpolates keys on the capture clock and shows the whole frame without keys', () => {
    expect(platformCamera(undefined, 2880, 1620, 3)).toEqual({ cx: 1440, cy: 810, zoom: 1 })
    const keys = [
      { t: 1, cx: 1440, cy: 810, zoom: 1 },
      { t: 2, cx: 600, cy: 240, zoom: 2 },
    ]
    expect(platformCamera(keys, 2880, 1620, 0.5)).toEqual({ cx: 1440, cy: 810, zoom: 1 })
    expect(platformCamera(keys, 2880, 1620, 1.5).zoom).toBeCloseTo(Math.SQRT2)
    expect(platformCamera(keys, 2880, 1620, 2.5)).toEqual({ cx: 600, cy: 240, zoom: 2 })
  })
  it('refuses a camera and follow together, keys outside the capture and keys out of order', () => {
    const clip = capture({})
    expect(checkPlatformClip({ clip, camera: [{ t: 0, cx: 1, cy: 1, zoom: 1 }], follow: 1.5 }, ctx)).toEqual(['camera and follow exclude each other'])
    expect(checkPlatformClip({ clip, camera: [{ t: 0, cx: 3000, cy: 1, zoom: 1 }] }, ctx)).toEqual(['camera key at 0 s points outside the 2880x1620 capture'])
    expect(checkPlatformClip({ clip, camera: [{ t: 2, cx: 1, cy: 1, zoom: 1 }, { t: 1, cx: 1, cy: 1, zoom: 1 }] }, ctx)).toEqual(['camera keys must be in increasing time order'])
  })
  it('never zooms past the pixels of the capture (sharp up to width / 1920)', () => {
    const clip = capture({})
    expect(checkPlatformClip({ clip, follow: 1.5 }, ctx)).toEqual([])
    expect(checkPlatformClip({ clip, follow: 1.6 }, ctx)).toEqual(['zoom 1.6 upscales the 2880x1620 capture (sharp up to 1.50)'])
    expect(checkPlatformClip({ clip, camera: [{ t: 0, cx: 1440, cy: 810, zoom: 2 }] }, ctx)).toEqual(['zoom 2 upscales the 2880x1620 capture (sharp up to 1.50)'])
  })
})

describe('GlobeShot and MapboxFlyover', () => {
  const track = (n: number, at: [number, number] | null = [960, 540]): ([number, number] | null)[] => Array.from({ length: n }, () => at)
  it('reads pins from the labelled place events and dots from the unlabelled ones', () => {
    const globe = capture({
      kind: 'globe',
      credits: [],
      duration_s: 4,
      events: [
        { t: 0, name: 'gpu', label: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU)' },
        { t: 0, name: 'rotate' },
        { t: 3, name: 'place', target: 'p2', x: 10, y: 10, track: track(60, [10, 10]) },
        { t: 3.5, name: 'arrive', x: 960, y: 540 },
        { t: 3.5, name: 'place', target: 'p1', label: 'Baalbek', x: 960, y: 540, track: track(30) },
      ],
    })
    expect(globePins(globe)).toEqual([{ id: 'p1', frame: 210, x: 960, y: 540, label: 'Baalbek', track: track(30) }])
    expect(globeDots(globe)).toEqual([{ id: 'p2', frame: 180, track: track(60, [10, 10]) }])
    expect(checkGlobeShot({ clip: globe }, ctx)).toEqual([])
  })
  it('moves a pin along its track, hides it on null and never shows it before its event frame', () => {
    const pin = { frame: 100, track: [[10, 20], null, [14, 22]] as ([number, number] | null)[] }
    expect(pinAt(pin, 99)).toBeNull()
    expect(pinAt(pin, 100)).toEqual({ x: 10, y: 20 })
    expect(pinAt(pin, 101)).toBeNull()
    expect(pinAt(pin, 102)).toEqual({ x: 14, y: 22 })
  })
  it('refuses a place event without a track that runs to the end of the take', () => {
    const place = { t: 3.5, name: 'place', target: 'p1', label: 'Baalbek', x: 960, y: 540 }
    const short = capture({ kind: 'globe', credits: [], duration_s: 4, events: [{ ...place, track: track(12) }] })
    expect(checkGlobeShot({ clip: short }, ctx)).toEqual(['place p1: the track holds 12 points, the take has 30 frames from the event on'])
    const none = capture({ kind: 'globe', credits: [], duration_s: 4, events: [place] })
    expect(checkGlobeShot({ clip: none }, ctx)).toEqual(['place p1 has no track (re-capture the take)'])
  })
  it('keeps Mapbox takes out of GlobeShot and our globe out of MapboxFlyover', () => {
    const mapboxTake = capture({ id: 'm1', kind: 'globe', width: 1920, height: 1080 })
    expect(checkGlobeShot({ clip: mapboxTake }, ctx)).toEqual(['capture m1 carries map credits: a Mapbox take belongs in MapboxFlyover'])
    expect(checkMapboxFlyover({ clip: { ...mapboxTake, credits: [] } }, ctx)).toEqual(['capture m1 has no Mapbox credit: our vector globe belongs in GlobeShot'])
    expect(checkMapboxFlyover({ clip: mapboxTake }, ctx)).toEqual([])
  })
})
