/**
 * ConnectorStatusModal - Displays detailed status of all content connectors
 */

import { useState, useEffect, useMemo, memo, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { ConnectorStatus, ConnectorStatusType, QueryTestResult } from '../types/connectors'
import { TEST_QUERY_LABELS, TEST_QUERY_ORDER } from '../types/connectors'
import {
  useConnectorStatus,
  formatRelativeTime,
  formatResponseTime,
  getConnectorsLedClass,
} from '../hooks/useConnectorStatus'
import PinAuthModal from './PinAuthModal'

interface ConnectorStatusModalProps {
  isOpen: boolean
  onClose: () => void
}

type SortKey = 'name' | 'category' | 'status' | 'last_ping' | 'response_time' | 'items'
type SortDir = 'asc' | 'desc'
type StatusFilter = 'all' | ConnectorStatusType
type TabFilter = 'all' | string

const STATUS_ICONS: Record<ConnectorStatusType, string> = {
  ok: '\u2713',      // checkmark
  warning: '\u26A0', // warning triangle
  error: '\u2717',   // X mark
  unknown: '?',
  unavailable: '\u2014', // em dash
}

const STATUS_LABELS: Record<ConnectorStatusType, string> = {
  ok: 'OK',
  warning: 'Slow',
  error: 'Error',
  unknown: 'Unknown',
  unavailable: 'Unavailable',
}

const CATEGORY_LABELS: Record<string, string> = {
  museums: 'Museums',
  sites: 'Sites',
  papers: 'Papers',
  '3d_models': '3D Models',
  maps: 'Maps',
  images: 'Images',
  texts: 'Texts',
  inscriptions: 'Inscriptions',
  numismatics: 'Coins',
  reference: 'Reference',
  other: 'Other',
  unknown: 'Unknown',
}

function ConnectorStatusModal({ isOpen, onClose }: ConnectorStatusModalProps) {
  const { data, summary, loading, error, refresh, runAllTests, runSingleTest, testingConnectorId } = useConnectorStatus()
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [tabFilter, setTabFilter] = useState<TabFilter>('all')
  const [refreshing, setRefreshing] = useState(false)
  const [showAuthModal, setShowAuthModal] = useState(false)
  const [adminAuthed, setAdminAuthed] = useState(false)
  // What to do after PIN auth succeeds
  const [pendingAction, setPendingAction] = useState<'refresh' | 'showTests' | 'runAllTests' | { type: 'runSingleTest', id: string } | null>(null)
  // Test mode state
  const [showTests, setShowTests] = useState(false)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [runningTests, setRunningTests] = useState(false)

  // Get unique tabs from all connectors
  const availableTabs = useMemo(() => {
    if (!data?.connectors) return []
    const tabSet = new Set<string>()
    data.connectors.forEach(c => {
      (c.tabs ?? []).forEach(tab => tabSet.add(tab))
    })
    return Array.from(tabSet).sort()
  }, [data?.connectors])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  // Gate an action behind admin PIN — if already authed, run immediately
  const requireAdmin = useCallback((action: typeof pendingAction) => {
    if (adminAuthed) {
      // Already verified this session — run directly
      setPendingAction(action)
      // Trigger via effect below
    } else {
      setPendingAction(action)
      setShowAuthModal(true)
    }
  }, [adminAuthed])

  const handleAuthSuccess = useCallback(async () => {
    setShowAuthModal(false)
    setAdminAuthed(true)
  }, [])

  // Execute pending action once admin is authed
  const executePendingAction = useCallback(async () => {
    if (!adminAuthed || !pendingAction) return
    const action = pendingAction
    setPendingAction(null)

    if (action === 'refresh') {
      setRefreshing(true)
      await refresh(true)
      setRefreshing(false)
    } else if (action === 'showTests') {
      setShowTests(true)
    } else if (action === 'runAllTests') {
      setRunningTests(true)
      await runAllTests()
      setRunningTests(false)
    } else if (typeof action === 'object' && action.type === 'runSingleTest') {
      await runSingleTest(action.id)
    }
  }, [adminAuthed, pendingAction, refresh, runAllTests, runSingleTest])

  // Fire pending action when auth completes
  useEffect(() => {
    if (adminAuthed && pendingAction) {
      executePendingAction()
    }
  }, [adminAuthed, pendingAction, executePendingAction])

  const handleRefreshClick = useCallback(() => {
    requireAdmin('refresh')
  }, [requireAdmin])

  const handleRunAllTests = useCallback(() => {
    requireAdmin('runAllTests')
  }, [requireAdmin])

  const handleRunSingleTest = useCallback((connectorId: string) => {
    requireAdmin({ type: 'runSingleTest', id: connectorId })
  }, [requireAdmin])

  const handleShowTestsToggle = useCallback((checked: boolean) => {
    if (checked && !adminAuthed) {
      requireAdmin('showTests')
    } else {
      setShowTests(checked)
    }
  }, [adminAuthed, requireAdmin])

  // Toggle row expansion
  const toggleRowExpansion = useCallback((connectorId: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      if (next.has(connectorId)) {
        next.delete(connectorId)
      } else {
        next.add(connectorId)
      }
      return next
    })
  }, [])

  const sortedConnectors = useMemo(() => {
    if (!data?.connectors) return []

    let filtered = data.connectors
    if (statusFilter !== 'all') {
      filtered = filtered.filter(c => c.status === statusFilter)
    }
    if (tabFilter !== 'all') {
      filtered = filtered.filter(c => (c.tabs ?? []).includes(tabFilter))
    }

    return [...filtered].sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'name':
          cmp = a.connector_name.localeCompare(b.connector_name)
          break
        case 'category':
          cmp = a.category.localeCompare(b.category)
          break
        case 'status':
          const statusOrder = { ok: 0, warning: 1, error: 2, unavailable: 3, unknown: 4 }
          cmp = (statusOrder[a.status as ConnectorStatusType] ?? 5) -
                (statusOrder[b.status as ConnectorStatusType] ?? 5)
          break
        case 'last_ping':
          const aTime = a.last_ping ? new Date(a.last_ping).getTime() : 0
          const bTime = b.last_ping ? new Date(b.last_ping).getTime() : 0
          cmp = bTime - aTime // Most recent first
          break
        case 'response_time':
          cmp = (a.response_time_ms ?? Infinity) - (b.response_time_ms ?? Infinity)
          break
        case 'items':
          cmp = (b.item_count ?? 0) - (a.item_count ?? 0)
          break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [data?.connectors, sortKey, sortDir, statusFilter, tabFilter])

  if (!isOpen) return null

  const SortHeader = ({ label, sortKeyValue }: { label: string; sortKeyValue: SortKey }) => (
    <th
      className={`sortable ${sortKey === sortKeyValue ? 'sorted' : ''}`}
      onClick={() => handleSort(sortKeyValue)}
    >
      {label}
      {sortKey === sortKeyValue && (
        <span className="sort-indicator">{sortDir === 'asc' ? ' \u25B2' : ' \u25BC'}</span>
      )}
    </th>
  )

  const modalContent = (
    <div className="connector-status-modal-overlay" onClick={onClose}>
      <div className="connector-status-modal" onClick={e => e.stopPropagation()}>
        <button className="popup-close connector-close-right" onClick={onClose} title="Close">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        <div className="connector-status-content">
          <div className="connector-status-header">
            <h2>
              <span className={`connectors-led ${getConnectorsLedClass(summary)}`} />
              Connector Status
            </h2>
            <div className="connector-status-summary">
              <button
                className={`summary-item ok ${statusFilter === 'ok' ? 'active' : ''}`}
                onClick={() => setStatusFilter(statusFilter === 'ok' ? 'all' : 'ok')}
                title="Click to filter by OK status"
              >
                {summary.ok} OK
              </button>
              <button
                className={`summary-item warning ${statusFilter === 'warning' ? 'active' : ''}`}
                onClick={() => setStatusFilter(statusFilter === 'warning' ? 'all' : 'warning')}
                title="Click to filter by Slow status"
              >
                {summary.warning} Slow
              </button>
              <button
                className={`summary-item error ${statusFilter === 'error' ? 'active' : ''}`}
                onClick={() => setStatusFilter(statusFilter === 'error' ? 'all' : 'error')}
                title="Click to filter by Error status"
              >
                {summary.error} Error
              </button>
              {summary.unavailable > 0 && (
                <button
                  className={`summary-item unavailable ${statusFilter === 'unavailable' ? 'active' : ''}`}
                  onClick={() => setStatusFilter(statusFilter === 'unavailable' ? 'all' : 'unavailable')}
                  title="Click to filter by Unavailable status"
                >
                  {summary.unavailable} Unavailable
                </button>
              )}
              {summary.unknown > 0 && (
                <button
                  className={`summary-item unknown ${statusFilter === 'unknown' ? 'active' : ''}`}
                  onClick={() => setStatusFilter(statusFilter === 'unknown' ? 'all' : 'unknown')}
                  title="Click to filter by Unknown status"
                >
                  {summary.unknown} Unknown
                </button>
              )}
            </div>
            <p className="connector-status-modal-description">
              Content is aggregated from museums, libraries, and archives worldwide.
              This system is in beta — not all connectors are fully operational yet and
              results may be incomplete or inaccurate. Actively being developed.
            </p>
          </div>

          <div className="connector-status-controls">
            <div className="filter-group">
              <label>Tabs:</label>
              <select
                value={tabFilter}
                onChange={e => setTabFilter(e.target.value as TabFilter)}
              >
                <option value="all">All Tabs</option>
                {availableTabs.map(tab => (
                  <option key={tab} value={tab}>{tab}</option>
                ))}
              </select>
            </div>
            <label className="test-toggle">
              <input
                type="checkbox"
                checked={showTests}
                onChange={e => handleShowTestsToggle(e.target.checked)}
              />
              Show Tests
            </label>
            {showTests && (
              <button
                className="run-tests-btn"
                onClick={handleRunAllTests}
                disabled={runningTests || loading}
                title="Run test queries against all connectors"
              >
                {runningTests ? (
                  <>
                    <span className="spinner" />
                    Testing...
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                    Run All Tests
                  </>
                )}
              </button>
            )}
            <button
              className="refresh-btn"
              onClick={handleRefreshClick}
              disabled={refreshing || loading}
              title="Refresh all connectors (requires admin PIN)"
            >
              {refreshing || loading ? (
                <>
                  <span className="spinner" />
                  Checking...
                </>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M23 4v6h-6" />
                    <path d="M1 20v-6h6" />
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                  </svg>
                  Refresh
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="connector-status-error">
              Failed to load status: {error}
            </div>
          )}

          <div className="connector-status-table-wrapper">
            <table className={`connector-status-table ${showTests ? 'show-tests' : ''}`}>
              <thead>
                <tr>
                  <SortHeader label="Connector" sortKeyValue="name" />
                  <SortHeader label="Category" sortKeyValue="category" />
                  <th>Tabs</th>
                  <SortHeader label="Status" sortKeyValue="status" />
                  <SortHeader label="Last Ping" sortKeyValue="last_ping" />
                  <SortHeader label="Response" sortKeyValue="response_time" />
                  {showTests && (
                    <>
                      <th className="test-header" title="API Documentation">Docs</th>
                      {TEST_QUERY_ORDER.map(qid => (
                        <th
                          key={qid}
                          className="test-header test-query-header"
                          title={TEST_QUERY_LABELS[qid]?.name ?? qid}
                        >
                          {TEST_QUERY_LABELS[qid]?.icon ?? '?'}
                        </th>
                      ))}
                      <th className="test-header">Actions</th>
                    </>
                  )}
                  {!showTests && <th>Error</th>}
                </tr>
              </thead>
              <tbody>
                {sortedConnectors.length === 0 ? (
                  <tr>
                    <td colSpan={showTests ? 14 : 7} className="no-results">
                      {loading ? 'Loading...' : 'No connectors found'}
                    </td>
                  </tr>
                ) : (
                  sortedConnectors.map(connector => (
                    <ConnectorRow
                      key={connector.connector_id}
                      connector={connector}
                      showTests={showTests}
                      isExpanded={expandedRows.has(connector.connector_id)}
                      onToggleExpand={() => toggleRowExpansion(connector.connector_id)}
                      onRunTest={() => handleRunSingleTest(connector.connector_id)}
                      isTesting={testingConnectorId === connector.connector_id}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>

          {data?.checked_at && (
            <div className="connector-status-footer">
              Last updated: {formatRelativeTime(data.checked_at)}
            </div>
          )}
        </div>
      </div>
    </div>
  )

  return (
    <>
      {createPortal(modalContent, document.body)}
      <PinAuthModal
        isOpen={showAuthModal}
        onClose={() => { setShowAuthModal(false); setPendingAction(null) }}
        onSuccess={handleAuthSuccess}
        variant="admin"
      />
    </>
  )
}

interface ConnectorRowProps {
  connector: ConnectorStatus
  showTests: boolean
  isExpanded: boolean
  onToggleExpand: () => void
  onRunTest: () => void
  isTesting: boolean
}

/**
 * Get test result indicator for a query
 */
function getTestIndicator(testResults: Record<string, QueryTestResult> | undefined, queryId: string): { icon: string; className: string; title: string } {
  if (!testResults || !testResults[queryId]) {
    return { icon: '-', className: 'test-none', title: 'Not tested' }
  }

  const result = testResults[queryId]
  if (result.error) {
    return { icon: '✗', className: 'test-error', title: `Error: ${result.error}` }
  }
  if (result.result_count === 0) {
    return { icon: '0', className: 'test-zero', title: 'No results' }
  }
  return {
    icon: String(result.result_count),
    className: 'test-ok',
    title: `${result.result_count} results in ${Math.round(result.response_time_ms)}ms`
  }
}

const ConnectorRow = memo(({ connector, showTests, isExpanded, onToggleExpand, onRunTest, isTesting }: ConnectorRowProps) => {
  const status = connector.status as ConnectorStatusType
  const tabs = connector.tabs ?? []
  const [faviconError, setFaviconError] = useState(false)

  // Extract domain for favicon (request larger size for crisp display)
  const getFaviconUrl = (url: string) => {
    try {
      const domain = new URL(url).hostname
      return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`
    } catch {
      return null
    }
  }

  const faviconUrl = connector.base_url ? getFaviconUrl(connector.base_url) : null
  const hasTestResults = connector.test_results && Object.keys(connector.test_results).length > 0
  const hasSampleItems = hasTestResults && Object.values(connector.test_results!).some(r => r.sample_items.length > 0)

  return (
    <>
      <tr className={`status-${status} ${isExpanded ? 'expanded' : ''}`}>
        <td className="connector-name">
          {showTests && hasSampleItems && (
            <button
              className="expand-btn"
              onClick={onToggleExpand}
              title={isExpanded ? 'Collapse' : 'Expand to see sample items'}
            >
              {isExpanded ? '▼' : '▶'}
            </button>
          )}
          {faviconUrl && !faviconError && (
            <img
              src={faviconUrl}
              alt=""
              className="connector-favicon"
              onError={() => setFaviconError(true)}
            />
          )}
          {connector.base_url ? (
            <a
              href={connector.base_url}
              target="_blank"
              rel="noopener noreferrer"
              className="connector-link"
              title={`Open ${connector.connector_name} website`}
            >
              {connector.connector_name}
            </a>
          ) : (
            connector.connector_name
          )}
        </td>
        <td className="connector-category">
          {CATEGORY_LABELS[connector.category] ?? connector.category}
        </td>
        <td className="connector-tabs">
          {tabs.length > 0 ? tabs.join(', ') : '-'}
        </td>
        <td className={`connector-status status-${status}`}>
          <span className="status-icon">{STATUS_ICONS[status]}</span>
          {STATUS_LABELS[status]}
        </td>
        <td className="connector-ping">{formatRelativeTime(connector.last_ping)}</td>
        <td className="connector-response">
          {formatResponseTime(connector.response_time_ms)}
        </td>
        {showTests ? (
          <>
            <td className="connector-docs">
              {connector.api_docs_url ? (
                <a
                  href={connector.api_docs_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Open API documentation"
                >
                  📄
                </a>
              ) : '-'}
            </td>
            {TEST_QUERY_ORDER.map(qid => {
              const indicator = getTestIndicator(connector.test_results, qid)
              return (
                <td
                  key={qid}
                  className={`test-cell ${indicator.className}`}
                  title={indicator.title}
                >
                  {indicator.icon}
                </td>
              )
            })}
            <td className="connector-actions">
              <button
                className="run-test-btn"
                onClick={onRunTest}
                disabled={isTesting || !connector.available}
                title={connector.available ? 'Run tests for this connector' : 'Connector unavailable'}
              >
                {isTesting ? (
                  <span className="spinner-small" />
                ) : (
                  '▶'
                )}
              </button>
            </td>
          </>
        ) : (
          <td className="connector-error" title={connector.error_message ?? undefined}>
            {connector.error_message
              ? connector.error_message.length > 40
                ? connector.error_message.substring(0, 40) + '...'
                : connector.error_message
              : '-'
            }
          </td>
        )}
      </tr>
      {/* Expanded row with sample items */}
      {showTests && isExpanded && hasTestResults && (
        <tr className="expanded-row">
          <td colSpan={14}>
            <div className="sample-items-grid">
              {TEST_QUERY_ORDER.map(qid => {
                const result = connector.test_results?.[qid]
                if (!result || result.sample_items.length === 0) return null
                return (
                  <div key={qid} className="query-samples">
                    <h4>
                      {TEST_QUERY_LABELS[qid]?.icon} {TEST_QUERY_LABELS[qid]?.name}
                      <span className="result-count">({result.result_count} results)</span>
                    </h4>
                    <div className="sample-items">
                      {result.sample_items.map(item => (
                        <a
                          key={item.id}
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="sample-item"
                          title={item.title}
                        >
                          {item.thumbnail_url ? (
                            <img
                              src={item.thumbnail_url}
                              alt=""
                              className="sample-thumbnail"
                              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                            />
                          ) : (
                            <div className="sample-no-thumb">📷</div>
                          )}
                          <span className="sample-title">{item.title}</span>
                        </a>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </td>
        </tr>
      )}
    </>
  )
})

ConnectorRow.displayName = 'ConnectorRow'

export default memo(ConnectorStatusModal)
