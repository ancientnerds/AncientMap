import { describe, expect, it } from 'vitest'

import { readingItem } from '../Reading'
import type { ReadingPage } from '../types'

const page = (over: Partial<ReadingPage>): ReadingPage => ({
  page: 'story',
  sessions: [11, 11, 11, 10],
  ...over,
})

describe('Reading readingItem', () => {
  it('bars the first mark and continues the ladder in the hint', () => {
    const row = readingItem(page({}))
    expect(row.label).toBe('story')
    expect(row.value).toBe(11)
    expect(row.hint).toBe('· 11 · 11 · 10')
  })

  it('never warns and never shares — the whole panel is counts', () => {
    const row = readingItem(page({ page: 'country', sessions: [2, 2, 2, 1] }))
    expect(row.hint).toBe('· 2 · 2 · 1')
    expect(row.tone).toBeUndefined()
    expect(row.href).toBeUndefined()
  })

  it('keys by page type, so the same page type is one row', () => {
    expect(readingItem(page({})).key).toBe('read:story')
    expect(readingItem(page({ page: 'country' })).key).toBe('read:country')
  })

  it('leaves the hint off a funnel with a single mark', () => {
    expect(readingItem(page({ sessions: [4] })).hint).toBeUndefined()
  })

  it('separates thousands the way every other count on the page does', () => {
    expect(readingItem(page({ sessions: [4200, 1234] })).hint).toBe('· 1,234')
  })
})
