import { describe, expect, it } from 'vitest'

import { deviceItem, groupLine, languageItem, mobileLine } from '../Devices'
import type { DevicesData } from '../types'

/** The live seven-day window, re-measured 2026-09-19: laptop 117 + desktop 6
 *  fold to one desktop bucket, mobile 45, over 168 sessions. */
const live: DevicesData = {
  sessions: 168,
  devices: [
    { device: 'desktop', sessions: 123 },
    { device: 'mobile', sessions: 45 },
  ],
  languages: [
    { language: 'en-US', sessions: 93 },
    { language: 'en-GB', sessions: 21 },
    { language: 'zh-CN', sessions: 11 },
    { language: 'de-DE', sessions: 7 },
    { language: 'tr-TR', sessions: 4 },
  ],
  language_groups: [
    { language: 'en', sessions: 114 },
    { language: 'zh', sessions: 11 },
    { language: 'de', sessions: 7 },
    { language: 'tr', sessions: 4 },
  ],
}

describe('Devices rows', () => {
  it('names the laptop fold and prints the share next to its own count', () => {
    const row = deviceItem({ device: 'desktop', sessions: 123 }, 168)
    expect(row.label).toBe('Desktop, laptops included')
    expect(row.value).toBe(123)
    expect(row.hint).toBe('73 % of 168')
  })

  it('prints a word Umami invents later as it arrived', () => {
    expect(deviceItem({ device: 'watch', sessions: 1 }, 168).label).toBe('watch')
  })

  it('keeps the full language tag as the row title and adds no share', () => {
    const row = languageItem({ language: 'en-GB', sessions: 21 })
    expect(row.label).toBe('en-GB')
    expect(row.value).toBe(21)
    expect(row.hint).toBeUndefined()
  })
})

describe('Devices headline', () => {
  it('reads mobile against every session, never as a bare percentage', () => {
    expect(mobileLine(live)).toBe('Mobile is 45 of 168 sessions (27 %).')
  })

  it('counts a missing mobile bucket as zero', () => {
    expect(mobileLine({ ...live, devices: [{ device: 'desktop', sessions: 168 }] })).toBe(
      'Mobile is 0 of 168 sessions (0 %).'
    )
  })

  it('says nothing at all in an empty window, because both lists already do', () => {
    // The two sentences the note used to return here are the two `empty` props
    // of the lists above it, word for word, so the empty panel printed each of
    // them twice — visible in docs/reports/screenshots/dashboard-mobile-empty.png
    // before this was fixed.
    const empty: DevicesData = { sessions: 0, devices: [], languages: [], language_groups: [] }
    expect(mobileLine(empty)).toBe('')
    expect(groupLine(empty.language_groups, empty.sessions)).toBe('')
  })

  it('folds the tags onto their primary subtag with counts', () => {
    expect(groupLine(live.language_groups, live.sessions)).toBe(
      'By primary subtag: en 114, zh 11, de 7, tr 4 of 168 sessions.'
    )
  })
})
