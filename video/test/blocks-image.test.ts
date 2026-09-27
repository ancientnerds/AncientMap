import { describe, expect, it } from 'vitest'

import { checkMapboxTopdown, pinsOf } from '../src/blocks/MapboxTopdown'
import { checkPhotoPlate, plateCamera } from '../src/blocks/PhotoPlate'
import type { Capture, Media } from '../src/blocks/types'

const image: Media = {
  id: 'm1',
  src: 'media/stone_person.jpg',
  license: 'CC BY-SA 4.0',
  attribution: 'Jane Doe',
  source_url: 'https://commons.wikimedia.org/wiki/File:Stone.jpg',
  depicts: 'the Stone of the Pregnant Woman with one person for scale',
  markers: [{ id: 'mk1', box: [0.625, 0.583, 0.075, 0.2], label: '1 PERSON' }],
}

const topdown: Capture = {
  id: 'td1',
  kind: 'mapbox_topdown',
  src: 'captures/td1.jpg',
  fps: null,
  duration_s: null,
  width: 2560,
  height: 1440,
  events: [
    { t: 0, name: 'pin', target: 'p2', label: 'Quarry', x: 1065, y: 1355, lat: 33.99917, lng: 36.20028 },
    { t: 0, name: 'pin', target: 'p1', label: 'Temple of Jupiter', x: 1496, y: 77, lat: 34.00667, lng: 36.20333 },
  ],
  credits: ['© Mapbox © Maxar'],
}

describe('PhotoPlate', () => {
  it('pushes in slowly, then flies onto the marker after its highlight cue', () => {
    const cues = [{ frame: 60, do: 'highlight' as const, target: 'mk1' }]
    expect(plateCamera(image, [1600, 1200], 'in', cues, 30, 300, 1920, 1080).zoom).toBeLessThan(1.02)
    const after = plateCamera(image, [1600, 1200], 'in', cues, 200, 300, 1920, 1080)
    expect(after.cx).toBeCloseTo(1060)
    expect(after.cy).toBeCloseTo(819.6, 0)
    expect(after.zoom).toBeGreaterThan(1.5)
  })
  it('refuses a marker box outside its image', () => {
    expect(checkPhotoPlate({ image: { ...image, markers: [{ id: 'mk1', box: [0.9, 0.5, 0.2, 0.1], label: '1 PERSON' }] } })).toEqual([
      'marker mk1 box [0.9,0.5,0.2,0.1] is not a box inside the image (fractions 0..1)',
    ])
    expect(checkPhotoPlate({ image })).toEqual([])
  })
})

describe('MapboxTopdown', () => {
  it('reads its pins from the capture events', () => {
    expect(pinsOf(topdown)).toEqual([
      { id: 'p2', label: 'Quarry', x: 1065, y: 1355, lat: 33.99917, lng: 36.20028 },
      { id: 'p1', label: 'Temple of Jupiter', x: 1496, y: 77, lat: 34.00667, lng: 36.20333 },
    ])
  })
  it('refuses a frame without pins, pins off the image and lines between unknown pins', () => {
    expect(checkMapboxTopdown({ map: topdown, lines: [{ from: 'p2', to: 'p1' }] })).toEqual([])
    expect(checkMapboxTopdown({ map: { ...topdown, events: [] } })).toEqual(['capture td1 has no pin events'])
    const off = { ...topdown, events: [{ ...topdown.events[0], x: 3000 }] }
    expect(checkMapboxTopdown({ map: off })).toEqual(['pin p2 lies outside the 2560x1440 image'])
    expect(checkMapboxTopdown({ map: topdown, lines: [{ from: 'p2', to: 'p9' }] })).toEqual(['line p2 -> p9 must join two different pins of the capture'])
  })
})
