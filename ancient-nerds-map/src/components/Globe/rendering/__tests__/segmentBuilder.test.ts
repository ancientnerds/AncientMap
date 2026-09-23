/**
 * The pure half of the vector layers: the feature walker, the Antarctic filter and the
 * Float32Array fill the worker runs. The positions must be bit-identical to the old
 * main-thread builder (latLngTo3DRef per endpoint, pushed into a number[] and converted by
 * Float32BufferAttribute), because the basemap sphere uses the same formula (A5).
 */

import { describe, expect, it } from 'vitest'

import {
  buildSegmentPositions,
  extractLineLabels,
  isArtificialAntarcticBoundary,
  latLngTo3DArray,
  processLayerRequest,
  type LayerFeature,
} from '../segmentBuilder'

/** The formula Globe.tsx's latLngTo3DRef used, evaluated in the same order. */
function legacyPoint(lat: number, lng: number, r: number): [number, number, number] {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return [-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)]
}

/** The old loaders' walker, verbatim in behaviour: explicit segment pairs, Antarctic filter. */
function legacyPositions(features: LayerFeature[], r: number): Float32Array {
  const out: number[] = []
  for (const feature of features) {
    const g = feature.geometry
    let sets: number[][][] = []
    if (g.type === 'LineString') sets = [g.coordinates as number[][]]
    else if (g.type === 'MultiLineString' || g.type === 'Polygon') sets = g.coordinates as number[][][]
    else if (g.type === 'MultiPolygon') sets = (g.coordinates as number[][][][]).flat()
    for (const coords of sets) {
      if (coords.length <= 1) continue
      for (let i = 0; i < coords.length - 1; i++) {
        const a = coords[i]
        const b = coords[i + 1]
        if (isArtificialAntarcticBoundary(a, b)) continue
        out.push(...legacyPoint(a[1], a[0], r), ...legacyPoint(b[1], b[0], r))
      }
    }
  }
  return new Float32Array(out)
}

const FEATURES: LayerFeature[] = [
  { geometry: { type: 'LineString', coordinates: [[10, 50], [10.5, 50.2], [11, 50]] } },
  { geometry: { type: 'MultiLineString', coordinates: [[[-70.1234, -33.5], [-70.2, -33.6]], [[5, 5]], [[120.5, 10.25], [121, 11], [122, 11.5]]] } },
  { geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]], [[0.2, 0.2], [0.3, 0.2], [0.2, 0.2]]] } },
  { geometry: { type: 'MultiPolygon', coordinates: [[[[170, -40], [171, -41], [170, -40]]], [[[-179.5, 65], [-178, 66], [-179.5, 65]]]] } },
  // One artificial Antarctic segment between two real ones: only the middle one is dropped.
  { geometry: { type: 'LineString', coordinates: [[175, -65], [180, -70], [180, -80], [179, -81]] } },
]

describe('buildSegmentPositions', () => {
  it('returns one Float32Array per radius, bit-identical to the legacy builder', () => {
    const [front, back] = buildSegmentPositions(FEATURES, [1.002, 1.001])
    expect(front).toBeInstanceOf(Float32Array)
    expect(back).toBeInstanceOf(Float32Array)
    expect(Array.from(front)).toEqual(Array.from(legacyPositions(FEATURES, 1.002)))
    expect(Array.from(back)).toEqual(Array.from(legacyPositions(FEATURES, 1.001)))
  })

  it('drops the artificial Antarctic segment and keeps the real ones', () => {
    const line: LayerFeature[] = [{ geometry: { type: 'LineString', coordinates: [[175, -65], [180, -70], [180, -80], [179, -81]] } }]
    const [positions] = buildSegmentPositions(line, [1])
    // 3 segments in the line, one artificial: 2 segments x 2 endpoints x 3 floats
    expect(positions.length).toBe(12)
    const expected = new Float32Array([
      ...legacyPoint(-65, 175, 1), ...legacyPoint(-70, 180, 1),
      ...legacyPoint(-80, 180, 1), ...legacyPoint(-81, 179, 1),
    ])
    expect(Array.from(positions)).toEqual(Array.from(expected))
  })

  it('writes nothing for single-point lines and unknown geometry types', () => {
    const [positions] = buildSegmentPositions([
      { geometry: { type: 'LineString', coordinates: [[1, 1]] } },
      { geometry: { type: 'Point', coordinates: [1, 1] } },
    ], [1.002])
    expect(positions.length).toBe(0)
  })

  it('shares the one coordinate formula with the other loaders', () => {
    expect(latLngTo3DArray(51, 10, 1.002)).toEqual(legacyPoint(51, 10, 1.002))
  })
})

describe('isArtificialAntarcticBoundary', () => {
  it('flags long vertical segments at round longitudes south of -60 and pole connectors', () => {
    expect(isArtificialAntarcticBoundary([180, -70], [180, -80])).toBe(true)
    expect(isArtificialAntarcticBoundary([-90.2, -65], [-90.1, -75])).toBe(true)
    expect(isArtificialAntarcticBoundary([10, -89.9], [40, -89.8])).toBe(true)
    expect(isArtificialAntarcticBoundary([180, -70], [180, -71])).toBe(false)
    expect(isArtificialAntarcticBoundary([180, 10], [180, 20])).toBe(false)
    expect(isArtificialAntarcticBoundary([45, -70], [45, -80])).toBe(false)
  })
})

describe('extractLineLabels', () => {
  it('names each feature at the centroid of the coordinates the old label code averaged', () => {
    const labels = extractLineLabels([
      { properties: { name: 'Line', scalerank: 3 }, geometry: { type: 'LineString', coordinates: [[0, 0], [2, 4]] } },
      { properties: { NAME: 'Multi', SCALERANK: 5 }, geometry: { type: 'MultiLineString', coordinates: [[[0, 0], [1, 1]], [[2, 2]]] } },
      { properties: { name: 'Poly' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [3, 0], [0, 3]], [[9, 9], [9, 9]]] } },
      { properties: { name: 'MultiPoly' }, geometry: { type: 'MultiPolygon', coordinates: [[[[0, 0], [2, 0]]], [[[4, 0], [6, 0]]]] } },
      { properties: {}, geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] } },
      { properties: { name: 'Empty' }, geometry: { type: 'LineString', coordinates: [] } },
    ])
    expect(labels).toEqual([
      { name: 'Line', lat: 2, lng: 1, rank: 3 },
      { name: 'Multi', lat: 1, lng: 1, rank: 5 },
      { name: 'Poly', lat: 1, lng: 1, rank: 99 },
      { name: 'MultiPoly', lat: 0, lng: 3, rank: 99 },
    ])
  })
})

describe('processLayerRequest', () => {
  it('decodes the transferred bytes, builds every radius and lists the transferable buffers', () => {
    const fc = { type: 'FeatureCollection', features: [{ properties: { name: 'R' }, geometry: { type: 'LineString', coordinates: [[1, 2], [3, 4]] } }] }
    const buffer = new TextEncoder().encode(JSON.stringify(fc)).buffer as ArrayBuffer
    const { response, transfer } = processLayerRequest({ id: 7, buffer, radii: [1.002, 1.001], withLabels: true })
    if ('error' in response) throw new Error(response.error)
    expect(response.id).toBe(7)
    expect(response.positions).toHaveLength(2)
    expect(response.labels).toEqual([{ name: 'R', lat: 3, lng: 2, rank: 99 }])
    expect(transfer).toEqual(response.positions.map(p => p.buffer))
  })

  it('leaves labels out unless asked', () => {
    const buffer = new TextEncoder().encode('{"type":"FeatureCollection","features":[]}').buffer as ArrayBuffer
    const { response } = processLayerRequest({ id: 1, buffer, radii: [1], withLabels: false })
    expect(response).toEqual({ id: 1, positions: [new Float32Array(0)] })
  })

  it('answers a body that is not a FeatureCollection with an error naming what it got', () => {
    const buffer = new TextEncoder().encode('<!doctype html><html>').buffer as ArrayBuffer
    const { response, transfer } = processLayerRequest({ id: 2, buffer, radii: [1], withLabels: false })
    expect(response.id).toBe(2)
    expect('error' in response && response.error).toMatch(/JSON/)
    expect(transfer).toEqual([])
    const notFc = new TextEncoder().encode('{"type":"Feature"}').buffer as ArrayBuffer
    const second = processLayerRequest({ id: 3, buffer: notFc, radii: [1], withLabels: false }).response
    expect('error' in second && second.error).toMatch(/FeatureCollection/)
  })
})
