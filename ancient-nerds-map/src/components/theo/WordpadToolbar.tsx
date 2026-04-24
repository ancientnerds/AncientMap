/**
 * WordpadToolbar — sticky toolbar targeting the currently focused block's
 * TipTap editor. Subscribes to that editor's selectionUpdate event so the
 * active state (e.g. Bold button lit when cursor is inside a <strong>)
 * reflects cursor position accurately.
 *
 * onMouseDown={e => e.preventDefault()} on every button is critical — without
 * it, clicking a button blurs the editor before the command can run, and the
 * command targets a stale selection.
 */

import { useEffect, useReducer, useCallback } from 'react'
import type { Editor } from '@tiptap/react'

interface WordpadToolbarProps {
  focusedEditor: Editor | null
}

export default function WordpadToolbar({ focusedEditor }: WordpadToolbarProps) {
  const [, force] = useReducer((x: number) => x + 1, 0)

  // Re-render whenever the focused editor's selection or content changes so
  // isActive(...) calls reflect current state.
  useEffect(() => {
    if (!focusedEditor) return
    const handler = () => force()
    focusedEditor.on('selectionUpdate', handler)
    focusedEditor.on('transaction', handler)
    return () => {
      focusedEditor.off('selectionUpdate', handler)
      focusedEditor.off('transaction', handler)
    }
  }, [focusedEditor])

  const setLink = useCallback(() => {
    if (!focusedEditor) return
    const previous = focusedEditor.getAttributes('link').href as string | undefined
    const url = window.prompt('URL', previous ?? '')
    if (url === null) return
    if (url === '') {
      focusedEditor.chain().focus().extendMarkRange('link').unsetLink().run()
    } else {
      focusedEditor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
    }
  }, [focusedEditor])

  const disabled = !focusedEditor
  const isActive = (name: string, attrs?: Record<string, unknown>) =>
    !!focusedEditor && focusedEditor.isActive(name, attrs)

  const cmd = (fn: (e: Editor) => void) => (ev: React.MouseEvent) => {
    ev.preventDefault()
    if (!focusedEditor) return
    fn(focusedEditor)
  }

  return (
    <div className="theo-wordpad-toolbar">
      <button
        type="button"
        className={`theo-editor-btn ${isActive('bold') ? 'active' : ''}`}
        onMouseDown={ev => ev.preventDefault()}
        onClick={cmd(e => e.chain().focus().toggleBold().run())}
        disabled={disabled}
        title="Bold"
        aria-label="Bold"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z" /><path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z" />
        </svg>
      </button>

      <button
        type="button"
        className={`theo-editor-btn ${isActive('italic') ? 'active' : ''}`}
        onMouseDown={ev => ev.preventDefault()}
        onClick={cmd(e => e.chain().focus().toggleItalic().run())}
        disabled={disabled}
        title="Italic"
        aria-label="Italic"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="19" y1="4" x2="10" y2="4" /><line x1="14" y1="20" x2="5" y2="20" /><line x1="15" y1="4" x2="9" y2="20" />
        </svg>
      </button>

      <span className="theo-editor-sep" />

      <button
        type="button"
        className={`theo-editor-btn ${isActive('heading', { level: 1 }) ? 'active' : ''}`}
        onMouseDown={ev => ev.preventDefault()}
        onClick={cmd(e => e.chain().focus().toggleHeading({ level: 1 }).run())}
        disabled={disabled}
        title="Heading 1"
        aria-label="Heading 1"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 12h8" /><path d="M4 18V6" /><path d="M12 18V6" /><path d="M17 12l3-2v8" />
        </svg>
      </button>

      <button
        type="button"
        className={`theo-editor-btn ${isActive('heading', { level: 2 }) ? 'active' : ''}`}
        onMouseDown={ev => ev.preventDefault()}
        onClick={cmd(e => e.chain().focus().toggleHeading({ level: 2 }).run())}
        disabled={disabled}
        title="Heading 2"
        aria-label="Heading 2"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 12h8" /><path d="M4 18V6" /><path d="M12 18V6" /><path d="M21 18h-4c0-4 4-3 4-6 0-1.5-2-2.5-4-1" />
        </svg>
      </button>

      <button
        type="button"
        className={`theo-editor-btn ${isActive('heading', { level: 3 }) ? 'active' : ''}`}
        onMouseDown={ev => ev.preventDefault()}
        onClick={cmd(e => e.chain().focus().toggleHeading({ level: 3 }).run())}
        disabled={disabled}
        title="Heading 3"
        aria-label="Heading 3"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 12h8" /><path d="M4 18V6" /><path d="M12 18V6" /><path d="M17.5 10.5c1.7-1 3.5 0 3.5 1.5a2 2 0 0 1-2 2c1.5 0 2 1 2 2a2 2 0 0 1-3.5 1.5" />
        </svg>
      </button>

      <span className="theo-editor-sep" />

      <button
        type="button"
        className={`theo-editor-btn ${isActive('link') ? 'active' : ''}`}
        onMouseDown={ev => ev.preventDefault()}
        onClick={setLink}
        disabled={disabled}
        title="Link"
        aria-label="Insert link"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      </button>

      <button
        type="button"
        className={`theo-editor-btn ${isActive('blockquote') ? 'active' : ''}`}
        onMouseDown={ev => ev.preventDefault()}
        onClick={cmd(e => e.chain().focus().toggleBlockquote().run())}
        disabled={disabled}
        title="Blockquote"
        aria-label="Blockquote"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z" /><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z" />
        </svg>
      </button>

      <button
        type="button"
        className={`theo-editor-btn ${isActive('bulletList') ? 'active' : ''}`}
        onMouseDown={ev => ev.preventDefault()}
        onClick={cmd(e => e.chain().focus().toggleBulletList().run())}
        disabled={disabled}
        title="Bullet list"
        aria-label="Bullet list"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
        </svg>
      </button>
    </div>
  )
}
