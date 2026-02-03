/**
 * Hook for fetching and managing connector status
 */

import { useState, useEffect, useCallback } from 'react'
import type {
  ConnectorsStatusResponse,
  StatusSummary,
  QueryTestResult,
  SingleConnectorTestResponse,
} from '../types/connectors'

// API base URL - uses environment variable or relative path (same pattern as contentService)
const API_BASE = import.meta.env.VITE_API_URL || '/api'

interface UseConnectorStatusResult {
  data: ConnectorsStatusResponse | null
  summary: StatusSummary
  loading: boolean
  error: string | null
  refresh: (checkLive?: boolean) => Promise<void>
  lastChecked: Date | null
  // Test-related methods
  runAllTests: () => Promise<void>
  runSingleTest: (connectorId: string) => Promise<Record<string, QueryTestResult> | null>
  testingConnectorId: string | null
}

const defaultSummary: StatusSummary = {
  total: 0,
  ok: 0,
  warning: 0,
  error: 0,
  unknown: 0,
  unavailable: 0,
}

export function useConnectorStatus(
  autoRefreshInterval?: number  // in ms, e.g., 300000 for 5 minutes
): UseConnectorStatusResult {
  const [data, setData] = useState<ConnectorsStatusResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [testingConnectorId, setTestingConnectorId] = useState<string | null>(null)

  const fetchStatus = useCallback(async (checkLive = false) => {
    setLoading(true)
    setError(null)

    try {
      // Build URL same pattern as contentService.ts
      const url = new URL(`${API_BASE}/content/connectors/status`, window.location.origin)
      if (checkLive) {
        url.searchParams.set('check_live', 'true')
      }

      const response = await fetch(url.toString(), {
        headers: { Accept: 'application/json' },
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch connector status: ${response.statusText}`)
      }

      const result: ConnectorsStatusResponse = await response.json()
      setData(result)
      setLastChecked(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  // Run tests for all connectors
  const runAllTests = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const url = new URL(`${API_BASE}/content/connectors/status`, window.location.origin)
      url.searchParams.set('include_tests', 'true')
      url.searchParams.set('check_live', 'true')
      url.searchParams.set('timeout', '60')

      const response = await fetch(url.toString(), {
        headers: { Accept: 'application/json' },
      })

      if (!response.ok) {
        throw new Error(`Failed to run connector tests: ${response.statusText}`)
      }

      const result: ConnectorsStatusResponse = await response.json()
      setData(result)
      setLastChecked(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  // Run tests for a single connector
  const runSingleTest = useCallback(async (connectorId: string): Promise<Record<string, QueryTestResult> | null> => {
    setTestingConnectorId(connectorId)

    try {
      const url = new URL(`${API_BASE}/content/connectors/status`, window.location.origin)
      url.searchParams.set('run_tests_for', connectorId)
      url.searchParams.set('timeout', '30')

      const response = await fetch(url.toString(), {
        headers: { Accept: 'application/json' },
      })

      if (!response.ok) {
        throw new Error(`Failed to run tests for ${connectorId}: ${response.statusText}`)
      }

      const result: SingleConnectorTestResponse = await response.json()

      // Update single connector in state
      setData(prev => {
        if (!prev) return prev
        return {
          ...prev,
          connectors: prev.connectors.map(c =>
            c.connector_id === connectorId
              ? { ...c, test_results: result.test_results }
              : c
          ),
        }
      })

      return result.test_results
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      return null
    } finally {
      setTestingConnectorId(null)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    fetchStatus(false)
  }, [fetchStatus])

  // Auto-refresh if interval provided
  useEffect(() => {
    if (!autoRefreshInterval) return

    const interval = setInterval(() => {
      fetchStatus(false)
    }, autoRefreshInterval)

    return () => clearInterval(interval)
  }, [autoRefreshInterval, fetchStatus])

  return {
    data,
    summary: data?.summary ?? defaultSummary,
    loading,
    error,
    refresh: fetchStatus,
    lastChecked,
    runAllTests,
    runSingleTest,
    testingConnectorId,
  }
}

/**
 * Determine LED class based on status summary
 */
export function getConnectorsLedClass(summary: StatusSummary): string {
  if (summary.total === 0) {
    return 'unknown'
  }
  // Count active connectors (excluding unavailable ones)
  const activeTotal = summary.total - (summary.unavailable || 0)
  if (activeTotal === 0) {
    return 'unknown'  // All connectors are unavailable
  }
  if (summary.error === activeTotal) {
    return 'error'
  }
  if (summary.ok === activeTotal || summary.ok + (summary.unavailable || 0) === summary.total) {
    return 'connected'  // All active connectors are OK
  }
  if (summary.error > 0 || summary.warning > 0) {
    return 'warning'
  }
  if (summary.unknown === activeTotal) {
    return 'unknown'
  }
  return 'connected'
}

/**
 * Format relative time for display
 */
export function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return 'Never'

  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSeconds < 60) return 'Just now'
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return `${diffDays}d ago`
}

/**
 * Format response time for display
 */
export function formatResponseTime(ms: number | null): string {
  if (ms === null) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
