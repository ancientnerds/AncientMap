import { describe, expect, it } from 'vitest'

import { feedItemToStory, pickLeadAndRail, storyHref, type FeedItem } from '../feedClient'

const item = (over: Partial<FeedItem>): FeedItem => ({
  id: 1,
  headline: 'Headline',
  summary: 'Summary line.',
  facts: ['One fact'],
  post_text: 'First sentence here. Second sentence. https://example.org/src',
  screenshot_url: '/data/news/screenshots/x.webp',
  youtube_url: 'https://www.youtube.com/watch?v=abc123',
  news_category: 'artifact',
  significance: 5,
  created_at: '2026-09-08T19:33:29',
  timestamp_seconds: 42,
  speculative_tag: null,
  site_id: null,
  site_name: null,
  site_name_extracted: null,
  site_country: null,
  site_type: null,
  site_period_name: null,
  site_period_start: null,
  web_sources: [{ url: 'https://a.b' }, { url: 'https://c.d' }],
  video: {
    id: 'abc123',
    title: 'Video title',
    channel_name: 'Michael Button',
    published_at: '2026-09-08T18:00:00',
  },
  ...over,
})

describe('feedItemToStory', () => {
  it('maps the feed row to the story payload the server sends', () => {
    expect(feedItemToStory(item({}))).toEqual({
      id: 1,
      headline: 'Headline',
      summary: 'Summary line.',
      facts: ['One fact'],
      post_text: 'First sentence here. Second sentence. https://example.org/src',
      site_name: '',
      site_id: '',
      site_country: '',
      site_curated: false,
      site_type: null,
      site_period_name: null,
      site_period_start: null,
      significance: 5,
      screenshot_url: '/data/news/screenshots/x.webp',
      youtube_url: 'https://www.youtube.com/watch?v=abc123',
      video_title: 'Video title',
      channel_name: 'Michael Button',
      published_at: '2026-09-08T18:00:00',
      news_category: 'artifact',
      web_sources: [{ url: 'https://a.b' }, { url: 'https://c.d' }],
      timestamp_seconds: 42,
      speculative_tag: null,
      related: [],
    })
  })

  it('dates the story by its video, and by the row only when the video has none', () => {
    const noVideoDate = feedItemToStory(item({ video: { id: 'x', title: 't', channel_name: 'c', published_at: '' } }))
    expect(noVideoDate.published_at).toBe('2026-09-08T19:33:29')
  })

  it('takes the matched site name, else the extractor guess, else nothing', () => {
    expect(feedItemToStory(item({ site_name: 'Etowah', site_name_extracted: 'etowa' })).site_name).toBe('Etowah')
    expect(feedItemToStory(item({ site_name_extracted: 'Trundholm bog' })).site_name).toBe('Trundholm bog')
    expect(feedItemToStory(item({})).site_name).toBe('')
  })

  it('never claims a refetched site is curated — the feed does not say', () => {
    // site_curated gates the /sites/{country}/{slug} chip, and that page is a
    // 404 for bulk-imported sites. The country and globe chips still work.
    const s = feedItemToStory(
      item({ site_id: 'da3ff939-2402-4bf8-a476-e7725c81c8d5', site_name: 'Stirling Castle', site_country: 'United Kingdom' }),
    )
    expect(s.site_curated).toBe(false)
    expect(s.site_id).toBe('da3ff939-2402-4bf8-a476-e7725c81c8d5')
    expect(s.site_country).toBe('United Kingdom')
  })

  it('carries the nullable feed fields into the non-null payload shape', () => {
    const bare = feedItemToStory(item({ post_text: null, youtube_url: null, facts: null, web_sources: null }))
    expect(bare.post_text).toBe('')
    expect(bare.youtube_url).toBe('')
    expect(bare.facts).toBeNull()
    expect(bare.web_sources).toBeNull()
  })
})

describe('storyHref', () => {
  it('is the story page path, slug and id', () => {
    expect(storyHref(feedItemToStory(item({})))).toBe('/news-archive/headline-1')
  })
})

describe('pickLeadAndRail', () => {
  it('lead = highest significance, ties to the newer, list keeps feed order without the lead', () => {
    const rows = [
      feedItemToStory(item({ id: 3, significance: 4, video: { id: 'a', title: 't', channel_name: 'c', published_at: '2026-09-08T10:00:00' } })),
      feedItemToStory(item({ id: 2, significance: 9, video: { id: 'b', title: 't', channel_name: 'c', published_at: '2026-09-07T10:00:00' } })),
      feedItemToStory(item({ id: 1, significance: 9, video: { id: 'c', title: 't', channel_name: 'c', published_at: '2026-09-06T10:00:00' } })),
    ]
    const { lead, rail } = pickLeadAndRail(rows)
    expect(lead.id).toBe(2)
    expect(rail.map(r => r.id)).toEqual([3, 1])
  })
})
