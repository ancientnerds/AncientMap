/**
 * window.__AN_ROUTE__ — injected by the server into every indexed page.
 *
 * The API serves these URLs (/news-archive/…, /sites/…, /research/…,
 * /articles/…) as the real app shell with the content already rendered
 * inside #root for crawlers. This object tells the React entry which page
 * to mount, and for stories it carries the whole payload so the page
 * renders with no extra request and no loading flash.
 *
 * Absent when the entry is opened directly (e.g. /site.html?id=…), so
 * every consumer must handle undefined.
 */

export interface StoryRoute {
  type: 'story'
  id: number
  headline: string
  summary: string
  facts: string[]
  postText: string
  screenshotUrl: string
  youtubeUrl: string
  videoTitle: string
  channelName: string
  publishedAt: string
  publishedDisplay: string
  category: string
  siteName: string
  sitePath: string
  siteId: string
  speculativeTag: string
  sources: { url: string; title: string; host: string; snippet: string }[]
  related: { slug: string; headline: string; kind: string }[]
}

interface StoryArchiveRoute {
  type: 'storyArchive'
  page: number
  totalPages: number
  total: number
  stories: {
    slug: string
    headline: string
    summary: string
    publishedDisplay?: string
    category?: string
    siteName?: string
    channelName?: string
    speculativeTag?: string
  }[]
}

export type AnRoute =
  | StoryRoute
  | StoryArchiveRoute
  | { type: 'site'; id: string }
  | { type: 'sitesIndex'; countries: { name: string; count: number; path: string }[] }
  | {
      type: 'country'
      country: string
      periodSpan: string
      total: number
      sections: {
        label: string
        anchor: string
        sites: {
          name: string
          path: string
          summary: string
          siteType: string
          period: string
          thumb: string
        }[]
      }[]
    }
  | { type: 'research'; slug: string }
  | { type: 'researchIndex' }
  | { type: 'article'; slug: string }
  | { type: 'articleIndex' }

declare global {
  interface Window {
    __AN_ROUTE__?: AnRoute
  }
}

export function anRoute(): AnRoute | undefined {
  return typeof window === 'undefined' ? undefined : window.__AN_ROUTE__
}
