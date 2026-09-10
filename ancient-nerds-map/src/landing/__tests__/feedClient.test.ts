import { describe, expect, it } from 'vitest'

import { feedItemToTeaser, leadFirst, type FeedItem } from '../feedClient'

const item = (over: Partial<FeedItem>): FeedItem => ({
  id: 1,
  headline: 'Headline',
  screenshot_url: '/data/news/screenshots/x.webp',
  news_category: 'artifact',
  significance: 5,
  created_at: '2026-09-08T19:33:29',
  site_name: null,
  site_name_extracted: null,
  video: {
    channel_name: 'Michael Button',
    published_at: '2026-09-08T18:00:00',
  },
  ...over,
})

describe('feedItemToTeaser', () => {
  it('maps the feed row to the lean list row the server sends', () => {
    expect(feedItemToTeaser(item({}))).toEqual({
      id: 1,
      headline: 'Headline',
      screenshot_url: '/data/news/screenshots/x.webp',
      news_category: 'artifact',
      significance: 5,
      published_at: '2026-09-08T18:00:00',
      site_name: '',
      channel_name: 'Michael Button',
    })
  })

  it('dates the story by its video, and by the row only when the video has none', () => {
    const noVideoDate = feedItemToTeaser(item({ video: { channel_name: 'c', published_at: '' } }))
    expect(noVideoDate.published_at).toBe('2026-09-08T19:33:29')
  })

  it('takes the matched site name, else the extractor guess, else nothing', () => {
    expect(feedItemToTeaser(item({ site_name: 'Etowah', site_name_extracted: 'etowa' })).site_name).toBe('Etowah')
    expect(feedItemToTeaser(item({ site_name_extracted: 'Trundholm bog' })).site_name).toBe('Trundholm bog')
    expect(feedItemToTeaser(item({})).site_name).toBe('')
  })

  it('carries a category-less, score-less row without inventing values', () => {
    const bare = feedItemToTeaser(item({ news_category: null, significance: null, screenshot_url: null }))
    expect(bare.news_category).toBeNull()
    expect(bare.significance).toBeNull()
    expect(bare.screenshot_url).toBeNull()
  })
})

describe('leadFirst', () => {
  it('puts the highest significance first, ties to the newer, rest in feed order', () => {
    const rows = [
      feedItemToTeaser(item({ id: 3, significance: 4, video: { channel_name: 'c', published_at: '2026-09-08T10:00:00' } })),
      feedItemToTeaser(item({ id: 2, significance: 9, video: { channel_name: 'c', published_at: '2026-09-07T10:00:00' } })),
      feedItemToTeaser(item({ id: 1, significance: 9, video: { channel_name: 'c', published_at: '2026-09-06T10:00:00' } })),
    ]
    expect(leadFirst(rows).map(r => r.id)).toEqual([2, 3, 1])
  })
})
