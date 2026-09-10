/**
 * Client side of the Stories window: fetches /api/news/feed for the
 * category chips and "load more" and maps feed rows to the same lean
 * StoryTeaser the server put in the payload
 * (api/routes/landing_html.py::story_teaser), so a refetched row renders
 * exactly like an SSR one.
 */
import type { StoryTeaser } from '../types/anRoute'

/**
 * The fields of NewsItemResponse a list row needs. The endpoint returns a
 * good deal more (body text, sources, site joins) — that is the story
 * page's material, and the homepage stopped rendering it when the window
 * became a portal.
 */
export interface FeedItem {
  id: number
  headline: string
  screenshot_url: string | null
  news_category: string | null
  significance: number | null
  created_at: string
  site_name: string | null
  site_name_extracted: string | null
  video: { channel_name: string; published_at: string }
}

interface FeedResponse {
  items: FeedItem[]
  has_more: boolean
}

/** NewsItemResponse → StoryTeaser. */
export function feedItemToTeaser(it: FeedItem): StoryTeaser {
  return {
    id: it.id,
    headline: it.headline,
    screenshot_url: it.screenshot_url,
    news_category: it.news_category,
    significance: it.significance,
    // Same rule as story_payload: the video's publish date is the story's
    // date, and item creation is what is left when the video has none.
    published_at: it.video.published_at || it.created_at,
    site_name: it.site_name ?? it.site_name_extracted ?? '',
    channel_name: it.video.channel_name,
  }
}

/**
 * The list in the order the section shows it: the lead first — highest
 * significance, ties to the newer — then the rest in feed order. Same rule
 * as landing_html.pick_lead_and_rail, so a refetched category reads like
 * the payload the server sent.
 */
export function leadFirst(rows: StoryTeaser[]): StoryTeaser[] {
  const lead = rows.reduce((best, r) => {
    const s = r.significance ?? 0
    const b = best.significance ?? 0
    if (s > b) return r
    if (s === b && r.published_at > best.published_at) return r
    return best
  })
  return [lead, ...rows.filter(r => r.id !== lead.id)]
}

export async function fetchFeed(params: { category: string | null; page: number; pageSize: number }): Promise<StoryTeaser[]> {
  const q = new URLSearchParams({ page: String(params.page), page_size: String(params.pageSize) })
  if (params.category) q.set('news_category', params.category)
  const res = await fetch(`/api/news/feed?${q}`)
  if (!res.ok) throw new Error(`feed ${res.status}`)
  const data = (await res.json()) as FeedResponse
  return data.items.map(feedItemToTeaser)
}
