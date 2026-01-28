/**
 * TypeScript types for AI Agent functionality.
 */

/**
 * AI mode type - chat for quick responses, research for in-depth analysis.
 */
export type AIMode = 'chat' | 'research'

/**
 * Configuration for an AI mode.
 */
export interface AIModeConfig {
  model: string
  display_name: string
  description: string
  icon: string
  max_tokens: number
  examples: string[]
}

/**
 * Response from /api/ai/modes endpoint.
 */
export interface AIModesResponse {
  chat: AIModeConfig
  research: AIModeConfig
}

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
}

/**
 * A message in the AI chat conversation.
 */
export interface AIMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sites?: SiteHighlight[]
  timestamp: Date
  isStreaming?: boolean
}

/**
 * AI session information.
 */
export interface AISession {
  token: string
  verified: boolean
  expiresAt: Date
  messageCount: number
}

/**
 * Response from PIN verification endpoint.
 */
export interface PinVerifyResponse {
  verified: boolean
  session_token?: string
  expires_in?: number
  error?: string
  message?: string
  connected: boolean
  users_connected: number
}

/**
 * Response from chat endpoint.
 */
export interface ChatResponse {
  response: string
  sites: SiteHighlight[]
  query_metadata: {
    query_intent?: {
      filters: Record<string, unknown>
      site_types: string[]
      period?: string
      region?: string
    }
    sites_searched?: number
    sites_returned?: number
  }
}

/**
 * Server-Sent Event types for streaming.
 */
export type SSEEventType = 'token' | 'sites' | 'done' | 'error' | 'queued' | 'processing'

export interface SSETokenEvent {
  type: 'token'
  content: string
}

export interface SSESitesEvent {
  type: 'sites'
  sites: SiteHighlight[]
}

export interface SSEDoneEvent {
  type: 'done'
  metadata: {
    sites_searched: number
    sites_returned: number
    model?: string
    mode?: AIMode
  }
}

export interface SSEErrorEvent {
  type: 'error'
  error: string
}

export interface SSEQueuedEvent {
  type: 'queued'
  position: number
}

export interface SSEProcessingEvent {
  type: 'processing'
  status: string
}

export type SSEEvent = SSETokenEvent | SSESitesEvent | SSEDoneEvent | SSEErrorEvent | SSEQueuedEvent | SSEProcessingEvent

/**
 * AI service health status.
 */
export interface AIHealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'error'
  vector_store: {
    status: string
    document_count?: number
    error?: string
  }
  llm: {
    status: string
    model?: string
    loaded?: boolean
    error?: string
  }
}
