/**
 * @vitest-environment jsdom
 *
 * MapboxGlobeService: the zoom methods the touch gestures use, and the report
 * that keeps the slider in step with a finger zoom (2026-10-01: a pinch zoomed
 * only the map, the slider stayed at 66 % and the 3D globe never came back).
 * Real mapbox-gl does not run under jsdom; a fake map stands in for it.
 */
import { describe, it, expect, vi } from 'vitest'

vi.mock('mapbox-gl', () => ({ default: {} }))
vi.mock('mapbox-gl/dist/mapbox-gl.css', () => ({}))

import { MapboxGlobeService } from '../MapboxGlobeService'

type Handler = (e?: unknown) => void

function fakeMap(zoom = 5) {
  const handlers: Record<string, Handler[]> = {}
  const state = { zoom }
  const map = {
    getZoom: () => state.zoom,
    getMinZoom: () => 0.7,
    getMaxZoom: () => 22,
    unproject: vi.fn(([x, y]: [number, number]) => ({ lng: x / 10, lat: y / 10 })),
    project: vi.fn(([lng, lat]: [number, number]) => {
      // a flat map: 100 px per degree at zoom 5, doubling per zoom level
      const scale = 100 * Math.pow(2, state.zoom - 5)
      return { x: lng * scale, y: lat * scale }
    }),
    jumpTo: vi.fn((o: { zoom?: number }) => { if (o.zoom !== undefined) state.zoom = o.zoom }),
    easeTo: vi.fn((o: { zoom?: number }) => { if (o.zoom !== undefined) state.zoom = o.zoom }),
    on: (type: string, fn: Handler) => { (handlers[type] ??= []).push(fn) },
    fire: (type: string, e?: unknown) => handlers[type]?.forEach(fn => fn(e)),
  }
  return map
}

function service(map: ReturnType<typeof fakeMap>, interactive = true) {
  const s = new MapboxGlobeService()
  const container = document.createElement('div')
  container.getBoundingClientRect = () => ({ left: 20, top: 100, width: 412, height: 815 }) as DOMRect
  Object.assign(s as unknown as Record<string, unknown>, { map, container, isInitialized: true, isInteractive: interactive })
  ;(s as unknown as { setupEventListeners: () => void }).setupEventListeners()
  return s
}

describe('zoomAround', () => {
  it('zooms around the map point under the finger, in container coordinates', () => {
    const map = fakeMap(5)
    const s = service(map)
    s.zoomAround(1.5, 220, 300, false)
    expect(map.unproject).toHaveBeenCalledWith([200, 200])
    expect(map.jumpTo).toHaveBeenCalledWith({ zoom: 6.5, around: { lng: 20, lat: 20 } })
  })

  it('animates when asked (double tap, two-finger tap)', () => {
    const map = fakeMap(5)
    service(map).zoomAround(-1, 220, 300, true)
    expect(map.easeTo).toHaveBeenCalledWith({ zoom: 4, around: { lng: 20, lat: 20 }, duration: 300 })
  })

  it('stays within the map zoom range', () => {
    const map = fakeMap(1)
    service(map).zoomAround(-3, 220, 300, false)
    expect(map.jumpTo).toHaveBeenCalledWith(expect.objectContaining({ zoom: 0.7 }))
  })

  it('reports the new zoom like any finger zoom', () => {
    const map = fakeMap(5)
    const s = service(map)
    const report = vi.fn()
    s.onTouchZoom(report)
    s.zoomAround(0.25, 220, 300, false)
    expect(report).toHaveBeenCalledWith(5.25)
  })
})

describe('the report of a finger zoom', () => {
  it("passes on a zoom of Mapbox's own pinch", () => {
    const map = fakeMap(5)
    const s = service(map)
    const report = vi.fn()
    s.onTouchZoom(report)
    map.fire('zoom', { originalEvent: { type: 'touchmove' } })
    expect(report).toHaveBeenCalledWith(5)
  })

  it('ignores the wheel and programmatic zooms (the slider already knows those)', () => {
    const map = fakeMap(5)
    const s = service(map)
    const report = vi.fn()
    s.onTouchZoom(report)
    map.fire('zoom', { originalEvent: { type: 'wheel' } })
    map.fire('zoom', {})
    map.fire('zoom', undefined)
    expect(report).not.toHaveBeenCalled()
  })

  it('is silent while the map is not the interactive one', () => {
    const map = fakeMap(5)
    const s = service(map, false)
    const report = vi.fn()
    s.onTouchZoom(report)
    map.fire('zoom', { originalEvent: { type: 'touchmove' } })
    expect(report).not.toHaveBeenCalled()
  })
})

describe('zoomToSpan', () => {
  it('sets the zoom at which two points are the given distance apart', () => {
    const map = fakeMap(5)
    // 2 degrees apart = 200 px at zoom 5; 50 px wanted -> two levels out
    service(map).zoomToSpan({ lat: 0, lng: 0 }, { lat: 0, lng: 2 }, 50)
    expect(map.getZoom()).toBeCloseTo(3, 9)
  })
})
