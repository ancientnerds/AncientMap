import { describe, expect, it } from 'vitest'

import { dotRadius, hourWeights, project, ringPath } from '../mapMath'

describe('map math', () => {
  it('projects lon/lat onto a 1000×500 equirectangular canvas', () => {
    expect(project([0, 0])).toEqual([500, 250])
    expect(project([-180, 90])).toEqual([0, 0])
    expect(project([180, -90])).toEqual([1000, 500])
  })

  it('sums sessions per country for one hour, or all hours', () => {
    const pts = [
      { country: 'DE', city: 'x', hour: 8, sessions: 2 },
      { country: 'DE', city: 'y', hour: 9, sessions: 1 },
      { country: 'US', city: 'z', hour: 8, sessions: 5 },
    ]
    expect(hourWeights(pts, 8)).toEqual({ DE: 2, US: 5 })
    expect(hourWeights(pts, null)).toEqual({ DE: 3, US: 5 })
  })

  it('turns a GeoJSON ring into a closed SVG path, dropping the repeated closing point', () => {
    const ring = [
      [-180, 90],
      [180, 90],
      [180, -90],
      [-180, -90],
      [-180, 90],
    ]
    expect(ringPath(ring)).toBe('M0 0L1000 0L1000 500L0 500Z')
  })


  it('sizes a dot by the square root of its sessions', () => {
    expect(dotRadius(0)).toBe(4)
    expect(dotRadius(1)).toBe(7)
    expect(dotRadius(4)).toBe(10)
  })
})
