/**
 * TypeScript types for Connector Status API
 */

export type ConnectorStatusType = 'ok' | 'warning' | 'error' | 'unknown' | 'unavailable'

/**
 * A sample item from test results
 */
export interface SampleItem {
  id: string
  title: string
  url: string
  thumbnail_url: string | null
}

/**
 * Result of a single test query against a connector
 */
export interface QueryTestResult {
  query_id: string
  query_name: string
  result_count: number
  sample_items: SampleItem[]
  response_time_ms: number
  error: string | null
}

/**
 * Test query labels for UI display
 */
export const TEST_QUERY_LABELS: Record<string, { icon: string; name: string }> = {
  machu_picchu: { icon: '🏔️', name: 'Machu Picchu' },
  stonehenge: { icon: '🗿', name: 'Stonehenge' },
  great_sphinx: { icon: '🦁', name: 'Great Sphinx' },
  roman_empire: { icon: '🏛️', name: 'Roman Empire' },
  inca_empire: { icon: '⛰️', name: 'Inca Empire' },
  egyptian_empire: { icon: '🏺', name: 'Egyptian Empire' },
}

/**
 * Ordered list of test query IDs (for consistent column ordering)
 */
export const TEST_QUERY_ORDER = [
  'machu_picchu',
  'stonehenge',
  'great_sphinx',
  'roman_empire',
  'inca_empire',
  'egyptian_empire',
]

export interface ConnectorStatus {
  connector_id: string
  connector_name: string
  category: string  // museums, sites, papers, 3d_models, maps, images, texts, inscriptions, numismatics, reference
  status: ConnectorStatusType
  available: boolean  // False for archived/stub connectors
  base_url: string | null  // Website URL for the connector
  last_ping: string | null
  last_sync: string | null
  error_message: string | null
  item_count: number | null
  response_time_ms: number | null
  tabs: string[]  // UI tabs this connector populates (Photos, Artworks, Maps, 3D, Artifacts, Books)
  // Test results (optional, populated when tests are run)
  test_results?: Record<string, QueryTestResult>
  api_docs_url?: string
}

export interface StatusSummary {
  total: number
  ok: number
  warning: number
  error: number
  unknown: number
  unavailable: number
}

export interface ConnectorsStatusResponse {
  connectors: ConnectorStatus[]
  summary: StatusSummary
  checked_at: string
}

/**
 * Response for single connector test
 */
export interface SingleConnectorTestResponse {
  connector_id: string
  test_results: Record<string, QueryTestResult>
}
