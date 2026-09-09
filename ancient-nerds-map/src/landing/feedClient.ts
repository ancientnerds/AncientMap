/**
 * Client side of the Stories section: fetches /api/news/feed for the
 * category chips and "load more" and maps feed rows to the StoryTeaser
 * shape the server already used for the first paint. The mapping mirrors
 * api/routes/landing_html.py::story_teaser — same slug helpers, same
 * first-sentence rule — so a refetched card looks exactly like an SSR one.
 */
import { splitPostText } from '../components/news/postText'
import { storyPath } from '../seo/meta'
import { blurb } from '../seo/text'
import type { StoryTeaser } from '../types/anRoute'

export interface FeedItem {
  id: number
  headline: string
  post_text: string | null
  screenshot_url: string | null
  news_category: string | null
  significance: number | null
  created_at: string
  site_id: string | null
  site_name: string | null
  site_country: string | null
  web_sources: unknown[] | null
  video: { channel_name: string }
}

interface FeedResponse {
  items: FeedItem[]
  has_more: boolean
}

const MAX_SUMMARY = 180

/**
 * First sentence of the post text, capped at MAX_SUMMARY. The cut itself is
 * blurb()'s job — one definition of "shorten on a word boundary and append
 * an ellipsis" for cards and descriptions alike.
 */
export function firstSentence(postText: string | null): string {
  if (!postText) return ''
  const body = splitPostText(postText).paragraphs[0] ?? ''
  const match = body.match(/^.*?[.!?](?=\s|$)/)
  return blurb((match ? match[0] : body).trim(), MAX_SUMMARY)
}

export function feedItemToTeaser(it: FeedItem): StoryTeaser {
  const site =
    it.site_id && it.site_name && it.site_country
      ? { name: it.site_name, country: it.site_country }
      : null
  return {
    id: it.id,
    headline: it.headline,
    summary: firstSentence(it.post_text),
    screenshot_url: it.screenshot_url,
    category: it.news_category,
    significance: it.significance,
    created_at: it.created_at,
    channel: it.video.channel_name,
    sources: it.web_sources?.length ?? 0,
    path: storyPath(it.headline, it.id),
    site,
  }
}

/** Lead = highest significance (ties: newer); rail = the rest in feed order. */
export function pickLeadAndRail(rows: StoryTeaser[]): { lead: StoryTeaser; rail: StoryTeaser[] } {
  const lead = rows.reduce((best, r) => {
    const s = r.significance ?? 0
    const b = best.significance ?? 0
    if (s > b) return r
    if (s === b && r.created_at > best.created_at) return r
    return best
  })
  return { lead, rail: rows.filter(r => r.id !== lead.id) }
}

export async function fetchFeed(params: { category: string | null; page: number; pageSize: number }): Promise<{ items: StoryTeaser[]; hasMore: boolean }> {
  const q = new URLSearchParams({ page: String(params.page), page_size: String(params.pageSize) })
  if (params.category) q.set('news_category', params.category)
  const res = await fetch(`/api/news/feed?${q}`)
  if (!res.ok) throw new Error(`feed ${res.status}`)
  const data = (await res.json()) as FeedResponse
  return { items: data.items.map(feedItemToTeaser), hasMore: data.has_more }
}
