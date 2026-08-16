/**
 * The route payload the server injects into every indexed page.
 *
 * The API serves these URLs (/news-archive/…, /sites/…, /research/…,
 * /articles/…) as the real app shell with the content already rendered
 * inside #root for crawlers. This object tells the React entry which page
 * to mount, and for stories it carries the whole payload so the page
 * renders with no extra request and no loading flash.
 *
 * Read it through seo/RouteContext: the entry calls readInjectedRoute()
 * once and hands the payload to RouteProvider — nothing else touches the
 * window global. Absent when the entry is opened directly, so every
 * consumer must handle undefined.
 *
 * story, storyArchive, sitesIndex and country describe what the server
 * injects TODAY (pipeline/seo_pages.py::_route_json). site, research,
 * article and the two index types describe the post-cutover contract
 * (react-ssr plan, Tasks 11-14): production still injects stubs ({id},
 * {slug}, {}) and those pages fetch their own data until the cutover
 * lands, so only read the extra fields behind a type check.
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

export interface StoryArchiveRoute {
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
    screenshotUrl?: string
  }[]
}

/** Post-cutover contract (react-ssr Tasks 11-14) — production still injects {id}/{slug}/{} stubs. */
export interface SiteRoute {
  type: 'site'
  id: string
  name: string
  country: string
  siteType: string
  /** Display string: curated period name, or a start/end year range. */
  period: string
  description: string
  coords: { lat: number | null; lon: number | null }
  image: {
    url: string
    author: string | null
    license: string | null
    commonsUrl: string | null
  } | null
  altNames: string[]
  news: { slug: string; headline: string }[]
  links: { title: string | null; url: string; contentType: string | null }[]
  parent: { name: string; path: string } | null
  siblings: { name: string; path: string }[]
}

export interface SitesIndexRoute {
  type: 'sitesIndex'
  countries: { name: string; count: number; path: string }[]
}

/**
 * One raw row of a country listing — snake_case deliberately: the API hands
 * the SQL row dicts through unchanged (api/routes/sites_html.py). Grouping,
 * period span and blurbs are display decisions and live in TypeScript
 * (src/seo/grouping.ts, src/seo/text.ts) since the react-ssr Task 10 cutover.
 */
export interface CountrySite {
  name: string
  /** Site-relative detail path, built server-side by site_path(). */
  path: string
  description: string | null
  site_type: string | null
  period_name: string | null
  period_start: number | null
  thumbnail_url: string | null
}

export interface CountryRoute {
  type: 'country'
  country: string
  sites: CountrySite[]
}

/** Post-cutover contract (react-ssr Tasks 11-14) — production still injects {id}/{slug}/{} stubs. */
export interface ResearchRoute {
  type: 'research'
  slug: string
  title: string
  summary: string
  author: string
  /** ISO date (YYYY-MM-DD), pre-formatted server-side like StoryRoute.publishedAt. */
  publishedAt: string
  heroImageUrl: string
}

/** Post-cutover contract (react-ssr Tasks 11-14) — production still injects {id}/{slug}/{} stubs. */
export interface ResearchIndexRoute {
  type: 'researchIndex'
  papers: { slug: string; title: string; summary: string }[]
}

/** Post-cutover contract (react-ssr Tasks 11-14) — production still injects {id}/{slug}/{} stubs. */
export interface ArticleRoute {
  type: 'article'
  slug: string
  title: string
  summary: string
  publishedAt: string
  heroImageUrl: string
}

/** Post-cutover contract (react-ssr Tasks 11-14) — production still injects {id}/{slug}/{} stubs. */
export interface ArticleIndexRoute {
  type: 'articleIndex'
  articles: { slug: string; title: string; summary: string }[]
}

export type AnRoute =
  | StoryRoute
  | StoryArchiveRoute
  | SiteRoute
  | SitesIndexRoute
  | CountryRoute
  | ResearchRoute
  | ResearchIndexRoute
  | ArticleRoute
  | ArticleIndexRoute
