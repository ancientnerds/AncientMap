/**
 * TheoReportOverlay — Full-screen report viewer for completed research.
 * Uses ReactMarkdown with custom site: link handling (same as LyraChatModal).
 * Supports inline WYSIWYG editing via TheoEditor when isOwner is true.
 */

import { useState, useMemo, useCallback, useEffect, lazy, Suspense } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import QualityBadge, { type QualityScore } from './QualityBadge'

const TheoEditor = lazy(() => import('./TheoEditor'))

interface ResearchResult {
  report: string
  sites_found: number
  tools_used: number
  total_tokens: number
  effort: string
  duration_ms: number
  quality_score?: QualityScore | null
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
  isOwner?: boolean
  isPublic?: boolean
  onSaveEdit?: (report: string) => void
}

export default function TheoReportOverlay({
  question,
  result,
  pipelineTrace,
  effort,
  onClose,
  isOwner,
  isPublic,
  onSaveEdit,
}: TheoReportOverlayProps) {
  const [showTrace, setShowTrace] = useState(false)
  const [editing, setEditing] = useState(false)

  // Escape key to close (not while editing)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (editing) return
        onClose()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose, editing])

  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (editing) return
    if (e.target === e.currentTarget) onClose()
  }, [onClose, editing])

  const handleSaveEdit = useCallback((markdown: string) => {
    onSaveEdit?.(markdown)
    setEditing(false)
  }, [onSaveEdit])

  const handleDiscardEdit = useCallback(() => {
    setEditing(false)
  }, [])

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

  const readingMinutes = Math.ceil(result.report.split(/\s+/).length / 200)

  return (
    <div className="theo-overlay" onClick={handleBackdropClick}>
      <div className="theo-overlay-inner" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="theo-report-header">
          <img src="/images/theo.png" alt="Theo" className="theo-avatar" style={{ width: 48, height: 48 }} />
          <div className="theo-report-header-text">
            <div className="theo-report-question">
              {question.length > 200 ? question.slice(0, 200) + '...' : question}
              <button
                className="theo-copy-question"
                onClick={() => navigator.clipboard.writeText(question)}
                title="Copy full prompt"
                aria-label="Copy full prompt"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
            </div>
            <div className="theo-report-meta-row">
              <span className="theo-badge theo-badge-effort">{{ brief: 'Brief', note: 'Note', article: 'Article', review: 'Review', thesis: 'Thesis' }[effort] || effort}</span>
              <QualityBadge qualityScore={result.quality_score} effort={effort} />
              <span className="theo-badge" style={{ border: '1px solid var(--border-default)', color: 'var(--text-dimmed)' }}>
                {readingMinutes} min read
              </span>
              <button
                className="theo-report-share"
                onClick={() => { navigator.clipboard.writeText(window.location.href); }}
                title="Copy link"
                aria-label="Copy link"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
              </button>
            </div>
          </div>

          {/* Edit button — only for owner, disabled when public */}
          {isOwner && (
            <button
              className="theo-edit-btn"
              onClick={() => setEditing(true)}
              disabled={isPublic}
              title={isPublic ? 'Unpublish to edit' : 'Edit paper'}
              aria-label={isPublic ? 'Unpublish to edit' : 'Edit paper'}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </button>
          )}

          <button className="theo-report-close" onClick={onClose} aria-label="Close report">
            ✕
          </button>
        </div>

        {/* Report Body — editor or reader */}
        {editing ? (
          <Suspense fallback={<div className="theo-report-body" style={{ padding: 20, color: 'var(--text-dimmed)' }}>Loading editor...</div>}>
            <TheoEditor
              content={result.report}
              onSave={handleSaveEdit}
              onDiscard={handleDiscardEdit}
            />
          </Suspense>
        ) : (
          <div className="theo-report-body theo-md-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {result.report}
            </ReactMarkdown>
          </div>
        )}

        {/* Pipeline Trace (collapsible) — hidden during editing */}
        {!editing && doneStages.length > 0 && (
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
