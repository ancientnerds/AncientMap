import { describe, expect, it } from 'vitest'

import { bucketTotals, sourceBucket } from '../Sources'

describe('source buckets', () => {
  it('folds the API families into the six founder buckets', () => {
    expect(sourceBucket('google')).toBe('search')
    expect(sourceBucket('search')).toBe('search')
    expect(sourceBucket('ai')).toBe('ai')
    expect(sourceBucket('direct')).toBe('direct')
    expect(sourceBucket('discord.com')).toBe('discord')
    expect(sourceBucket('discord')).toBe('discord')
    expect(sourceBucket('youtube')).toBe('youtube')
    expect(sourceBucket('m.youtube.com')).toBe('youtube')
    expect(sourceBucket('reddit.com')).toBe('other')
  })

  it('sums sessions per bucket in the fixed display order', () => {
    const rows = [
      { source: 'google.com', family: 'google', sessions: 10 },
      { source: 'bing.com', family: 'search', sessions: 2 },
      { source: 'direct', family: 'direct', sessions: 7 },
      { source: 'youtube', family: 'youtube', sessions: 3 },
      { source: 'reddit.com', family: 'reddit.com', sessions: 1 },
    ]
    expect(bucketTotals(rows)).toEqual([
      ['search', 'Suche', 12],
      ['ai', 'KI-Assistenten', 0],
      ['discord', 'Discord', 0],
      ['youtube', 'YouTube', 3],
      ['direct', 'Direkt', 7],
      ['other', 'Andere', 1],
    ])
  })
})
