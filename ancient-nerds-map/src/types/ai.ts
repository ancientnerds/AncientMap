/**
 * TypeScript types for Lyra Chat functionality.
 */

import type { PipelineTrace } from './pipeline'

/**
 * Context type — where the chat was opened from.
 */
export type LyraContextType = 'global' | 'site' | 'empire' | 'news'

/**
 * A site that can be highlighted on the map.
 */
export interface SiteHighlight {
  id: string
  name: string
  lat: number
  lon: number
  site_type?: string
  period_name?: string
  country?: string
  thumbnail_url?: string
}

/**
 * A news item returned by the RAG pipeline.
 */
export interface NewsHighlight {
  headline: string
  summary?: string
  channel: string
  video_id: string
  video_title?: string
  timestamp_seconds?: number
  category?: string
  significance?: number
  relevance?: number
  date?: string
  post_text?: string
  screenshot_url?: string
  site_id?: string
  site_name?: string
  site_country?: string
  site_type?: string
  site_period_name?: string
  site_period_start?: number
  facts?: string[] | null
}

/**
 * A message in the Lyra chat conversation.
 */
export interface LyraMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  statusLines?: string[]
  sites?: SiteHighlight[]
  news?: NewsHighlight[]
  timestamp: Date
  isStreaming?: boolean
  confidence?: number | null
  tokens?: { input: number; output: number; voyage?: number }
  discoveries?: { newCount: number; total: number }
  pipelineTrace?: PipelineTrace
}

/**
 * Request body for POST /lyra/chat
 */
export interface LyraChatRequest {
  message: string
  context_type: LyraContextType
  context_id?: string
  context_year?: number
  turnstile_token: string
  history?: { role: string; content: string }[]
}

/**
 * Server-Sent Event types for streaming.
 */
export type SSEEventType = 'token' | 'status' | 'sites' | 'news' | 'done' | 'error' | 'achievements' | 'pipeline' | 'queue_info' | 'queue_position'

export interface SSETokenEvent {
  type: 'token'
  content: string
}

export interface SSESitesEvent {
  type: 'sites'
  sites: SiteHighlight[]
}

export interface SSENewsEvent {
  type: 'news'
  news: NewsHighlight[]
}

export interface SSEDoneEvent {
  type: 'done'
  metadata: {
    model?: string
    tool_calls?: number
    sites_found?: number
    avg_relevance?: number | null
    tokens?: { input: number; output: number; voyage?: number }
  }
}

export interface SSEErrorEvent {
  type: 'error'
  error: string
}

export interface SSEStatusEvent {
  type: 'status'
  content: string
}

export interface SSEAchievementsEvent {
  type: 'achievements'
  achievements: Array<{
    id: string
    name: string
    description: string
    tier: string
    icon: string
    reward_credits: number
    reward_xp: number
    reward_card_tier?: number | null
    reward_card_count: number
  }>
}

export interface SSEQueueInfoEvent {
  type: 'queue_info'
  position: number
  queue_length: number
}

export interface SSEQueuePositionEvent {
  type: 'queue_position'
  position: number       // -1 means "processing now"
  queue_length: number
  estimated_wait_seconds: number
}

export type SSEEvent = SSETokenEvent | SSEStatusEvent | SSESitesEvent | SSENewsEvent | SSEDoneEvent | SSEErrorEvent | SSEAchievementsEvent | SSEQueueInfoEvent | SSEQueuePositionEvent

/**
 * Summary of a saved conversation for the history panel.
 */
export interface ConversationSummary {
  id: string
  title: string
  updatedAt: number
}
