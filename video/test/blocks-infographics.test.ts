import { describe, expect, it } from 'vitest'

import { type BarChartProps, barAxis, barFraction, basisLine as barBasis, checkBarChart, valueText } from '../src/blocks/BarChart'
import { checkDiagram, fitDiagram } from '../src/blocks/Diagram'
import { basisLine as scaleBasis, checkScaleDrawing, dimensionLabel, fitScale } from '../src/blocks/ScaleDrawing'
import { DOT, FILL, MIN_FRAMES, type ScaleZoomProps, checkScaleZoom, pullWindow, basisLine as zoomBasis, zoomScale } from '../src/blocks/ScaleZoom'
import { checkTimeline, labelAnchor } from '../src/blocks/Timeline'
import { checkUnitGrid, basisLine as gridBasis, gridLayout, groupStarts } from '../src/blocks/UnitGrid'

describe('ScaleDrawing', () => {
  const objects = [
    { id: 'o1', label: 'Stone', shape: 'block' as const, width: 20, height: 6, x: 0 },
    { id: 'o2', label: 'Person', shape: 'person' as const, width: 0.5, height: 1.75, x: 21.5 },
  ]
  it('fits the widest extent and the tallest object at one scale', () => {
    expect(fitScale(objects, 1100, 300)).toBeCloseTo(50)
  })
  it('labels upright shapes by height and the others by width x height', () => {
    expect(dimensionLabel(objects[1], 'm')).toBe('1.75 m')
    expect(dimensionLabel(objects[0], 'm')).toBe('20 × 6 m')
  })
  it('refuses objects without a size', () => {
    expect(checkScaleDrawing({ title: 't', unit: 'm', basis: 'bus 12 m', objects: [{ ...objects[0], width: 0 }, objects[1]] })).toEqual(['object o1 needs a positive width and height'])
  })
})

describe('UnitGrid', () => {
  const groups = [
    { id: 'a', count: 40, label: 'a', tone: 'accent' as const },
    { id: 'b', count: 10, label: 'b', tone: 'warn' as const },
  ]
  it('starts each group after the previous one filled, or on its show cue', () => {
    expect(groupStarts(groups, () => null)).toEqual([12, 38])
    expect(groupStarts(groups, (id) => (id === 'b' ? 100 : null))).toEqual([12, 100])
  })
  it('picks the largest cells, or the given columns', () => {
    expect(gridLayout(80, { x: 0, y: 0, w: 1100, h: 500 })).toEqual({ columns: 14, rows: 6, cell: 1100 / 14 })
    expect(gridLayout(80, { x: 0, y: 0, w: 1100, h: 500 }, 20).columns).toBe(20)
  })
  it('holds at most 400 cells', () => {
    expect(checkUnitGrid({ title: 't', basis: 'b', unitLabel: 'u', groups: [{ id: 'a', count: 401, label: 'a', tone: 'accent' }] })).toEqual(['401 cells; the grid holds at most 400'])
  })
})

describe('BarChart', () => {
  it('needs something to compare', () => {
    expect(checkBarChart({ title: 't', unit: 't', basis: 'b', bars: [{ id: 'x', label: 'x', value: 0 }, { id: 'y', label: 'y', value: 0 }] })).toEqual(['every bar is 0: nothing to compare'])
  })
  it('shows a range where sources differ and refuses an empty range', () => {
    const p: BarChartProps = { title: 't', unit: 't', basis: 'b', bars: [{ id: 'x', label: 'x', value: [1000, 1650] }, { id: 'y', label: 'y', value: 500 }] }
    expect(checkBarChart(p)).toEqual([])
    const axis = barAxis(p)
    expect(axis).toEqual({ lo: 0, hi: 1650 })
    expect(barFraction(axis, 1000)).toBeCloseTo(1000 / 1650)
    expect(valueText([1000, 1650], 't')).toBe('1,000–1,650 t')
    expect(valueText(12.5, 't')).toBe('12.5 t')
    // a bar bound to a case-file quantity shows exactly its value: 1.75 stays 1.75, not 1.8
    expect(valueText(1.75, 'm')).toBe('1.75 m')
    const empty: BarChartProps = { ...p, bars: [{ id: 'x', label: 'x', value: [1650, 1000] }, p.bars[1]] }
    expect(checkBarChart(empty)).toEqual(['bar x: range [1650, 1000] needs low < high'])
  })
  it('prints small values exactly, exponent form included, never rounded to another number', () => {
    expect(valueText(1.5e-7, 'm')).toBe('0.00000015 m')
    expect(valueText(0.0000015, 'm')).toBe('0.0000015 m')
    expect(valueText(1e-10, 'm')).toBe('0.0000000001 m')
  })
})

describe('ScaleZoom (owner decision 31: linear, never a log axis)', () => {
  const p: ScaleZoomProps = {
    title: 't',
    unit: 'km',
    basis: 'b',
    small: { id: 'q1', label: 'Earth', value: 12742 },
    large: { id: 'q2', label: 'Sun', value: 1392700 },
  }
  it('pulls back from the small quantity to the large one over the middle of the scene', () => {
    expect(pullWindow(300)).toEqual({ start: 75, end: 240 })
    expect(p.small.value * zoomScale(p, 1600, 0, 300)).toBeCloseTo(FILL * 1600)
    expect(p.large.value * zoomScale(p, 1600, 299, 300)).toBeCloseTo(FILL * 1600)
    // the small one ends as a dot: far below DOT pixels on the fitted scale
    expect(p.small.value * zoomScale(p, 1600, 299, 300)).toBeLessThan(DOT)
  })
  it('draws both quantities on one linear scale in every frame', () => {
    for (const frame of [0, 80, 120, 160, 200, 240, 299]) {
      const s = zoomScale(p, 1600, frame, 300)
      expect((p.small.value * s) / (p.large.value * s)).toBeCloseTo(p.small.value / p.large.value, 12)
    }
    // the visible extent grows linearly between the eased ends: halfway through the pull it is halfway between the two values
    const { start, end } = pullWindow(300)
    expect((FILL * 1600) / zoomScale(p, 1600, (start + end) / 2, 300)).toBeCloseTo((p.small.value + p.large.value) / 2, 3)
  })
  it('refuses a small value of 0, a large value not above it and a scene too short for the pull-back', () => {
    expect(checkScaleZoom(p, { fps: 60, durationInFrames: MIN_FRAMES })).toEqual([])
    expect(checkScaleZoom({ ...p, small: { ...p.small, value: 0 } }, { fps: 60, durationInFrames: 300 })).toEqual(['q1: the small value must be greater than 0'])
    expect(checkScaleZoom({ ...p, large: { ...p.large, value: 12742 } }, { fps: 60, durationInFrames: 300 })).toEqual(['q2: the large value 12742 must be greater than the small value 12742'])
    expect(checkScaleZoom(p, { fps: 60, durationInFrames: 180 })).toEqual([
      'a ScaleZoom scene needs at least 240 frames (the small quantity, the pull-back, a 1 s hold), got 180',
    ])
  })
})

describe('basis lines (owner rule: comparisons state their basis)', () => {
  it('print the basis verbatim on screen', () => {
    const basis = 'block 20.5 m x 4 m, DAI 2014; person 1.75 m'
    expect(scaleBasis({ title: 't', unit: 'm', basis, objects: [] })).toBe(`To scale. Basis: ${basis}`)
    expect(gridBasis({ title: 't', basis, unitLabel: 'one city bus', groups: [] })).toBe(`1 square = one city bus. Basis: ${basis}`)
    expect(barBasis({ title: 't', unit: 't', basis, bars: [] })).toBe(`Basis: ${basis}`)
    const q = { id: 'q', label: 'q', value: 1 }
    expect(zoomBasis({ title: 't', unit: 'km', basis, small: q, large: { ...q, id: 'r', value: 1000 } })).toBe(`To scale, linear. Basis: ${basis}`)
  })
})

describe('Timeline', () => {
  it('aligns labels near the ends to the edge', () => {
    expect(labelAnchor(0.05).textAlign).toBe('left')
    expect(labelAnchor(0.5).textAlign).toBe('center')
    expect(labelAnchor(0.95).textAlign).toBe('right')
  })
  it('refuses an empty range, events outside it and year 0', () => {
    expect(checkTimeline({ title: 't', from: 100, to: 100, events: [] })).toEqual(['timeline range 100..100 is empty'])
    expect(checkTimeline({ title: 't', from: -100, to: 100, events: [{ id: 'e', year: 0, label: 'x', tone: 'muted' }] })).toEqual(['event e: year 0 does not exist'])
    expect(checkTimeline({ title: 't', from: -100, to: 100, events: [{ id: 'e', year: 300, label: 'x', tone: 'muted' }] })).toEqual(['event e (300) lies outside -100..100'])
  })
})

describe('Diagram', () => {
  it('centres the user space in the drawing area at one scale', () => {
    expect(fitDiagram(100, 50, { x: 0, y: 0, w: 1000, h: 1000 })).toEqual({ s: 10, ox: 0, oy: 250 })
  })
  it('needs the geometry of each element type', () => {
    expect(checkDiagram({ title: 't', width: 10, height: 10, elements: [{ id: 'd2', type: 'circle', tone: 'accent', cx: 1, cy: 1 }] })).toEqual(['element d2 (circle) needs "r"'])
  })
})
