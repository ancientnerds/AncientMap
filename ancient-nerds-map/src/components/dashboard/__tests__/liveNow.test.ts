import { describe, expect, it } from 'vitest'

import { fmtSpan, secondsSince } from '../LiveNow'

describe('LiveNow fmtSpan', () => {
  it('never claims a whole minute it does not have', () => {
    expect(fmtSpan(0)).toBe('< 1 min')
    expect(fmtSpan(30)).toBe('< 1 min')
    expect(fmtSpan(59)).toBe('< 1 min')
  })

  it('reads minutes below the hour', () => {
    expect(fmtSpan(60)).toBe('1 min')
    expect(fmtSpan(360)).toBe('6 min')
  })

  it('splits hours from minutes and keeps the zero minute', () => {
    expect(fmtSpan(7860)).toBe('2 h 11 min')
    // A round hour must still say "min", or the row reads as a different unit
    // from the one above it.
    expect(fmtSpan(3600)).toBe('1 h 0 min')
  })
})

describe('LiveNow secondsSince', () => {
  it('measures whole seconds against the clock it is given', () => {
    expect(secondsSince('2026-09-19T07:30:00Z', Date.parse('2026-09-19T08:07:00Z'))).toBe(2220)
  })

  it('clamps a stamp from the future to zero', () => {
    // last_seen comes from the database's clock, not the browser's, so a
    // reader whose machine is a few seconds slow must not see "-4 s ago".
    expect(secondsSince('2026-09-19T08:07:00Z', Date.parse('2026-09-19T07:30:00Z'))).toBe(0)
  })
})
