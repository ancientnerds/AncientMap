/**
 * WordpadBlock — one block of the WordPad paper review surface.
 *
 * Text kinds (paragraph, heading, list, blockquote) get an inline TipTap
 * editor — click anywhere in the text to edit, type, use the toolbar. On
 * blur, if the round-tripped markdown differs from the original, PATCH
 * state='edited' and trust the server response as the new source of truth.
 *
 * Figures, mosaics, and hero render as static JSX (no editor — caption edits
 * deferred to V2). Tables, code, html, and hr render read-only via
 * ReactMarkdown.
 *
 * Every block has an action row at the END of the block: [Approve] [Edit]
 * [Reject] for text kinds, [Approve] [Reject] for everything else. The Edit
 * button just focuses the paragraph's editor — the actual typing happens
 * inline, not in a modal.
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useEditor, EditorContent, type Editor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { markdownToHtml, htmlToMarkdown, isDirty } from './wordpadMarkdown'

// Must mirror backend `api/services/theo_blocks.py::Block` + hero shape.
export interface Figure {
  src: string
  title: string
  caption: string
  sourceUrl: string
}

export interface HeroPayload {
  src: string
  caption: string
  sourceUrl: string
  title: string
}

export interface Block {
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

export interface BlockListResponse {
  version: number
  blocks: Block[]
}

const TEXT_KINDS: Block['kind'][] = ['paragraph', 'heading', 'list', 'blockquote']
const MEDIA_KINDS: Block['kind'][] = ['figure', 'mosaic', 'hero']

type DecisionState = 'approved' | 'rejected' | 'edited'

interface WordpadBlockProps {
  block: Block
  version: number
  requestId: string
  mdComponents: Components
  onFocusEditor: (editor: Editor | null) => void
  onResponse: (resp: BlockListResponse) => void
  onImageClick: (idx: number) => void
  lightboxStart: number
}

/**
 * Shared PATCH helper hook. Returns `{patch, saving, error}`.
 */
function usePatch(block: Block, version: number, requestId: string, onResponse: (r: BlockListResponse) => void) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const patch = useCallback(
    async (state: DecisionState, content?: string) => {
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
      } catch (e) {
        setError(e instanceof Error ? e.message : 'save failed')
      } finally {
        setSaving(false)
      }
    },
    [block.block_id, requestId, version, onResponse],
  )

  return { patch, saving, error }
}

/**
 * Top-level dispatcher. Picks the right inner component for this block's
 * kind so the `useEditor` hook only fires for text blocks (React hooks rules
 * require unconditional hook calls per component).
 */
export default function WordpadBlock(props: WordpadBlockProps) {
  const { block } = props
  if (TEXT_KINDS.includes(block.kind)) {
    return <TextBlock {...props} />
  }
  return <StaticBlock {...props} />
}

// ---------------------------------------------------------------------------
// Text blocks — inline TipTap editor + footer with approve/edit/reject
// ---------------------------------------------------------------------------

function TextBlock({
  block,
  version,
  requestId,
  onFocusEditor,
  onResponse,
}: WordpadBlockProps) {
  const effective = useMemo(
    () => (block.state === 'edited' && block.edited_content != null ? block.edited_content : block.content),
    [block.state, block.edited_content, block.content],
  )

  const { patch, saving, error } = usePatch(block, version, requestId, onResponse)
  const [dirty, setDirty] = useState(false)

  // Stash the original markdown so we can detect reverts back to it.
  const originalMarkdownRef = useRef<string>(effective)
  // Latest value of `patch` for the TipTap callbacks (whose closure captures
  // its first-render version otherwise, since deps change recreates the
  // editor — which we don't want to do on every patch change).
  const patchRef = useRef(patch)
  useEffect(() => {
    patchRef.current = patch
  }, [patch])

  const initialHtml = useMemo(() => markdownToHtml(effective), [effective])

  const editor = useEditor(
    {
      extensions: [
        StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
        Link.configure({
          openOnClick: false,
          autolink: false,
          HTMLAttributes: { target: '_blank', rel: 'noopener noreferrer' },
        }),
      ],
      content: initialHtml,
      immediatelyRender: false,
      onUpdate: ({ editor }) => {
        setDirty(isDirty(editor.getHTML(), originalMarkdownRef.current))
      },
      onFocus: ({ editor }) => {
        onFocusEditor(editor)
      },
      onBlur: ({ editor }) => {
        if (isDirty(editor.getHTML(), originalMarkdownRef.current)) {
          patchRef.current('edited', htmlToMarkdown(editor.getHTML()))
        }
      },
    },
    [block.block_id],
  )

  // When the effective content changes (server returned a new version after
  // an edit), refresh both the editor content and the "original" ref.
  useEffect(() => {
    if (!editor) return
    const currentMd = htmlToMarkdown(editor.getHTML()).trim()
    if (currentMd !== effective.trim()) {
      editor.commands.setContent(markdownToHtml(effective), { emitUpdate: false })
    }
    originalMarkdownRef.current = effective
    setDirty(false)
  }, [effective, editor])

  const stateClass = dirty ? 'edited' : block.state
  const blockClass = `theo-wordpad-block theo-wordpad-block--${stateClass}`

  const approveDisabled = saving || dirty || block.state === 'approved'
  const rejectDisabled = saving || dirty || block.state === 'rejected'
  const tooltip = dirty ? 'Click outside the paragraph to save edits first' : undefined

  const focusEditor = () => editor?.chain().focus('end').run()

  return (
    <div className={blockClass}>
      <div className="theo-wordpad-block-content">
        <div className="theo-editor-content theo-md-body">
          {editor && <EditorContent editor={editor} />}
        </div>
        {error && <div className="theo-wordpad-block-error">{error}</div>}
      </div>
      <BlockFooter
        dirty={dirty}
        state={block.state}
        approveDisabled={approveDisabled}
        rejectDisabled={rejectDisabled}
        saving={saving}
        tooltip={tooltip}
        onApprove={() => patch('approved')}
        onReject={() => patch('rejected')}
        onEdit={focusEditor}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Static blocks — figures / mosaics / hero / tables / code / html / hr
// ---------------------------------------------------------------------------

function StaticBlock({
  block,
  version,
  requestId,
  mdComponents,
  onResponse,
  onImageClick,
  lightboxStart,
}: WordpadBlockProps) {
  const effective =
    block.state === 'edited' && block.edited_content != null ? block.edited_content : block.content
  const { patch, saving, error } = usePatch(block, version, requestId, onResponse)
  const isMedia = MEDIA_KINDS.includes(block.kind)

  const blockClass = `theo-wordpad-block theo-wordpad-block--${block.state}`
  const approveDisabled = saving || block.state === 'approved'
  const rejectDisabled = saving || block.state === 'rejected'

  return (
    <div className={blockClass}>
      <div className="theo-wordpad-block-content">
        {isMedia ? (
          <MediaView block={block} onImageClick={onImageClick} lightboxStart={lightboxStart} />
        ) : (
          <div className="theo-md-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {effective}
            </ReactMarkdown>
          </div>
        )}
        {error && <div className="theo-wordpad-block-error">{error}</div>}
      </div>
      <BlockFooter
        dirty={false}
        state={block.state}
        approveDisabled={approveDisabled}
        rejectDisabled={rejectDisabled}
        saving={saving}
        onApprove={() => patch('approved')}
        onReject={() => patch('rejected')}
        // No onEdit for static blocks — media/tables/code can't be inline-edited in V1
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Footer row at the end of each block — approve / edit / reject
// ---------------------------------------------------------------------------

function BlockFooter({
  dirty,
  state,
  approveDisabled,
  rejectDisabled,
  saving,
  tooltip,
  onApprove,
  onReject,
  onEdit,
}: {
  dirty: boolean
  state: Block['state']
  approveDisabled: boolean
  rejectDisabled: boolean
  saving: boolean
  tooltip?: string
  onApprove: () => void
  onReject: () => void
  onEdit?: () => void
}) {
  const showEditedChip = dirty || state === 'edited'
  return (
    <div className="theo-wordpad-block-footer">
      {showEditedChip && (
        <span className="theo-wordpad-edited-chip" title="Edited">
          ✎ edited
        </span>
      )}
      {state === 'approved' && !dirty && (
        <span className="theo-wordpad-state-chip theo-wordpad-state-chip--approved">✓ approved</span>
      )}
      {state === 'rejected' && !dirty && (
        <span className="theo-wordpad-state-chip theo-wordpad-state-chip--rejected">✗ rejected</span>
      )}
      <div className="theo-wordpad-footer-spacer" />
      <button
        type="button"
        className={`theo-wordpad-footer-btn approve ${state === 'approved' ? 'active' : ''}`}
        onClick={onApprove}
        disabled={approveDisabled}
        title={tooltip ?? 'Approve'}
      >
        ✓ Approve
      </button>
      {onEdit && (
        <button
          type="button"
          className="theo-wordpad-footer-btn edit"
          onClick={onEdit}
          disabled={saving}
          title="Edit paragraph (focus cursor)"
        >
          ✎ Edit
        </button>
      )}
      <button
        type="button"
        className={`theo-wordpad-footer-btn reject ${state === 'rejected' ? 'active' : ''}`}
        onClick={onReject}
        disabled={rejectDisabled}
        title={tooltip ?? 'Reject'}
      >
        ✗ Reject
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Media view — figures / mosaics / hero
// ---------------------------------------------------------------------------

function MediaView({
  block,
  onImageClick,
  lightboxStart,
}: {
  block: Block
  onImageClick: (idx: number) => void
  lightboxStart: number
}) {
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
        <img src={f.src} alt={f.title || ''} loading="lazy" onClick={() => onImageClick(lightboxStart)} />
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

  return null
}
