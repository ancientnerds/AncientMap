import { describe, expect, it } from 'vitest'

import { feedItemToTeaser, firstSentence, pickLeadAndRail, type FeedItem } from '../feedClient'

const item = (over: Partial<FeedItem>): FeedItem => ({
  id: 1,
  headline: 'Headline',
  post_text: 'First sentence here. Second sentence. https://example.org/src',
  screenshot_url: '/data/news/screenshots/x.webp',
  news_category: 'artifact',
  significance: 5,
  created_at: '2026-09-08T19:33:29',
  site_id: null,
  site_name: null,
  site_country: null,
  web_sources: [{ url: 'a' }, { url: 'b' }],
  video: { channel_name: 'Michael Button' },
  ...over,
})

describe('firstSentence', () => {
  it('takes the first sentence and drops trailing links', () => {
    expect(firstSentence('One. Two. https://x.y')).toBe('One.')
    expect(firstSentence('No period at all https://x.y')).toBe('No period at all')
  })
  it('cuts overlong sentences at 180 characters on a word boundary', () => {
    const long = `${'word '.repeat(50)}end.`
    const out = firstSentence(long)
    expect(out.length).toBeLessThanOrEqual(181)
    expect(out.endsWith('…')).toBe(true)
  })
})

describe('feedItemToTeaser', () => {
  it('maps the feed row to the payload shape', () => {
    const t = feedItemToTeaser(item({}))
    expect(t).toEqual({
      id: 1,
      headline: 'Headline',
      summary: 'First sentence here.',
      screenshot_url: '/data/news/screenshots/x.webp',
      category: 'artifact',
      significance: 5,
      created_at: '2026-09-08T19:33:29',
      channel: 'Michael Button',
      sources: 2,
      path: '/news-archive/headline-1',
      site: null,
    })
  })
  it('builds the site chip only with id, name and country', () => {
    const t = feedItemToTeaser(item({ site_id: 'da3ff939-2402-4bf8-a476-e7725c81c8d5', site_name: 'Stirling Castle', site_country: 'United Kingdom' }))
    expect(t.site).toEqual({ name: 'Stirling Castle', country: 'United Kingdom' })
    expect(feedItemToTeaser(item({ site_id: 'x', site_name: 'Y', site_country: null })).site).toBeNull()
  })
})

describe('pickLeadAndRail', () => {
  it('lead = highest significance, ties to the newer, rail keeps feed order without the lead', () => {
    const rows = [
      feedItemToTeaser(item({ id: 3, significance: 4, created_at: '2026-09-08T10:00:00' })),
      feedItemToTeaser(item({ id: 2, significance: 9, created_at: '2026-09-07T10:00:00' })),
      feedItemToTeaser(item({ id: 1, significance: 9, created_at: '2026-09-06T10:00:00' })),
    ]
    const { lead, rail } = pickLeadAndRail(rows)
    expect(lead.id).toBe(2)
    expect(rail.map(r => r.id)).toEqual([3, 1])
  })
})
