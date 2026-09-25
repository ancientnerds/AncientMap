/**
 * The /api/stats/* contract (api/routes/founders_stats.py). One place, so a
 * renamed field is a compile error in every panel that reads it.
 */

import type { MapPoint } from './mapMath'

export type SessionKind = 'reader' | 'explorer' | 'researcher' | 'searcher' | 'other'

export interface HourBucket {
  /** Start of the hour, UTC. Always 48 buckets, including the empty ones. */
  hour: string
  /** Sessions with any event in this hour. */
  sessions: number
  /** Of those, the confirmed-human ones — the strip's lower segment. */
  human: number
  /** Of those, the ones an AI assistant sent. Overlaps `human`; never added
   *  to it. Too rare to draw (13 in 7 days), so it lives in the legend. */
  ai: number
}

/** GET /api/stats/overview?days=N */
export interface Overview {
  days: number
  /** `human` and `ai` are both subsets of `all` and overlap each other. */
  sessions: { all: number; human: number; ai: number }
  types: Partial<Record<SessionKind, number>>
  hours: HourBucket[]
}

/** GET /api/stats/map?days=N */
export interface MapData {
  points: MapPoint[]
}

export interface CountryCount {
  /** ISO-3166 alpha-2 from Umami, or "??" when it could not place the visitor. */
  country: string
  sessions: number
}

/** One tile of the pulse panel: the total and the flags behind it. */
export interface CountryWindow {
  /** Human sessions — every session on the live tile, where nobody has acted yet. */
  sessions: number
  /** Every session in the window, human or not. */
  all: number
  /** Biggest first — the panel clips the row, so the order is what survives. */
  countries: CountryCount[]
}

/** GET /api/stats/countries — fixed windows, not the page's range switch. */
export interface CountriesData {
  now: CountryWindow
  today: CountryWindow
  d7: CountryWindow
  d30: CountryWindow
}

export interface ContentRow {
  event_name: string
  /** Site name, story slug, paper path or search term. */
  label: string
  /** Country of the site — only on `site_open` rows. */
  country: string | null
  /** Result count of the search — only on `search` rows; 0 means nothing found. */
  results: number | null
  /** Opens (or searches). */
  n: number
  /** Sessions behind `n`. Absent from an API older than this bundle (ci.yml
   *  swaps the frontend first); the panel then ranks by `n`. */
  visitors?: number
}

/** GET /api/stats/content?days=N */
export interface ContentData {
  sites: ContentRow[]
  stories: ContentRow[]
  papers: ContentRow[]
  searches: ContentRow[]
}

export interface FeedbackItem {
  created_at: string
  url_path: string | null
  prompt: string | null
  answer: string | null
  text: string | null
  /** What was rated — whichever of these the event carried. */
  site: string | null
  country: string | null
  paper: string | null
  journal: string | null
  story: string | null
}

/** GET /api/stats/feedback?days=N */
export interface FeedbackData {
  items: FeedbackItem[]
}

export interface JourneyChain {
  /** "google → story → site_open → site": entry source, then page types and actions. */
  chain: string
  sessions: number
}

export interface EntryPage {
  page: string
  sessions: number
  /** Of those, how many went no further. */
  stopped: number
}
export interface ExitPage {
  page: string
  sessions: number
  /** Views of this page type across all human sessions — the row prints
   *  "12 of 20", never a percentage: 46 human sessions is too few for one. */
  views: number
}
export interface PageEnds {
  sessions: number
  /** Human sessions with exactly one page view. There is no `no_page` key:
   *  a session without a page view is not `human` (stats_analysis.py 9d), so
   *  that number would be 0 forever. */
  one_page: number
  moving: number
  entries: EntryPage[]
  exits: ExitPage[]
}
export interface OutboundLink {
  host: string
  clicks: number
  visitors: number
}

export interface ReadingPage {
  page: string
  /** One count per mark of `ReadingFunnel.steps`, in that order — sessions
   *  that reached it. Parallel arrays, so a row is read against `steps`. */
  sessions: number[]
}
/**
 * How far visitors read, folded out of the same rows as the chains above
 * (stats_analysis.py reading_funnel). Counts only, never a share: story
 * 17/15/13/10, country 2/2/2/2, site 1/1/1/1 over the seven days to
 * 2026-09-19, and twenty readers cannot carry a percentage — a percentage is
 * what a founder would read one as.
 */
export interface ReadingFunnel {
  /** The percent marks src/analytics/boot.ts fires: 25, 50, 75, 100. */
  steps: number[]
  /** Sessions that scrolled at all — the sample size the panel's note has to
   *  name. boot.ts only fires on a real scroll event, so this is never the
   *  number of page views. */
  readers: number
  pages: ReadingPage[]
}

/** GET /api/stats/journeys?days=N */
export interface JourneysData {
  chains: JourneyChain[]
  pages: PageEnds
  outbound: OutboundLink[]
  reading: ReadingFunnel
}

/** The six failures pipeline/stats_analysis.py problems() knows. */
export type ProblemKind =
  | 'js_error'
  | 'slow_page'
  | 'broken_link'
  | 'shallow_exit'
  | 'empty_search'
  /** The globe's WebGL context died — the page is over for that visitor. */
  | 'webgl_lost'

/**
 * Who a problem last hit. Cookieless analytics has no user: this is the
 * session Umami recognises for one calendar month, shortened to eight
 * characters so two rows can be read as the same visitor.
 */
export interface Visitor {
  session: string
  country: string | null
  device: string | null
  browser: string | null
}

export interface Problem {
  kind: ProblemKind
  /** What is broken — an error message, a path, a page type. */
  label: string
  /** Comparable severity: hits, weighted per kind. */
  score: number
  /** The numbers behind the score, in one sentence. */
  detail: string
  /** ISO timestamp of the last occurrence; null when the row cannot date itself. */
  at: string | null
  last: Visitor | null
}

/** GET /api/stats/problems?days=N */
export interface ProblemsData {
  problems: Problem[]
}

export interface SourceRow {
  source: string
  family: string
  sessions: number
  /** Page views, so the panel can put this next to nginx's request count. */
  views: number
}

export interface LogFamily {
  family: string
  visits: number
  bots: number
}
export interface LogHost {
  host: string
  visits: number
}
export interface LogStatus {
  status: number
  visits: number
}
/** What nginx saw in the same window — human page requests only. */
export interface LogCoverage {
  covered_from: string
  covered_days: number
  lines: number
  /** Arrivals from a host in no known family that was seen only once in the
   *  window — referrer spam, and counted out of `families` and `hosts`
   *  (pipeline/referral_log.py UNKNOWN_HOST_MIN). */
  unverified: number
  /** Pages Chrome prefetched for a Google result page (Sec-Purpose), which
   *  nobody has looked at yet — never an arrival (pipeline/referral_log.py). */
  prefetched: number
  families: LogFamily[]
  hosts: LogHost[]
  statuses: LogStatus[]
}

/** GET /api/stats/sources?days=N */
export interface SourcesData {
  sources: SourceRow[]
  /** null when /app/logs/referrals.log is not mounted — every dev box. */
  log: LogCoverage | null
  /** An English sentence naming the path and the bind, when `log` is null. */
  log_reason: string | null
}

/** A spread of globe times in ms. `median` is null below five samples;
 *  `min`/`max` are null with none. */
export interface GlobeTimes {
  min: number | null
  median: number | null
  max: number | null
  samples: number
}

/** How the globe loads that never fired globe_ready ended (stats_analysis.globe_funnel).
 *  The four counts sum to `gave_up`. Per session, capped by its unreached loads,
 *  in this order: unsupported, error, abandoned; the rest is `no_signal`. */
export interface GlobeEndings {
  unsupported: number
  error: number
  abandoned: number
  no_signal: number
}

/** GET /api/stats/globe?days=N — the denominator is page loads, not sessions,
 *  and only loads of the build that reports its endings (the globe-load deploy
 *  of 2026-09-24) count: SQL_GLOBE leaves the earlier ones out. */
export interface GlobeData {
  loads: number
  reached: number
  gave_up: number
  sessions: { all: number; reached: number }
  ready_ms: GlobeTimes
  /** Absent from an API older than this bundle (ci.yml swaps the frontend
   *  first); GlobeReach says so instead of drawing the split. */
  not_reached: GlobeEndings
  /** How long the counted `abandoned` loads had waited when they left. */
  abandon_ms: GlobeTimes
  /** Phone loads that stayed at the phone gate - the gate doing its job, in
   *  none of the counts above. Absent from an older API. */
  gate_stops?: number
  /** Loads and arrivals per kind of machine (stats_analysis DEVICE_GROUPS:
   *  laptop and desktop are one). Absent from an older API. */
  by_device?: GlobeDevice[]
}

export interface GlobeDevice {
  /** 'desktop' | 'mobile' | 'tablet' | 'unknown' */
  device: string
  loads: number
  reached: number
}

export interface Cluster {
  screen: string | null
  browser: string | null
  os: string | null
  sessions: number
}
/** GET /api/stats/clusters?days=N */
export interface ClustersData {
  /** How many session ids had to share one path inside one clock minute to
   *  count. Every event, not only page views: these clients fire events
   *  without ever sending one (umami_db.py SQL_CLUSTERS). */
  min_ids: number
  flagged: number
  clusters: Cluster[]
}

/** A visitor who is here now, and what they have open. Extends Visitor. */
export interface LiveVisitor extends Visitor {
  page: string
  title: string
  /** Path of the page they have open. The row links to it on the main host. */
  path: string
  /** Seconds since this page view started. */
  here: number
  last_seen: string
}
/** GET /api/stats/live — fixed windows, not the page's range switch. */
export interface LiveData {
  window_minutes: number
  lookback_hours: number
  /** Visitors in the window. `shown` is how many of them the list prints. */
  total: number
  shown: number
  visitors: LiveVisitor[]
  /** Only when `total` is 0: the most recent visitor of the lookback. */
  last: LiveVisitor | null
}

export interface MemberAct {
  act: string
  n: number
  /** Distinct actors on this one table. Not comparable across acts: three of
   *  the four key on discord_users.id, research_requests on a snowflake. */
  by: number
  at: string | null
}
/** GET /api/stats/members — all-time counts, never a window. */
export interface MembersData {
  members: number
  founders: number
  newest_signup: string | null
  /** The newest login of a FOUNDER, matching the tile it sits under. */
  last_login: string | null
  acts: MemberAct[]
}

export interface DeviceCount {
  /** desktop / mobile / tablet, plus "unknown" when Umami saw no screen size.
   *  Umami's own "laptop" is a desktop machine under 1920 px and is folded
   *  into desktop (stats_analysis.py DEVICE_GROUPS); anything Umami invents
   *  later arrives verbatim, so the string is not a union. */
  device: string
  sessions: number
}
export interface LanguageCount {
  /** The full tag ("en-US") in `languages`, the primary subtag ("en") in
   *  `language_groups` — the same sessions, read at two resolutions. */
  language: string
  sessions: number
}
/** GET /api/stats/devices?days=N — counts only. */
export interface DevicesData {
  /** The denominator: every session in the window. At this size a share has
   *  to be printed with the count it came from (laptop 117, mobile 45,
   *  desktop 6 of 168 sessions = about 27 % phones, not 88 %). */
  sessions: number
  devices: DeviceCount[]
  /** The tag the browser asked for, which is what a row is titled with. */
  languages: LanguageCount[]
  /** Folded onto the primary subtag: en-US and en-GB are one audience, and
   *  "en 114 of 168" is the only headline five small rows carry. */
  language_groups: LanguageCount[]
}
