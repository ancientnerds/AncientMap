/**
 * The pure helpers the paper extras share with researchMeta: the newest
 * correction day and the two YouTube URLs.
 */

import { describe, expect, it } from 'vitest'

import { latestCorrectionDate, youtubeThumbnailUrl, youtubeWatchUrl } from '../paperExtras'

describe('latestCorrectionDate', () => {
  it('picks the newest day whatever the order', () => {
    expect(
      latestCorrectionDate([
        { date: '2026-10-04', text: 'b', evidence_id: null, holds_anchor: false },
        { date: '2026-10-02', text: 'a', evidence_id: null, holds_anchor: false },
        { date: '2026-11-01', text: 'c', evidence_id: null, holds_anchor: false },
      ]),
    ).toBe('2026-11-01')
  })
})

describe('YouTube URLs', () => {
  it('builds the watch page from the id', () => {
    expect(youtubeWatchUrl('dQw4w9WgXcQ')).toBe('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  })

  it('builds the thumbnail every video has (hqdefault)', () => {
    expect(youtubeThumbnailUrl('dQw4w9WgXcQ')).toBe('https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg')
  })
})
