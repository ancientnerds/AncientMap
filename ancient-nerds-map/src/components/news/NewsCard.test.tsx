import { describe, expect, it } from 'vitest'

import type { NewsItemData } from '../../types/news'
import { storyHrefFor } from './NewsCard'

/**
 * storyHrefFor spiegelt story_page_query() im Backend. Weicht es ab, verlinken
 * Karten auf Seiten, die seit 2026-09-11 mit 410 antworten — der Feed filtert
 * significance selbst, die Journal-Zitate-Route (/api/news/articles/{id}/
 * citations) aber nicht, und beide landen in derselben Karte.
 */
function item(overrides: Partial<NewsItemData> = {}): NewsItemData {
  return {
    id: 8270,
    headline: 'Bayeux Tapestry offers rare glimpse',
    post_text: 'Archaeologists re-examined the tapestry.',
    facts: null,
    timestamp_range: null,
    timestamp_seconds: null,
    screenshot_url: null,
    youtube_url: null,
    youtube_deep_url: null,
    video: {
      id: 'abc',
      title: 'v',
      channel_name: 'c',
      channel_id: 'ci',
      published_at: '2026-09-10T00:00:00',
      thumbnail_url: null,
      duration_minutes: null,
    },
    created_at: '2026-09-10T00:00:00',
    site_id: null,
    site_name: null,
    site_lat: null,
    site_lon: null,
    site_type: null,
    site_period_name: null,
    site_period_start: null,
    site_country: null,
    site_name_extracted: null,
    significance: 5,
    news_category: null,
    speculative_tag: null,
    verified: true,
    verified_at: null,
    web_sources: null,
    ...overrides,
  }
}

describe('storyHrefFor', () => {
  it('links a scored story with a body', () => {
    expect(storyHrefFor(item())).toContain('-8270')
  })

  it('links a story the scorer has not reached yet', () => {
    // significance === null heißt "noch nicht bewertet", nicht "verworfen" —
    // story_page_query lässt diese Zeilen ebenfalls durch.
    expect(storyHrefFor(item({ significance: null }))).toContain('-8270')
  })

  it('refuses a story without a body', () => {
    expect(storyHrefFor(item({ post_text: null }))).toBeNull()
  })

  it('refuses a rejected story, whose page answers 410', () => {
    expect(storyHrefFor(item({ significance: 1 }))).toBeNull()
  })

  it('links a story at the significance floor', () => {
    expect(storyHrefFor(item({ significance: 2 }))).toContain('-8270')
  })
})
