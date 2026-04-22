/**
 * TheoApprovalEditor — Per-section approval editor.
 *
 * Replaces the free-form TipTap editor. Fetches the server's canonical block
 * list and renders each block with a corner badge (approved / rejected /
 * edited / pending) so the reviewer has to explicitly decide on every block
 * before the paper can be published. Decisions round-trip through
 * `PATCH /theo/research/{id}/section`; the response is the new authoritative
 * block list so the UI never disagrees with the server on "what is a block".
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ImageLightbox, { type LightboxImage } from '../ImageLightbox'
import { inferSourceType } from '../../utils/sourceType'

// Must mirror backend `api/services/theo_blocks.py::Block` + hero shape.
interface Figure {
  src: string
  title: string
  caption: string
  sourceUrl: string
}

interface HeroPayload {
  src: string
  caption: string
  sourceUrl: string
  title: string
}

interface Block {
  block_id: string
  content_hash: string
  position: { segment_idx: number; block_idx: number }
  kind:
    | 'heading'
    | 'paragraph'
    | 'list'
    | 'blockquote'
    | 'table'
    | 'code'
    | 'hr'
    | 'html'
    | 'figure'
    | 'mosaic'
    | 'hero'
  content: string
  figures?: Figure[]
  hero?: HeroPayload
  state: 'pending' | 'approved' | 'rejected' | 'edited'
  decided_by?: string | null
  decided_at?: string | null
  edited_content?: string | null
}

interface BlockListResponse {
  version: number
  blocks: Block[]
}

interface TheoApprovalEditorProps {
  requestId: string
  mdComponents: Components
  onDiscard: () => void
  onReportChange?: (newReport: string) => void
}

function isReferencesStart(block: Block): boolean {
  return block.kind === 'heading' && block.content.trim().toLowerCase().startsWith('## references')
}

/**
 * Decide which blocks the reviewer must explicitly handle. References are
 * auto-approved server-side — the UI renders them flat (no badge, no popover)
 * and they don't count toward the publish gate.
 */
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

/**
 * Render the raw content of a block. For text-ish kinds we hand the content
 * to ReactMarkdown with the caller's components (so citation links and custom
 * protocols stay identical to the read-only view). For figures / mosaics we
 * emit the same JSX shape `TheoPaperBody` uses, so the layout is byte-for-byte
 * identical to the public page.
 */
function BlockRenderer({
  block,
  mdComponents,
  onImageClick,
  lightboxStart,
}: {
  block: Block
  mdComponents: Components
  onImageClick: (idx: number) => void
  lightboxStart: number
}) {
  // Show edited preview when an edit has been saved — reviewer sees what will
  // actually ship, not the stale original.
  const effective = block.state === 'edited' && block.edited_content != null
    ? block.edited_content
    : block.content

  if (block.kind === 'hero' && block.hero) {
    return (
      <figure className="theo-inline-figure">
        <img
          src={block.hero.src}
          alt={block.hero.title || 'Hero image'}
          loading="lazy"
          onClick={() => onImageClick(lightboxStart)}
        />
        {block.hero.caption && (
          <figcaption>
            {block.hero.sourceUrl ? (
              <a href={block.hero.sourceUrl} target="_blank" rel="noopener noreferrer">
                <em>{block.hero.caption}</em>
              </a>
            ) : (
              <em>{block.hero.caption}</em>
            )}
          </figcaption>
        )}
      </figure>
    )
  }

  if (block.kind === 'figure' && block.figures && block.figures.length > 0) {
    const f = block.figures[0]
    return (
      <figure className="theo-inline-figure">
        <img
          src={f.src}
          alt={f.title || ''}
          loading="lazy"
          onClick={() => onImageClick(lightboxStart)}
        />
        {f.caption && (
          <figcaption>
            {f.sourceUrl ? (
              <a href={f.sourceUrl} target="_blank" rel="noopener noreferrer">
                <em>{f.caption}</em>
              </a>
            ) : (
              <em>{f.caption}</em>
            )}
          </figcaption>
        )}
      </figure>
    )
  }

  if (block.kind === 'mosaic' && block.figures && block.figures.length > 0) {
    const cols = Math.min(3, block.figures.length)
    return (
      <div className={`theo-figure-mosaic theo-figure-mosaic--cols-${cols}`}>
        {block.figures.map((fig, i) => (
          <figure key={i} className="theo-figure-mosaic-item">
            <img
              src={fig.src}
              alt={fig.title || ''}
              loading="lazy"
              onClick={() => onImageClick(lightboxStart + i)}
            />
            {fig.caption && (
              <figcaption>
                {fig.sourceUrl ? (
                  <a href={fig.sourceUrl} target="_blank" rel="noopener noreferrer">
                    <em>{fig.caption}</em>
                  </a>
                ) : (
                  <em>{fig.caption}</em>
                )}
              </figcaption>
            )}
          </figure>
        ))}
      </div>
    )
  }

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
      {effective}
    </ReactMarkdown>
  )
}

function badgeIcon(state: Block['state']): string {
  if (state === 'approved') return '✓'
  if (state === 'rejected') return '✗'
  if (state === 'edited') return '✎'
  return '?'
}

function ApprovalBlockWrapper({
  block,
  version,
  requestId,
  mdComponents,
  onImageClick,
  lightboxStart,
  onResponse,
}: {
  block: Block
  version: number
  requestId: string
  mdComponents: Components
  onImageClick: (idx: number) => void
  lightboxStart: number
  onResponse: (resp: BlockListResponse) => void
}) {
  const [showPopover, setShowPopover] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string>('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const patch = useCallback(
    async (state: 'approved' | 'rejected' | 'edited', content?: string) => {
      setSaving(true)
      setError(null)
      try {
        const token = localStorage.getItem('an_auth_token')
        const resp = await fetch(`/api/theo/research/${requestId}/section`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            block_id: block.block_id,
            state,
            expected_version: version,
            content,
          }),
        })
        if (!resp.ok) {
          const detail = await resp.text().catch(() => '')
          throw new Error(`HTTP ${resp.status}: ${detail.slice(0, 120)}`)
        }
        const data: BlockListResponse = await resp.json()
        onResponse(data)
        setShowPopover(false)
        setEditing(false)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'save failed')
      } finally {
        setSaving(false)
      }
    },
    [block.block_id, requestId, version, onResponse],
  )

  const startEdit = () => {
    setDraft(block.edited_content ?? (block.kind === 'hero' ? block.hero?.caption ?? '' : block.content))
    setEditing(true)
    setShowPopover(false)
  }

  return (
    <div className={`theo-approval-block theo-approval-block--${block.state}`}>
      <div className="theo-approval-content">
        <BlockRenderer
          block={block}
          mdComponents={mdComponents}
          onImageClick={onImageClick}
          lightboxStart={lightboxStart}
        />
      </div>

      {editing && (
        <div className="theo-approval-edit-box">
          <textarea
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder={block.kind === 'hero' ? 'Hero caption…' : 'Block markdown…'}
            spellCheck={false}
          />
          {error && <div style={{ color: '#f44336', fontSize: 12, marginTop: 6 }}>{error}</div>}
          <div className="theo-approval-edit-actions">
            <button onClick={() => { setEditing(false); setError(null) }} disabled={saving}>Cancel</button>
            <button className="save" onClick={() => patch('edited', draft)} disabled={saving}>
              {saving ? 'Saving…' : 'Save edit'}
            </button>
          </div>
        </div>
      )}

      {showPopover && !editing && (
        <div className="theo-approval-popover" onClick={e => e.stopPropagation()}>
          <button className="approve" disabled={saving} onClick={() => patch('approved')}>Approve</button>
          <button className="reject" disabled={saving} onClick={() => patch('rejected')}>Reject</button>
          <button className="edit" disabled={saving} onClick={startEdit}>Edit</button>
        </div>
      )}

      <div
        className={`theo-approval-badge theo-approval-badge--${block.state}`}
        title={
          block.state === 'pending'
            ? 'Decide on this block'
            : `${block.state}${block.decided_by ? ` by ${block.decided_by}` : ''}`
        }
        onClick={e => {
          e.stopPropagation()
          setShowPopover(s => !s)
        }}
      >
        {badgeIcon(block.state)}
      </div>
    </div>
  )
}

function TheoApprovalEditor({
  requestId,
  mdComponents,
  onDiscard,
  onReportChange,
}: TheoApprovalEditorProps) {
  const [response, setResponse] = useState<BlockListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
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
    return () => { cancelled = true }
  }, [requestId])

  const { reviewable, references } = useMemo(
    () => splitReferences(response?.blocks ?? []),
    [response],
  )

  const lightbox = useMemo(() => computeLightboxSources(response?.blocks ?? []), [response])

  const reviewableCount = reviewable.length
  const decidedCount = reviewable.filter(b => b.state !== 'pending').length
  const allDecided = reviewableCount > 0 && decidedCount === reviewableCount

  // Let the overlay re-render the header meta (reading time etc.) whenever an
  // edit changes the effective report. We reconstruct the report client-side
  // from the latest block content so the parent sees the same text the server
  // stored.
  useEffect(() => {
    if (!response || !onReportChange || didSyncReport.current) return
    didSyncReport.current = true  // only sync once on load; edits are reported per-PATCH
    const parts = response.blocks
      .filter(b => b.kind !== 'hero')
      .map(b => (b.state === 'edited' && b.edited_content != null ? b.edited_content : b.content))
    onReportChange(parts.join(''))
  }, [response, onReportChange])

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
      // Hard reload to the public slug so the reviewer lands on the same view
      // a visitor would see.
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
        Loading approval editor…
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
      <div className="theo-report-body theo-md-body">
        {reviewable.map(block => (
          <ApprovalBlockWrapper
            key={block.block_id}
            block={block}
            version={response.version}
            requestId={requestId}
            mdComponents={mdComponents}
            onImageClick={setLightboxIndex}
            lightboxStart={lightbox.start.get(block.block_id) ?? 0}
            onResponse={setResponse}
          />
        ))}

        {references.length > 0 && (
          <div style={{ marginTop: 24, opacity: 0.95 }}>
            {references.map(block => (
              <div key={block.block_id}>
                <BlockRenderer
                  block={block}
                  mdComponents={mdComponents}
                  onImageClick={setLightboxIndex}
                  lightboxStart={lightbox.start.get(block.block_id) ?? 0}
                />
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
        <button onClick={onDiscard} style={{
          background: 'transparent',
          border: '1px solid rgba(160, 160, 168, 0.30)',
          color: 'var(--text-default)',
          padding: '6px 14px',
          borderRadius: 4,
          fontSize: 13,
          cursor: 'pointer',
        }}>Exit editor</button>
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
        <div style={{
          position: 'sticky',
          bottom: 56,
          background: 'rgba(198, 40, 40, 0.18)',
          border: '1px solid rgba(198, 40, 40, 0.55)',
          padding: '6px 12px',
          color: '#f44336',
          fontSize: 12,
          zIndex: 5,
        }}>
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

export default TheoApprovalEditor
