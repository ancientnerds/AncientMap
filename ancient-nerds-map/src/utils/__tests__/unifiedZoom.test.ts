import { describe, it, expect } from 'vitest'
import {
  MAPBOX_SWITCH_PERCENT,
  mapboxPercentForSlider,
  mapboxZoomToPercent,
  sliderAfterTouchZoom,
  sliderForMapboxZoom,
} from '../unifiedZoom'

/**
 * The globe has one zoom value, the slider (0-100). 0-65 is the Three.js globe,
 * 66-100 the Mapbox map. Mouse wheel and slider move it; since 2026-10-01 a
 * finger pinch on the Mapbox map moves it too, through the inverse below, so a
 * pinch out can bring the 3D globe back.
 */
describe('unified zoom', () => {
  it('switches to Mapbox at 66 %', () => {
    expect(MAPBOX_SWITCH_PERCENT).toBe(66)
  })

  it('maps a Mapbox zoom level onto 0-100 % of 0.7..18', () => {
    expect(mapboxZoomToPercent(0.7)).toBe(0)
    expect(mapboxZoomToPercent(18)).toBe(100)
    expect(mapboxZoomToPercent(9.35)).toBeCloseTo(50, 10)
  })

  // The slider-to-map step the wheel and the slider use, as it was inline in
  // useGlobeZoom.ts: base + (slider - 66) / 34 * (100 - base), capped at 100.
  it.each([
    [66, 34.9, 34.9],
    [83, 34.9, 34.9 + 0.5 * 65.1],
    [100, 34.9, 100],
    [66, 20, 20],
    [90, 20, 20 + (24 / 34) * 80],
  ])('slider %d with base %d % gives Mapbox %f %', (slider, base, expected) => {
    expect(mapboxPercentForSlider(slider, base)).toBeCloseTo(expected, 12)
  })

  it('reads a Mapbox zoom back into the slider value it came from', () => {
    const base = mapboxZoomToPercent(4.5)
    for (const slider of [66, 70, 83, 99, 100]) {
      const mapboxPercent = mapboxPercentForSlider(slider, base)
      const mapboxZoom = 0.7 + (mapboxPercent / 100) * 17.3
      expect(sliderForMapboxZoom(mapboxZoom, base)).toBeCloseTo(slider, 9)
    }
  })

  it('goes below 66 % when the map is zoomed out past where it was entered', () => {
    const base = mapboxZoomToPercent(4.5)
    expect(sliderForMapboxZoom(4.5, base)).toBeCloseTo(66, 10)
    expect(sliderForMapboxZoom(4.0, base)).toBeLessThan(66)
    expect(sliderForMapboxZoom(5.0, base)).toBeGreaterThan(66)
  })
})

describe('sliderAfterTouchZoom', () => {
  it('gives the whole slider value a finger zoom on the map stands for', () => {
    const base = mapboxZoomToPercent(4.5)
    expect(sliderAfterTouchZoom(4.5, base)).toBe(66)
    // a tenth of a level below the entry zoom is a quarter step: still 66
    expect(sliderAfterTouchZoom(4.4, base)).toBe(66)
    expect(sliderAfterTouchZoom(3.0, base)).toBeLessThan(66)
    expect(Number.isInteger(sliderAfterTouchZoom(7.123, base))).toBe(true)
  })

  it('stays within 0-100', () => {
    const base = mapboxZoomToPercent(4.5)
    expect(sliderAfterTouchZoom(0.7, base)).toBeGreaterThanOrEqual(0)
    expect(sliderAfterTouchZoom(22, base)).toBe(100)
  })
})
