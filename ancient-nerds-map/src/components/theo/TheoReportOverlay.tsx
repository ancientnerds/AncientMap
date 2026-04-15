/**
 * TheoReportOverlay — Full-screen report viewer for completed research.
 * Renders the full paper with clickable citation links, formatted references,
 * inline source images with attribution, and quality audit results.
 * Supports inline WYSIWYG editing via TheoEditor when isOwner is true.
 */

import { useState, useMemo, useCallback, useEffect, useRef, lazy, Suspense } from 'react'
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
  edited_at?: string | null
  approved_by?: string | null
  approved_at?: string | null
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
  requestId?: string
  initialEditing?: boolean
  onSaveEdit?: (report: string) => void
  onApprove?: (approvedBy: string, approvedAt: string) => void
}

const EFFORT_LABELS: Record<string, string> = {
  brief: 'Brief', note: 'Note', article: 'Article',
  review: 'Review', thesis: 'Thesis', dissertation: 'Dissertation',
}

// ---------------------------------------------------------------------------
// Citation enrichment — same pattern as ArticlesPage
// ---------------------------------------------------------------------------

/** Parse the References section and return a map of [N] → URL. */
function parseReferenceCitations(content: string): Map<number, string> {
  const cites = new Map<number, string>()
  // Research papers use "## References" with format: [N] Title — URL (accessed ...)
  const refsIdx = content.search(/^## References/m)
  if (refsIdx === -1) return cites
  const refsList = content.slice(refsIdx)
  // Match: [N] ... — https://... or [N] ... https://...
  const pattern = /^\[(\d+)\].*?(https?:\/\/\S+)/gm
  let m: RegExpExecArray | null
  while ((m = pattern.exec(refsList)) !== null) {
    cites.set(parseInt(m[1], 10), m[2].replace(/[)\]>,;]+$/, ''))
  }
  return cites
}

/** Fix inline ## headings — ensure they're on their own line with a blank line before. */
function fixHeadings(content: string): string {
  // Strip trailing --- from paragraphs
  content = content.replace(/\s*---\s*$/gm, '')
  // Ensure ## headings have a blank line before them
  content = content.replace(/([^\n])\s*(## )/g, '$1\n\n$2')
  return content
}

/** Convert [N] in body text to clickable markdown links. */
function enrichCitations(content: string, cites: Map<number, string>): string {
  // Don't touch the References section itself
  const refsIdx = content.search(/^## References/m)
  if (refsIdx === -1) {
    return replaceInBody(content, cites)
  }
  const body = content.slice(0, refsIdx)
  const refs = content.slice(refsIdx)
  return replaceInBody(body, cites) + refs
}

function replaceInBody(body: string, cites: Map<number, string>): string {
  // Normalize multi-citations: [6, 7] → [6] [7]
  body = body.replace(/\[(\d+)(?:\s*,\s*(\d+))+\]/g, (match) => {
    const nums = match.match(/\d+/g) || []
    return nums.map(n => `[${n}]`).join(' ')
  })
  body = body.replace(/\](\[)/g, '] [')
  // Replace [N] with links — use ［N］ to avoid markdown re-parsing
  return body.replace(/(?<!\[)\[(\d+)\](?!\()/g, (_match, numStr) => {
    const num = parseInt(numStr, 10)
    const url = cites.get(num)
    if (url) {
      return `[［${num}］](${url})`
    }
    return `[［${num}］](#references)`
  })
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TheoReportOverlay({
  question,
  result,
  pipelineTrace,
  effort,
  onClose,
  isOwner,
  isPublic,
  requestId,
  initialEditing,
  onSaveEdit,
  onApprove,
}: TheoReportOverlayProps) {
  const [showTrace, setShowTrace] = useState(false)
  const [showAudit, setShowAudit] = useState(false)
  const [editing, setEditing] = useState(initialEditing ?? false)
  const [approving, setApproving] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

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
    if (isPublic) {
      if (!window.confirm('This paper is published. Save and update the public version?')) {
        return
      }
    }
    onSaveEdit?.(markdown)
    setEditing(false)
  }, [onSaveEdit, isPublic])

  const handleDiscardEdit = useCallback(() => {
    setEditing(false)
  }, [])

  // Fix headings + enrich citations
  const fixedReport = useMemo(() => fixHeadings(result.report), [result.report])
  const refCites = useMemo(() => parseReferenceCitations(fixedReport), [fixedReport])
  const enrichedReport = useMemo(() => enrichCitations(fixedReport, refCites), [fixedReport, refCites])

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
      // Citation links — render as superscript
      const text = String(children).trim()
      const numMatch = text.match(/[［\[]*(\d+)[］\]]*/)
      if (numMatch && (href === '#references' || refCites.has(parseInt(numMatch[1], 10)))) {
        const num = parseInt(numMatch[1], 10)
        return (
          <a
            {...props}
            href={href}
            target={href === '#references' ? undefined : '_blank'}
            rel={href === '#references' ? undefined : 'noopener noreferrer'}
            className="theo-citation-link"
          >
            [{num}]
          </a>
        )
      }
      return <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    },
    img: ({ src, alt }: React.ImgHTMLAttributes<HTMLImageElement>) => (
      <figure className="theo-source-image">
        <img src={src} alt={alt || ''} loading="lazy" />
        {alt && <figcaption>{alt}</figcaption>}
      </figure>
    ),
    h2: ({ children }: React.HTMLAttributes<HTMLHeadingElement>) => {
      const text = String(children)
      const id = text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/[\s]+/g, '-')
      return <h2 id={id}>{children}</h2>
    },
    // Style italic lines after images as attribution
    em: ({ children }: React.HTMLAttributes<HTMLElement>) => {
      const text = String(children)
      // Attribution lines: "Author, Wikimedia Commons, CC BY-SA 4.0" or "Metropolitan Museum..."
      if (text.includes('Wikimedia Commons') || text.includes('Metropolitan Museum') || text.includes('Public Domain') || text.includes('CC BY')) {
        return <span className="theo-image-attribution">{children}</span>
      }
      return <em>{children}</em>
    },
  }), [refCites])

  const doneStages = pipelineTrace?.filter(e => e.status === 'done' && e.stage) ?? []
  const readingMinutes = Math.ceil(result.report.split(/\s+/).length / 200)
  const qs = result.quality_score

  // Extract paper title from first # heading
  const paperTitle = useMemo(() => {
    const match = result.report.match(/^#\s+(.+)$/m)
    return match ? match[1].trim() : null
  }, [result.report])

  return (
    <div className="theo-overlay" onClick={handleBackdropClick}>
      <div className="theo-overlay-inner" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="theo-report-header">
          <img src="/images/theo.png" alt="Theo" className="theo-avatar" style={{ width: 48, height: 48 }} />
          <div className="theo-report-header-text">
            <div className="theo-report-question" title={question}>
              {paperTitle || (question.length > 120 ? question.slice(0, 120) + '...' : question)}
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
              <span className="theo-badge theo-badge-effort">{EFFORT_LABELS[effort] || effort}</span>
              <QualityBadge qualityScore={result.quality_score} effort={effort} />
              <span className="theo-badge" style={{ border: '1px solid var(--border-default)', color: 'var(--text-dimmed)' }}>
                {readingMinutes} min read
              </span>
              {result.edited_at && (
                <span className="theo-badge" style={{ border: '1px solid var(--border-default)', color: 'var(--text-dimmed)' }} title={new Date(result.edited_at + (result.edited_at.endsWith('Z') ? '' : 'Z')).toLocaleString()}>
                  edited {new Date(result.edited_at + (result.edited_at.endsWith('Z') ? '' : 'Z')).toLocaleDateString()}
                </span>
              )}
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

          {/* Edit button — owner can always edit */}
          {isOwner && (
            <button
              className="theo-edit-btn"
              onClick={() => setEditing(true)}
              title="Edit paper"
              aria-label="Edit paper"
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
              approving={approving}
              approved={!!result.approved_by}
              onApprove={isOwner && requestId ? async () => {
                setApproving(true)
                try {
                  const token = localStorage.getItem('an_auth_token')
                  const resp = await fetch(`/api/theo/research/${requestId}/approve`, {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${token}` },
                  })
                  if (resp.ok) {
                    const data = await resp.json()
                    onApprove?.(data.approved_by, data.approved_at)
                  }
                } catch { /* network error */ }
                setApproving(false)
              } : undefined}
            />
          </Suspense>
        ) : (
          <div className="theo-report-body theo-md-body" ref={bodyRef}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {enrichedReport}
            </ReactMarkdown>
          </div>
        )}

        {/* Quality Audit (collapsible) — shows dimension scores */}
        {!editing && qs && typeof qs.total === 'number' && (
          <>
            <button
              className="theo-trace-toggle"
              onClick={() => setShowAudit(!showAudit)}
            >
              {showAudit ? '▾' : '▸'} Quality audit — {qs.total}/100 ({qs.badge})
            </button>
            {showAudit && (
              <div className="theo-audit-body">
                <div className="theo-audit-grid">
                  {Object.entries(qs.dimensions).map(([dim, score]) => {
                    const max = dim === 'citation_coverage' ? 20 : 10
                    const pct = (score as number) / max * 100
                    const label = dim.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                    return (
                      <div key={dim} className="theo-audit-row">
                        <span className="theo-audit-label">{label}</span>
                        <div className="theo-audit-bar-bg">
                          <div
                            className="theo-audit-bar-fill"
                            style={{
                              width: `${pct}%`,
                              background: pct >= 80 ? '#2e7d32' : pct >= 60 ? '#f57f17' : '#c62828',
                            }}
                          />
                        </div>
                        <span className="theo-audit-score">{score as number}/{max}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </>
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

        {/* Debug Log Download */}
        {!editing && isOwner && requestId && (
          <button
            className="theo-trace-toggle"
            onClick={async () => {
              const token = localStorage.getItem('an_auth_token')
              try {
                const resp = await fetch(`/api/theo/research/${requestId}/log?format=md`, {
                  headers: token ? { Authorization: `Bearer ${token}` } : {},
                })
                if (!resp.ok) return
                const text = await resp.text()
                const blob = new Blob([text], { type: 'text/markdown' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `debug-log-${requestId.slice(0, 8)}.md`
                a.click()
                URL.revokeObjectURL(url)
              } catch { /* network error */ }
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Download debug log
          </button>
        )}
      </div>
    </div>
  )
}
