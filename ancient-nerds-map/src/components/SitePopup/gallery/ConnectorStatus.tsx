import { useState } from 'react'

interface ConnectorStatusProps {
  sourcesSearched: string[]
  sourcesFailed: string[]
  itemsBySource: Record<string, number>
  searchTimeMs: number
  isLoading: boolean
}

export function ConnectorStatus({
  sourcesSearched,
  sourcesFailed,
  itemsBySource,
  searchTimeMs,
  isLoading
}: ConnectorStatusProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const totalSources = sourcesSearched.length + sourcesFailed.length
  const successfulSources = sourcesSearched.filter(s => (itemsBySource[s] || 0) > 0)
  const emptySources = sourcesSearched.filter(s => (itemsBySource[s] || 0) === 0)

  if (isLoading && totalSources === 0) {
    return null
  }

  const formatTime = (ms: number) => {
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  return (
    <div className="connector-status">
      <button
        className="connector-status-header"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
      >
        <svg
          className={`connector-status-chevron ${isExpanded ? 'expanded' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
        <span className="connector-status-summary">
          {isLoading ? (
            <>Searching {totalSources} sources...</>
          ) : (
            <>
              {successfulSources.length} sources returned results
              {sourcesFailed.length > 0 && (
                <span className="connector-status-failed"> ({sourcesFailed.length} failed)</span>
              )}
              <span className="connector-status-time"> - {formatTime(searchTimeMs)}</span>
            </>
          )}
        </span>
      </button>

      {isExpanded && (
        <div className="connector-status-details">
          {successfulSources.length > 0 && (
            <div className="connector-status-section">
              <div className="connector-status-section-title">With Results</div>
              {successfulSources
                .sort((a, b) => (itemsBySource[b] || 0) - (itemsBySource[a] || 0))
                .map(source => (
                  <div key={source} className="connector-status-item success">
                    <span className="connector-status-icon">+</span>
                    <span className="connector-status-name">{formatSourceName(source)}</span>
                    <span className="connector-status-count">{itemsBySource[source]}</span>
                  </div>
                ))
              }
            </div>
          )}

          {emptySources.length > 0 && (
            <div className="connector-status-section">
              <div className="connector-status-section-title">No Results</div>
              {emptySources.map(source => (
                <div key={source} className="connector-status-item empty">
                  <span className="connector-status-icon">-</span>
                  <span className="connector-status-name">{formatSourceName(source)}</span>
                  <span className="connector-status-count">0</span>
                </div>
              ))}
            </div>
          )}

          {sourcesFailed.length > 0 && (
            <div className="connector-status-section">
              <div className="connector-status-section-title">Failed</div>
              {sourcesFailed.map(source => (
                <div key={source} className="connector-status-item failed">
                  <span className="connector-status-icon">!</span>
                  <span className="connector-status-name">{formatSourceName(source)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function formatSourceName(source: string): string {
  return source
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}
