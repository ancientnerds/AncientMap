import { describe, expect, it } from 'vitest'

import { dotRadius, project, ringPath } from '../mapMath'

describe('map math', () => {
  it('projects lon/lat onto a 1000×500 equirectangular canvas', () => {
    expect(project([0, 0])).toEqual([500, 250])
    expect(project([-180, 90])).toEqual([0, 0])
    expect(project([180, -90])).toEqual([1000, 500])
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


  it('sizes a dot by area against the busiest country', () => {
    expect(dotRadius(0, 100)).toBe(4)
    expect(dotRadius(100, 100)).toBe(26)
    expect(dotRadius(25, 100)).toBe(15)
    // An empty map divides by one, not by zero.
    expect(dotRadius(0, 0)).toBe(4)
  })
})
