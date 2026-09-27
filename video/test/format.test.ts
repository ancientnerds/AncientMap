import { describe, expect, it } from 'vitest'

import { domainOf, formatDistance, formatNumber, formatYear, haversineM, verbal, yearTicks } from '../src/format'

describe('format', () => {
  it('shows the domain without www', () => {
    expect(domainOf('https://www.dainst.org/baalbek?x=1')).toBe('dainst.org')
    expect(domainOf('https://en.wikipedia.org/wiki/Baalbek')).toBe('en.wikipedia.org')
  })
  it('measures and formats distances from coordinates', () => {
    // Baalbek quarry to the Temple of Jupiter: about 850 m
    const d = haversineM({ lat: 33.99917, lng: 36.20028 }, { lat: 34.00667, lng: 36.20333 })
    expect(d).toBeGreaterThan(800)
    expect(d).toBeLessThan(900)
    expect(formatDistance(d)).toMatch(/^8[0-9]0 m$/)
    expect(formatDistance(1449)).toBe('1.4 km')
    expect(formatDistance(23_400)).toBe('23 km')
  })
  it('writes BCE/CE years and refuses year 0', () => {
    expect(formatYear(-3000)).toBe('3000 BCE')
    expect(formatYear(120)).toBe('120 CE')
    expect(() => formatYear(0)).toThrow(/year 0/)
    expect(yearTicks(-200, 300)).toEqual([-200, -100, 100, 200, 300])
  })
  it('uses the house probability words', () => {
    expect([95, 80, 65, 50, 30, 10].map(verbal)).toEqual(['almost certain', 'very likely', 'likely', 'roughly even', 'unlikely', 'very unlikely'])
  })
  it('groups thousands', () => {
    expect(formatNumber(1650)).toBe('1,650')
    expect(formatNumber(12.54)).toBe('12.5')
    expect(formatNumber(1.75, 2)).toBe('1.75')
  })
})
