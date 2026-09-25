import { describe, expect, it } from 'vitest'

import { abandonLine, endingItems, secs, timesLine, visitorsLine } from '../GlobeReach'
import type { GlobeData } from '../types'

/** The live seven-day window on 2026-09-19, straight out of SQL_GLOBE:
 *  36 loads over 22 sessions, 10 globe_ready reports, 9450 ms at best. */
const live: GlobeData = {
  loads: 36,
  reached: 10,
  gave_up: 26,
  sessions: { all: 22, reached: 8 },
  ready_ms: { min: 9450, median: 19917, max: 80383, samples: 10 },
  not_reached: { gate: 9, unsupported: 2, error: 3, abandoned: 7, no_signal: 5 },
  abandon_ms: { min: 3100, median: 9800, max: 44000, samples: 7 },
}

describe('GlobeReach secs', () => {
  it('rounds down where the binary value sits below the half', () => {
    // 9450 / 1000 is 9.4499999999999992895 in IEEE-754, so toFixed(1) gives
    // "9.4". This is the live minimum, so the number is on the panel today.
    expect(secs(9450)).toBe('9.4 s')
    expect(secs(9500)).toBe('9.5 s')
  })

  it('keeps one decimal on the live extremes', () => {
    expect(secs(80383)).toBe('80.4 s')
    expect(secs(19917)).toBe('19.9 s')
  })
})

describe('GlobeReach timesLine', () => {
  it('says so plainly when no globe came up', () => {
    const none: GlobeData = {
      ...live,
      ready_ms: { min: null, median: null, max: null, samples: 0 },
    }
    // globe_ready fires when the overlay fades (sites, layers, focus), not at the layers
    expect(timesLine(none)).toBe('No globe came up in this window.')
  })

  it('names only best and worst below the median floor, and never prints null', () => {
    const thin: GlobeData = {
      ...live,
      ready_ms: { min: 9450, median: null, max: 80383, samples: 4 },
    }
    const line = timesLine(thin)
    expect(line).toBe('The 4 globe_ready reports we have waited 9.4 s at best, 80.4 s at worst.')
    expect(line).not.toContain('null')
    expect(line).not.toContain('in the middle')
  })

  it('names all three once the median is filled', () => {
    expect(timesLine(live)).toBe(
      'The 10 globe_ready reports we have waited 9.4 s at best, 19.9 s in the middle, 80.4 s at worst.'
    )
  })

  it('does not build a best and a worst out of one measurement', () => {
    // A quiet week reaches this: eleven globe_ready events in the live
    // seven-day window, eight two days earlier. min === max there, and the
    // plural sentence read "The 1 globe_ready reports … 9.4 s at best,
    // 9.4 s at worst" — a spread nothing measured.
    const one = { ...live, ready_ms: { min: 9450, median: null, max: 9450, samples: 1 } }
    expect(timesLine(one)).toBe('The one globe_ready report we have waited 9.4 s.')
  })
})

describe('GlobeReach visitorsLine', () => {
  it('names the people behind the page loads the tiles count', () => {
    // The tiles divide by loads on purpose (one person reloading counts
    // twice); `sessions` is the only visitor figure in the response and was
    // computed, typed and never rendered.
    expect(visitorsLine(live)).toBe('8 of 22 visitors who opened it got there.')
  })

  it('says nobody opened it rather than dividing by nothing', () => {
    expect(visitorsLine({ ...live, sessions: { all: 0, reached: 0 } })).toBe(
      'Nobody opened the globe in this window.'
    )
  })
})

describe('GlobeReach endingItems', () => {
  it('lists the ways a load ends in the order a load meets them', () => {
    const items = endingItems(live)
    expect(items.map(i => i.label)).toEqual([
      'Stopped at the phone gate',
      'Device cannot run the globe',
      'Error while starting',
      'Left while loading',
      'No signal',
    ])
    expect(items.map(i => i.value)).toEqual([9, 2, 3, 7, 5])
    // Rows that happen to be zero stay: the order is the reading, not the rank.
    const quiet = endingItems({ ...live, not_reached: { ...live.not_reached, unsupported: 0 } })
    expect(quiet.map(i => i.key)).toEqual(['gate', 'unsupported', 'error', 'abandoned', 'no_signal'])
  })

  it('hints the middle wait on the abandon row only when there is a middle', () => {
    const hints = endingItems(live).map(i => i.hint)
    expect(hints).toEqual([undefined, undefined, undefined, 'median 9.8 s', undefined])
    const thin = endingItems({ ...live, abandon_ms: { min: 3100, median: null, max: 44000, samples: 4 } })
    expect(thin.every(i => i.hint === undefined)).toBe(true)
  })
})

describe('GlobeReach abandonLine', () => {
  it('says nothing without a measured abandon', () => {
    expect(abandonLine({ ...live, abandon_ms: { min: null, median: null, max: null, samples: 0 } })).toBe('')
  })

  it('does not build a spread out of one measurement', () => {
    const one = { ...live, abandon_ms: { min: 4200, median: null, max: 4200, samples: 1 } }
    expect(abandonLine(one)).toBe('The one load left while loading had waited 4.2 s.')
  })

  it('names only the shortest and the longest below the median floor, and never prints null', () => {
    const thin = { ...live, abandon_ms: { min: 3100, median: null, max: 44000, samples: 4 } }
    const line = abandonLine(thin)
    expect(line).toBe('The 4 loads left while loading had waited 3.1 s at the shortest, 44.0 s at the longest.')
    expect(line).not.toContain('null')
  })

  it('names the middle once there is one', () => {
    expect(abandonLine(live)).toBe(
      'The 7 loads left while loading had waited 3.1 s at the shortest, 9.8 s in the middle, 44.0 s at the longest.'
    )
  })
})
