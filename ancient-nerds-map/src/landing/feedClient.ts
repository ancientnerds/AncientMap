/**
 * Client side of the Stories window: fetches /api/news/feed for the
 * category chips and "load more" and maps feed rows to the same StoryData
 * the server put in the payload (api/routes/articles_html.py::story_payload),
 * so a refetched story renders through <StoryArticle> exactly like an
 * SSR one.
 */
import { storyPath } from '../seo/meta'
import type { StoryData } from '../types/anRoute'

export interface FeedItem {
  id: number
  headline: string
  summary: string
  facts: string[] | null
  post_text: string | null
  screenshot_url: string | null
  youtube_url: string | null
  news_category: string | null
  significance: number | null
  created_at: string
  timestamp_seconds: number | null
  speculative_tag: string | null
  site_id: string | null
  site_name: string | null
  site_name_extracted: string | null
  site_country: string | null
  site_type: string | null
  site_period_name: string | null
  site_period_start: number | null
  web_sources: { url?: string | null; title?: string | null; snippet?: string | null }[] | null
  video: { id: string; title: string; channel_name: string; published_at: string }
}

interface FeedResponse {
  items: FeedItem[]
  has_more: boolean
}

/**
 * NewsItemResponse → StoryData.
 *
 * Two fields the feed does not carry:
 * - `site_curated` is false, so a refetched story shows the plain 📍 chip
 *   instead of a link to /sites/{country}/{slug}. That link is a 404 for
 *   bulk-imported sites, and the feed says nothing about source_id — the
 *   country and globe chips still work.
 * - `related` is empty, like every story in the homepage payload.
 *
 * `post_text` is nullable in the feed model and never null in the window:
 * splitPostText('') yields no paragraphs, so a body-less row renders as a
 * headline with meta and sources instead of throwing.
 */
export function feedItemToStory(it: FeedItem): StoryData {
  return {
    id: it.id,
    headline: it.headline,
    summary: it.summary,
    facts: it.facts,
    post_text: it.post_text ?? '',
    site_name: it.site_name ?? it.site_name_extracted ?? '',
    site_id: it.site_id ?? '',
    site_country: it.site_country ?? '',
    site_curated: false,
    site_type: it.site_type,
    site_period_name: it.site_period_name,
    site_period_start: it.site_period_start,
    significance: it.significance,
    screenshot_url: it.screenshot_url,
    youtube_url: it.youtube_url ?? '',
    video_title: it.video.title,
    channel_name: it.video.channel_name,
    // Same rule as story_payload: the video's publish date is the story's
    // date, and item creation is what is left when the video has none.
    published_at: it.video.published_at || it.created_at,
    news_category: it.news_category,
    web_sources: it.web_sources,
    timestamp_seconds: it.timestamp_seconds,
    speculative_tag: it.speculative_tag,
    related: [],
  }
}

/** Lead = highest significance (ties: newer); list = the rest in feed order. */
export function pickLeadAndRail(rows: StoryData[]): { lead: StoryData; rail: StoryData[] } {
  const lead = rows.reduce((best, r) => {
    const s = r.significance ?? 0
    const b = best.significance ?? 0
    if (s > b) return r
    if (s === b && r.published_at > best.published_at) return r
    return best
  })
  return { lead, rail: rows.filter(r => r.id !== lead.id) }
}

/** The window's link back to the full page — one definition for both. */
export function storyHref(story: StoryData): string {
  return storyPath(story.headline, story.id)
}

export async function fetchFeed(params: { category: string | null; page: number; pageSize: number }): Promise<{ items: StoryData[]; hasMore: boolean }> {
  const q = new URLSearchParams({ page: String(params.page), page_size: String(params.pageSize) })
  if (params.category) q.set('news_category', params.category)
  const res = await fetch(`/api/news/feed?${q}`)
  if (!res.ok) throw new Error(`feed ${res.status}`)
  const data = (await res.json()) as FeedResponse
  return { items: data.items.map(feedItemToStory), hasMore: data.has_more }
}
