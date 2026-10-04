import { describe, expect, it } from 'vitest'

import { type MapboxTopdownProps, checkMapboxTopdown, pinsOf, topdownFrame } from '../src/blocks/MapboxTopdown'
import { checkPhotoPlate, plateCamera } from '../src/blocks/PhotoPlate'
import type { Capture, Media } from '../src/blocks/types'
import type { SceneCue } from '../src/cues'
import { findViolations } from '../src/layout/geometry'
import { rectToScreen } from '../src/layout/transform'

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

/** The smoke timeline's Baalbek capture (scene s4): both pins inside the capture's pin band. */
const baalbek: Capture = {
  ...topdown,
  events: [
    { t: 0, name: 'pin', target: 'p2', label: 'Quarry', x: 1065.3, y: 1100.6, lat: 33.99917, lng: 36.20028 },
    { t: 0, name: 'pin', target: 'p1', label: 'Temple', x: 1496.2, y: 377.5, lat: 34.00667, lng: 36.20333 },
  ],
}

/** The layout lint's verdict on the pin rings ImageLayer registers at `frame` (those whose appear frame has come). */
function ringViolations(p: MapboxTopdownProps, cues: readonly SceneCue[], frame: number, duration: number) {
  const { view, marks } = topdownFrame(p, cues, frame, duration, 1920, 1080)
  return findViolations(marks.filter((m) => frame >= m.appear).map((m) => ({ id: m.id, kind: 'mark' as const, rect: rectToScreen(view, m.box), allow: [] })))
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
  it('flies from one highlighted marker to the next without jumping back to the whole photo', () => {
    const two: Pick<Media, 'markers'> = {
      markers: [
        { id: 'a', box: [0.1, 0.1, 0.05, 0.1], label: 'A' },
        { id: 'b', box: [0.8, 0.7, 0.05, 0.1], label: 'B' },
      ],
    }
    // The second highlight fires once the first flight has landed (150), and in the middle of it (70).
    for (const second of [150, 70]) {
      const cues = [
        { frame: 60, do: 'highlight' as const, target: 'a' },
        { frame: second, do: 'highlight' as const, target: 'b' },
      ]
      const cam = (f: number) => plateCamera(two, [1600, 1200], 'in', cues, f, 300, 1920, 1080)
      // A flight's fastest frame here moves the centre about 91 px and the zoom by 10 %;
      // the jump back to the Ken Burns path moved it 600 px and the zoom 3.2x in one frame.
      for (let f = 1; f < 300; f++) {
        const [p, q] = [cam(f - 1), cam(f)]
        expect(Math.abs(q.cx - p.cx)).toBeLessThan(100)
        expect(Math.abs(q.cy - p.cy)).toBeLessThan(100)
        expect(Math.abs(Math.log(q.zoom / p.zoom))).toBeLessThan(0.12)
      }
      const end = cam(299)
      expect([end.cx, end.cy, end.zoom]).toEqual([1320, 900, expect.closeTo(3.375)])
    }
    const held = [{ frame: 60, do: 'highlight' as const, target: 'a' }, { frame: 150, do: 'highlight' as const, target: 'b' }]
    const at = (f: number) => plateCamera(two, [1600, 1200], 'in', held, f, 300, 1920, 1080)
    expect(at(150).cx).toBeCloseTo(at(149).cx)
    expect(at(150).cy).toBeCloseTo(at(149).cy)
    expect(at(150).zoom).toBeCloseTo(at(149).zoom)
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
  it('shows every pin and the distance line until a highlight, then only the focused pin', () => {
    const cues = [{ frame: 50, do: 'highlight' as const, target: 'p1' }]
    const before = topdownFrame({ map: baalbek, lines: [{ from: 'p2', to: 'p1' }] }, cues, 49, 90, 1920, 1080)
    expect(before.marks.map((m) => [m.id, m.appear, m.focused])).toEqual([
      ['p2', 8, false],
      ['p1', 18, false],
    ])
    expect(before.lines.map((l) => [l.id, l.appear])).toEqual([['p2-p1', 38]])
    const after = topdownFrame({ map: baalbek, lines: [{ from: 'p2', to: 'p1' }] }, cues, 50, 90, 1920, 1080)
    expect(after.marks.map((m) => [m.id, m.appear, m.focused])).toEqual([['p1', 18, true]])
    expect(after.lines).toEqual([])
  })
  it('keeps every pin it registers inside the frame while it flies onto a highlighted pin and holds', () => {
    // The smoke timeline's Baalbek frame: a close-up of either pin puts the other one below the frame.
    for (const target of ['p1', 'p2']) {
      const cues = [{ frame: 20, do: 'highlight' as const, target }]
      for (let f = 0; f < 90; f++) expect(ringViolations({ map: baalbek, lines: [{ from: 'p2', to: 'p1' }] }, cues, f, 90)).toEqual([])
    }
  })
  it('flies from one highlighted pin to the next without a jump and brings that pin up on arrival', () => {
    const p = { map: baalbek, lines: [{ from: 'p2', to: 'p1' }] }
    const cues = [
      { frame: 20, do: 'highlight' as const, target: 'p1' },
      { frame: 60, do: 'highlight' as const, target: 'p2' },
    ]
    const held = topdownFrame(p, cues, 59, 150, 1920, 1080).view
    const next = topdownFrame(p, cues, 60, 150, 1920, 1080).view
    expect(next.scale).toBeCloseTo(held.scale)
    expect(next.tx).toBeCloseTo(held.tx)
    expect(next.ty).toBeCloseTo(held.ty)
    expect(topdownFrame(p, cues, 60, 150, 1920, 1080).marks.map((m) => [m.id, m.appear, m.focused])).toEqual([['p2', 96, true]])
    for (let f = 0; f < 150; f++) expect(ringViolations(p, cues, f, 150)).toEqual([])
  })
  it('keeps a pin anywhere in the capture pin band inside the frame through its close-up', () => {
    // capture/mapbox.py places every pin in x 0.10..0.90, y 0.15..0.80 of the capture.
    const corners = [
      [0.1, 0.15],
      [0.9, 0.15],
      [0.1, 0.8],
      [0.9, 0.8],
    ]
    const map: Capture = {
      ...baalbek,
      events: corners.map(([fx, fy], i) => ({ t: 0, name: 'pin', target: `c${i}`, label: `CORNER ${i}`, x: fx * 2560, y: fy * 1440, lat: 34, lng: 36 + i / 1000 })),
    }
    for (let i = 0; i < corners.length; i++) {
      const cues = [{ frame: 50, do: 'highlight' as const, target: `c${i}` }]
      for (let f = 0; f < 120; f++) expect(ringViolations({ map }, cues, f, 120)).toEqual([])
    }
  })
})
