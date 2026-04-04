/**
 * TheoReportOverlay — Full-screen report viewer for completed research.
 * Uses ReactMarkdown with custom site: link handling (same as LyraChatModal).
 */

import { useState, useMemo, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatDurationMs } from '../../utils/formatters'

interface ResearchResult {
  report: string
  sites_found: number
  tools_used: number
  total_tokens: number
  effort: string
  duration_ms: number
}

interface PipelineEntry {
  stage?: string
  status?: string
  duration_ms?: number
}

interface TheoReportOverlayProps {
  question: string
  result: ResearchResult
  pipelineTrace: PipelineEntry[] | null
  effort: string
  durationMs: number | null
  sitesFound: number
  toolsUsed: number
  onClose: () => void
}

export default function TheoReportOverlay({
  question,
  result,
  pipelineTrace,
  effort,
  durationMs,
  sitesFound,
  toolsUsed,
  onClose,
}: TheoReportOverlayProps) {
  const [showTrace, setShowTrace] = useState(false)

  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }, [onClose])

  const mdComponents = useMemo(() => ({
    a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
      // Handle site: links — open in new tab to site page
      if (href?.startsWith('site:')) {
        const siteId = href.slice(5)
        return (
          <a
            {...props}
            href={`/site.html?id=${siteId}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--accent-secondary)' }}
          >
            {children}
          </a>
        )
      }
      // Handle youtube: links
      if (href?.startsWith('lyra-video:') || href?.startsWith('youtube:')) {
        const videoId = href.includes(':') ? href.split(':')[1] : href
        return (
          <a
            {...props}
            href={`https://youtube.com/watch?v=${videoId}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        )
      }
      return <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    },
  }), [])

  const doneStages = pipelineTrace?.filter(e => e.status === 'done' && e.stage) ?? []

  return (
    <div className="theo-overlay" onClick={handleBackdropClick}>
      <div className="theo-overlay-inner" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="theo-report-header">
          <img src="/images/theo.png" alt="Theo" className="theo-avatar" style={{ width: 48, height: 48 }} />
          <div className="theo-report-header-text">
            <div className="theo-report-question">{question}</div>
            <div className="theo-report-meta-row">
              <span className="theo-badge theo-badge-effort">{effort}</span>
              {durationMs != null && (
                <span className="theo-badge theo-badge-completed">
                  {formatDurationMs(durationMs)}
                </span>
              )}
              {sitesFound > 0 && (
                <span className="theo-badge" style={{ border: '1px solid var(--border-accent)', color: 'var(--accent-secondary)' }}>
                  {sitesFound} sites
                </span>
              )}
              {toolsUsed > 0 && (
                <span className="theo-badge" style={{ border: '1px solid var(--border-default)', color: 'var(--text-muted)' }}>
                  {toolsUsed} tools
                </span>
              )}
            </div>
          </div>
          <button className="theo-report-close" onClick={onClose} aria-label="Close report">
            ✕
          </button>
        </div>

        {/* Report Body */}
        <div className="theo-report-body theo-md-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {result.report}
          </ReactMarkdown>
        </div>

        {/* Pipeline Trace (collapsible) */}
        {doneStages.length > 0 && (
          <>
            <button
              className="theo-trace-toggle"
              onClick={() => setShowTrace(!showTrace)}
            >
              {showTrace ? '▾' : '▸'} Pipeline trace ({doneStages.length} stages)
            </button>
            {showTrace && (
              <div className="theo-trace-body">
                {doneStages.map((entry, i) => (
                  <div key={i} className="theo-trace-entry">
                    <span className="theo-trace-stage">{entry.stage}</span>
                    <span className="theo-trace-dur">
                      {entry.duration_ms != null ? `${entry.duration_ms}ms` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
