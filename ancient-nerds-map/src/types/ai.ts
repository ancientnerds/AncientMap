/**
 * TypeScript types for Lyra Chat functionality.
 */

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
 * A source used by Lyra to generate a response.
 */
export interface LyraSource {
  type: 'video' | 'site' | 'web' | 'seshat' | 'qdrant' | 'channel'
  title: string
  url?: string
  detail?: string
}

/**
 * A message in the Lyra chat conversation.
 */
export interface LyraMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  statusLines?: string[]
  sites?: SiteHighlight[]
  news?: NewsHighlight[]
  timestamp: Date
  isStreaming?: boolean
  images?: string[]
  confidence?: number | null
  tokens?: { input: number; output: number; voyage?: number }
  sources?: LyraSource[]
}

/**
 * Request body for POST /lyra/chat
 */
export interface LyraChatRequest {
  message: string
  images?: { data: string }[]
  context_type: LyraContextType
  context_id?: string
  context_year?: number
  turnstile_token: string
  history?: { role: string; content: string }[]
}

/**
 * Server-Sent Event types for streaming.
 */
export type SSEEventType = 'token' | 'status' | 'sites' | 'news' | 'sources' | 'done' | 'error'

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

export interface SSESourcesEvent {
  type: 'sources'
  sources: LyraSource[]
}

export type SSEEvent = SSETokenEvent | SSEStatusEvent | SSESitesEvent | SSENewsEvent | SSESourcesEvent | SSEDoneEvent | SSEErrorEvent

/**
 * Summary of a saved conversation for the history panel.
 */
export interface ConversationSummary {
  id: string
  title: string
  updatedAt: number
}
