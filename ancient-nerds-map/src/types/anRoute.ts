/**
 * The route payload the server injects into every indexed page.
 *
 * The API serves these URLs (/news-archive/…, /sites/…, /research/…,
 * /articles/…) as the real app shell with the content already rendered
 * inside #root by the SSR sidecar. Every type carries its whole payload:
 * the sidecar renders from it, the browser hydrates the same tree from it
 * — no extra request, no loading flash (since Task 16 there is no other
 * renderer this shape could mirror).
 *
 * Read it through seo/RouteContext: the entry calls readInjectedRoute()
 * once and hands the payload to RouteProvider — nothing else touches the
 * window global. Absent when the entry is opened directly, so every
 * consumer must handle undefined.
 *
 * Every type carries raw snake_case rows since the react-ssr cutovers
 * (country/site Tasks 10/11, research/article Tasks 12/13, story/
 * storyArchive Task 14) — display formatting lives in src/seo/, not in
 * the payload.
 */

/**
 * One news story — the raw row fields api/routes/articles_html.py::story_page
 * hands through (react-ssr Task 14): NewsItem columns verbatim plus the
 * video/site joins and _related_stories(). The http(s) source filter, the
 * &t= video deeplink, screenshot absolutization and date formatting are
 * display decisions and live in src/seo/ and StoryPage.
 */
export interface StoryRoute {
  type: 'story'
  id: number
  headline: string
  summary: string
  facts: string[] | null
  /** Never null: public_stories_query filters on post_text IS NOT NULL. */
  post_text: string
  /** Matched site name, else the extractor's raw guess, else ''. */
  site_name: string
  site_id: string
  site_country: string
  /** /sites/{country}/{slug} serves curated sites only — gates the detail link. */
  site_curated: boolean
  /** Feeds the same SiteBadges the cards use. Null when no site matched. */
  site_type: string | null
  site_period_name: string | null
  site_period_start: number | null
  /** Lyra's 1–10 score; drives the same stamp the cards show. */
  significance: number | null
  screenshot_url: string | null
  youtube_url: string
  video_title: string
  channel_name: string
  /** Raw ISO timestamp: video publish date, else item creation. */
  published_at: string
  news_category: string | null
  /** LLM-derived JSON — only clean http(s) entries may render as links. */
  web_sources: { url?: string | null; title?: string | null; snippet?: string | null }[] | null
  timestamp_seconds: number | null
  speculative_tag: string | null
  related: { slug: string; headline: string; kind: string }[]
}

export interface StoryArchiveRoute {
  type: 'storyArchive'
  page: number
  total_pages: number
  total: number
  /** Archive search term (?q=) — '' on the plain listing. */
  q?: string
  stories: {
    slug: string
    headline: string
    summary: string
    published_at: string
    news_category: string | null
    site_name: string
    channel_name: string
    speculative_tag: string | null
    screenshot_url: string | null
  }[]
}

/**
 * One curated site detail page — the raw unified_sites row (snake_case,
 * api/routes/sites_html.py::site_detail hands it through unchanged) plus
 * _related_content() with ready-built paths. Display formatting (period
 * label, coordinate string) is a display decision and lives in
 * src/seo/display.ts, mirroring the CountryRoute convention.
 */
export interface SiteRoute {
  type: 'site'
  id: string
  name: string
  country: string
  site_type: string | null
  period_name: string | null
  period_start: number | null
  period_end: number | null
  description: string | null
  lat: number | null
  lon: number | null
  source_url: string | null
  /** card_stats enrichment — feeds the interactive SitePopup only. */
  best_wiki_url: string | null
  source_language: string | null
  description_citations: { n: number; url: string; title: string; domain: string }[] | null
  alt_names: string[]
  /** Hero from wiki_images with its Commons attribution (licence!). */
  image: {
    url: string
    author: string | null
    license: string | null
    commons_url: string | null
  } | null
  news: { slug: string; headline: string }[]
  links: { title: string | null; url: string; content_type: string | null }[]
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

/**
 * One public research paper — the raw paper_summary_kwargs fields the
 * route hands through (api/routes/research_html.py, react-ssr Task 12),
 * plus body_html: the published report rendered by the pipeline's
 * Python-markdown renderer (nh3-sanitized). The markdown renderer stays
 * Python on purpose — React only injects the finished HTML.
 */
export interface ResearchRoute {
  type: 'research'
  slug: string
  title: string
  summary: string | null
  /** published_by; null/absent means the Theo pipeline. */
  author: string | null
  /** Raw ISO timestamp from the row; date display is a TS decision. */
  published_at: string | null
  hero_image_url: string | null
  body_html: string
}

export interface ResearchIndexRoute {
  type: 'researchIndex'
  papers: { slug: string; title: string; summary: string | null }[]
}

/**
 * One weekly journal issue — the raw row fields the route hands through
 * (api/routes/articles_html.py, react-ssr Task 13) plus body_html, the
 * article markdown rendered by the pipeline's Python-markdown renderer
 * (nh3-sanitized). Same contract as ResearchRoute.
 */
export interface ArticleRoute {
  type: 'article'
  slug: string
  title: string
  summary: string | null
  /** Raw ISO timestamp from the row; date display is a TS decision. */
  published_at: string | null
  /** Journals carry no hero today — og:image falls back to the default. */
  hero_image_url: string | null
  body_html: string
}

export interface ArticleIndexRoute {
  type: 'articleIndex'
  articles: { slug: string; title: string; summary: string | null }[]
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
