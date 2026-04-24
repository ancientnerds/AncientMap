/**
 * TheoWordpadEditor — WordPad-style paper review with per-paragraph overlay.
 *
 * Replaces the previous per-section approval editor. Each reviewable text
 * block becomes its own small TipTap editor — the reviewer clicks any
 * paragraph and starts typing. A shared sticky toolbar at the top targets the
 * currently focused block's editor. Right-margin [✓]/[✗] buttons let the
 * reviewer decide on each unedited block.
 *
 * Paragraph-level editing uses block-level PATCHes to
 * `/api/theo/research/{id}/section`. The server re-audits citations on every
 * edit and returns the fresh block list, which becomes the new source of
 * truth for the UI.
 */

import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { Editor } from '@tiptap/react'
import type { Components } from 'react-markdown'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ImageLightbox, { type LightboxImage } from '../ImageLightbox'
import { inferSourceType } from '../../utils/sourceType'
import WordpadBlock, { type Block, type BlockListResponse } from './WordpadBlock'
import WordpadToolbar from './WordpadToolbar'

interface TheoWordpadEditorProps {
  requestId: string
  mdComponents: Components
  onDiscard: () => void
  onReportChange?: (newReport: string) => void
}

function isReferencesStart(block: Block): boolean {
  return block.kind === 'heading' && block.content.trim().toLowerCase().startsWith('## references')
}

/**
 * Blocks that carry no meaningful content for a reviewer to decide on:
 * horizontal rules and paragraphs/headings/lists whose text is just whitespace
 * (or the literal `---` marker that sometimes slips through the splitter).
 */
function isEmptyBlock(block: Block): boolean {
  if (block.kind === 'hr') return true
  if (block.kind === 'figure' || block.kind === 'mosaic' || block.kind === 'hero') return false
  const stripped = block.content.replace(/[-\s]/g, '')
  return stripped.length === 0
}

function splitReferences(blocks: Block[]): { reviewable: Block[]; references: Block[] } {
  const refsStart = blocks.findIndex(isReferencesStart)
  if (refsStart === -1) return { reviewable: blocks, references: [] }
  return {
    reviewable: blocks.slice(0, refsStart),
    references: blocks.slice(refsStart),
  }
}

function computeLightboxSources(blocks: Block[]): { images: LightboxImage[]; start: Map<string, number> } {
  const images: LightboxImage[] = []
  const start = new Map<string, number>()
  for (const b of blocks) {
    if (b.kind === 'hero' && b.hero) {
      start.set(b.block_id, images.length)
      images.push({
        src: b.hero.src,
        title: b.hero.caption || b.hero.title || undefined,
        sourceUrl: b.hero.sourceUrl || undefined,
        sourceType: inferSourceType(b.hero.sourceUrl),
      })
    } else if ((b.kind === 'figure' || b.kind === 'mosaic') && b.figures) {
      start.set(b.block_id, images.length)
      for (const f of b.figures) {
        images.push({
          src: f.src,
          title: f.caption || f.title || undefined,
          sourceUrl: f.sourceUrl || undefined,
          sourceType: inferSourceType(f.sourceUrl),
        })
      }
    }
  }
  return { images, start }
}

export default function TheoWordpadEditor({
  requestId,
  mdComponents,
  onDiscard,
  onReportChange,
}: TheoWordpadEditorProps) {
  const [response, setResponse] = useState<BlockListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [focusedEditor, setFocusedEditor] = useState<Editor | null>(null)
  const didSyncReport = useRef(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const token = localStorage.getItem('an_auth_token')
        const resp = await fetch(`/api/theo/research/${requestId}/blocks`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data: BlockListResponse = await resp.json()
        if (!cancelled) setResponse(data)
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : 'load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [requestId])

  const { reviewable: allReviewable, references } = useMemo(
    () => splitReferences(response?.blocks ?? []),
    [response],
  )

  // Hide empty/hr blocks from the UI — they don't need human review.
  const reviewable = useMemo(
    () => allReviewable.filter(b => !isEmptyBlock(b)),
    [allReviewable],
  )

  const lightbox = useMemo(() => computeLightboxSources(response?.blocks ?? []), [response])

  const reviewableCount = reviewable.length
  const decidedCount = reviewable.filter(b => b.state !== 'pending').length
  const allDecided = reviewableCount > 0 && decidedCount === reviewableCount

  // Silently approve any empty/hr blocks the server still considers "pending"
  // so the publish gate doesn't block on invisible content. Runs once per load,
  // serialized to avoid version conflicts.
  const autoApprovedRef = useRef(false)
  useEffect(() => {
    if (!response || autoApprovedRef.current) return
    const pending = allReviewable.filter(b => isEmptyBlock(b) && b.state === 'pending')
    if (pending.length === 0) {
      autoApprovedRef.current = true
      return
    }
    autoApprovedRef.current = true
    ;(async () => {
      const token = localStorage.getItem('an_auth_token')
      let version = response.version
      for (const block of pending) {
        try {
          const resp = await fetch(`/api/theo/research/${requestId}/section`, {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              block_id: block.block_id,
              state: 'approved',
              expected_version: version,
            }),
          })
          if (!resp.ok) break
          const data: BlockListResponse = await resp.json()
          version = data.version
          setResponse(data)
        } catch {
          break // network hiccup; reviewer can still manually approve if needed
        }
      }
    })()
  }, [response, allReviewable, requestId])

  // Sync once on load so the parent overlay can re-derive reading time etc.
  useEffect(() => {
    if (!response || !onReportChange || didSyncReport.current) return
    didSyncReport.current = true
    const parts = response.blocks
      .filter(b => b.kind !== 'hero')
      .map(b => (b.state === 'edited' && b.edited_content != null ? b.edited_content : b.content))
    onReportChange(parts.join(''))
  }, [response, onReportChange])

  const handleResponse = useCallback((resp: BlockListResponse) => {
    setResponse(resp)
  }, [])

  const handleFocusEditor = useCallback((editor: Editor | null) => {
    setFocusedEditor(prev => {
      // Only clear if the editor that's losing focus is the one we're tracking.
      // (onFocus of the next editor fires before onBlur of the previous one,
      // so we usually set the new editor first; explicit null is a "clear".)
      if (editor === null) return prev
      return editor
    })
  }, [])

  const publish = async () => {
    setPublishing(true)
    setPublishError(null)
    try {
      const token = localStorage.getItem('an_auth_token')
      const resp = await fetch(`/api/theo/research/${requestId}/publish`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!resp.ok) {
        const detail = await resp.text().catch(() => '')
        throw new Error(`HTTP ${resp.status}: ${detail.slice(0, 160)}`)
      }
      const data = await resp.json()
      if (data.slug) window.location.href = `/research/${data.slug}`
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : 'publish failed')
    } finally {
      setPublishing(false)
    }
  }

  if (loading) {
    return (
      <div className="theo-report-body" style={{ padding: 20, color: 'var(--text-dimmed)' }}>
        Loading WordPad editor…
      </div>
    )
  }
  if (loadError) {
    return (
      <div className="theo-report-body" style={{ padding: 20, color: '#f44336' }}>
        Failed to load blocks: {loadError}
        <button onClick={onDiscard} style={{ marginLeft: 12 }}>Close</button>
      </div>
    )
  }
  if (!response) return null

  return (
    <>
      <div className="theo-wordpad-frame theo-report-body theo-md-body">
        <WordpadToolbar focusedEditor={focusedEditor} />

        {reviewable.map(block => (
          <WordpadBlock
            key={block.block_id}
            block={block}
            version={response.version}
            requestId={requestId}
            mdComponents={mdComponents}
            onFocusEditor={handleFocusEditor}
            onResponse={handleResponse}
            onImageClick={setLightboxIndex}
            lightboxStart={lightbox.start.get(block.block_id) ?? 0}
          />
        ))}

        {references.length > 0 && (
          <div className="theo-wordpad-references">
            {references.map(block => (
              <div key={block.block_id}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                  {block.content}
                </ReactMarkdown>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="theo-approval-progress">
        <span style={{ fontSize: 13, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {decidedCount} / {reviewableCount} decided
        </span>
        <div className="theo-approval-progress-bar">
          <div
            className="theo-approval-progress-fill"
            style={{ width: reviewableCount === 0 ? '0%' : `${(decidedCount / reviewableCount) * 100}%` }}
          />
        </div>
        <button
          onClick={onDiscard}
          style={{
            background: 'transparent',
            border: '1px solid rgba(160, 160, 168, 0.30)',
            color: 'var(--text-default)',
            padding: '6px 14px',
            borderRadius: 4,
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          Exit editor
        </button>
        <button
          className="theo-approval-publish-btn"
          disabled={!allDecided || publishing}
          onClick={publish}
          title={allDecided ? 'Publish reviewed paper' : 'Decide on every block first'}
        >
          {publishing ? 'Publishing…' : 'Publish paper'}
        </button>
      </div>

      {publishError && (
        <div
          style={{
            position: 'sticky',
            bottom: 56,
            background: 'rgba(198, 40, 40, 0.18)',
            border: '1px solid rgba(198, 40, 40, 0.55)',
            padding: '6px 12px',
            color: '#f44336',
            fontSize: 12,
            zIndex: 5,
          }}
        >
          {publishError}
        </div>
      )}

      {lightboxIndex !== null && lightbox.images.length > 0 &&
        createPortal(
          <ImageLightbox
            images={lightbox.images}
            currentIndex={Math.min(lightboxIndex, lightbox.images.length - 1)}
            onClose={() => setLightboxIndex(null)}
            onNavigate={setLightboxIndex}
          />,
          document.body,
        )
      }
    </>
  )
}
