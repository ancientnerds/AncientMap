/**
 * The /api/stats/* contract (api/routes/founders_stats.py). One place, so a
 * renamed field is a compile error in every panel that reads it.
 */

import type { MapPoint } from './mapMath'

export type SessionKind = 'leser' | 'entdecker' | 'forscher' | 'sucher' | 'sonstige'

export interface DayBlock {
  views: number
  sessions: number
  /** Sessions with an event in the last five minutes. */
  live: number
}

export interface HourBucket {
  /** ISO timestamp of the hour (date_trunc), UTC. */
  hour: string
  views: number
  sessions: number
}

/** GET /api/stats/overview?days=N */
export interface Overview {
  today: DayBlock
  yesterday: DayBlock
  days: number
  sessions: { all: number; human: number }
  types: Partial<Record<SessionKind, number>>
  hours: HourBucket[]
}

/** GET /api/stats/map?days=N */
export interface MapData {
  points: MapPoint[]
}

export interface ContentRow {
  event_name: string
  /** Site name, story slug, paper path or search term. */
  label: string
  /** Country of the site — only on `site_open` rows. */
  country: string | null
  /** Result count of the search — only on `search` rows; 0 means nothing found. */
  results: number | null
  n: number
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

/** GET /api/stats/journeys?days=N */
export interface JourneysData {
  chains: JourneyChain[]
}

/** The five failures api/services/founders_stats.py problems() knows. */
export type ProblemKind = 'js_error' | 'slow_page' | 'broken_link' | 'shallow_exit' | 'empty_search'

export interface Problem {
  kind: ProblemKind
  /** What is broken — an error message, a path, a page type. */
  label: string
  /** Comparable severity: hits, weighted per kind. */
  score: number
  /** The numbers behind the score, in one sentence. */
  detail: string
}

/** GET /api/stats/problems?days=N */
export interface ProblemsData {
  problems: Problem[]
}

export interface SourceRow {
  source: string
  family: string
  sessions: number
}

/** GET /api/stats/sources?days=N */
export interface SourcesData {
  sources: SourceRow[]
}
