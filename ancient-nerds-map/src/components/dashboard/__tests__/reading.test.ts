import { describe, expect, it } from 'vitest'

import { ladderCells } from '../Reading'
import type { ReadingPage } from '../types'

const page = (over: Partial<ReadingPage>): ReadingPage => ({
  page: 'story',
  sessions: [11, 11, 11, 10],
  ...over,
})

describe('Reading ladderCells', () => {
  it('keeps every count and sizes each bar against the first mark', () => {
    expect(ladderCells(page({ sessions: [998, 811, 640, 300] }))).toEqual([
      { count: 998, share: 1 },
      { count: 811, share: 811 / 998 },
      { count: 640, share: 640 / 998 },
      { count: 300, share: 300 / 998 },
    ])
  })

  it('draws a full ladder when nobody dropped off', () => {
    expect(ladderCells(page({ sessions: [2, 2, 2, 2] })).map(c => c.share)).toEqual([1, 1, 1, 1])
  })

  it('survives a row whose first mark is zero instead of dividing by it', () => {
    expect(ladderCells(page({ sessions: [0, 0, 0, 0] })).every(c => c.share === 0)).toBe(true)
  })
})
