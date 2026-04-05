/**
 * TheoEditor — TipTap WYSIWYG editor for research papers.
 * Converts markdown <-> HTML on mount/save. Toolbar mirrors the read-view styling.
 */

import { useCallback, useMemo } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'

// ---------------------------------------------------------------------------
// Markdown -> HTML (simple regex, no library)
// ---------------------------------------------------------------------------

function markdownToHtml(md: string): string {
  let html = md

  // Escape HTML entities first (except ones we'll produce)
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Blockquotes (must come before paragraph splitting)
  // Gather consecutive > lines into a single blockquote
  html = html.replace(/(?:^|\n)((?:&gt; ?.+(?:\n|$))+)/g, (_match, block: string) => {
    const inner = block.replace(/^&gt; ?/gm, '').trim()
    return `\n<blockquote>${inner}</blockquote>\n`
  })

  // Headings (# ## ###)
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')

  // Bold + italic combined
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // Italic
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')

  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')

  // Unordered lists: consecutive lines starting with - or *
  html = html.replace(/(?:^|\n)((?:(?:- |\* ).+(?:\n|$))+)/g, (_match, block: string) => {
    const items = block
      .split('\n')
      .filter(l => l.match(/^(?:- |\* )/))
      .map(l => `<li>${l.replace(/^(?:- |\* )/, '')}</li>`)
      .join('')
    return `\n<ul>${items}</ul>\n`
  })

  // Paragraphs: split on double newline, wrap non-tag lines in <p>
  const blocks = html.split(/\n{2,}/)
  html = blocks
    .map(b => {
      const trimmed = b.trim()
      if (!trimmed) return ''
      // Already a block element
      if (/^<(?:h[1-6]|ul|ol|li|blockquote|p)[\s>]/i.test(trimmed)) return trimmed
      return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`
    })
    .filter(Boolean)
    .join('\n')

  return html
}

// ---------------------------------------------------------------------------
// HTML -> Markdown (simple DOM-free conversion)
// ---------------------------------------------------------------------------

function htmlToMarkdown(html: string): string {
  let md = html

  // Headings
  md = md.replace(/<h1[^>]*>([\s\S]*?)<\/h1>/gi, '# $1\n\n')
  md = md.replace(/<h2[^>]*>([\s\S]*?)<\/h2>/gi, '## $1\n\n')
  md = md.replace(/<h3[^>]*>([\s\S]*?)<\/h3>/gi, '### $1\n\n')

  // Bold and italic
  md = md.replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, '**$1**')
  md = md.replace(/<em[^>]*>([\s\S]*?)<\/em>/gi, '*$1*')

  // Links
  md = md.replace(/<a[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi, '[$2]($1)')

  // List items and lists
  md = md.replace(/<li[^>]*><p[^>]*>([\s\S]*?)<\/p><\/li>/gi, '- $1')
  md = md.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, '- $1')
  md = md.replace(/<\/?[uo]l[^>]*>/gi, '')

  // Blockquotes
  md = md.replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, (_m, inner: string) => {
    return inner
      .split('\n')
      .map(line => `> ${line}`)
      .join('\n') + '\n\n'
  })

  // Paragraphs
  md = md.replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, '$1\n\n')

  // Line breaks
  md = md.replace(/<br\s*\/?>/gi, '\n')

  // Strip remaining tags
  md = md.replace(/<[^>]+>/g, '')

  // Decode entities
  md = md.replace(/&amp;/g, '&')
  md = md.replace(/&lt;/g, '<')
  md = md.replace(/&gt;/g, '>')
  md = md.replace(/&quot;/g, '"')
  md = md.replace(/&#39;/g, "'")

  // Collapse excessive blank lines
  md = md.replace(/\n{3,}/g, '\n\n')

  return md.trim() + '\n'
}

// ---------------------------------------------------------------------------
// TheoEditor component
// ---------------------------------------------------------------------------

interface TheoEditorProps {
  content: string        // markdown input
  onSave: (markdown: string) => void
  onDiscard: () => void
}

export default function TheoEditor({ content, onSave, onDiscard }: TheoEditorProps) {
  const initialHtml = useMemo(() => markdownToHtml(content), [content])

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { target: '_blank', rel: 'noopener noreferrer' },
      }),
    ],
    content: initialHtml,
  })

  const handleSave = useCallback(() => {
    if (!editor) return
    const html = editor.getHTML()
    const md = htmlToMarkdown(html)
    onSave(md)
  }, [editor, onSave])

  const setLink = useCallback(() => {
    if (!editor) return
    const previous = editor.getAttributes('link').href as string | undefined
    const url = window.prompt('URL', previous ?? '')
    if (url === null) return
    if (url === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run()
    } else {
      editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
    }
  }, [editor])

  const wordCount = editor?.state.doc.textContent.split(/\s+/).filter(Boolean).length ?? 0

  if (!editor) return null

  return (
    <div className="theo-editor">
      {/* Toolbar */}
      <div className="theo-editor-toolbar">
        <button
          type="button"
          className={`theo-editor-btn ${editor.isActive('bold') ? 'active' : ''}`}
          onClick={() => editor.chain().focus().toggleBold().run()}
          title="Bold"
          aria-label="Bold"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"/><path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"/>
          </svg>
        </button>

        <button
          type="button"
          className={`theo-editor-btn ${editor.isActive('italic') ? 'active' : ''}`}
          onClick={() => editor.chain().focus().toggleItalic().run()}
          title="Italic"
          aria-label="Italic"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="4" x2="10" y2="4"/><line x1="14" y1="20" x2="5" y2="20"/><line x1="15" y1="4" x2="9" y2="20"/>
          </svg>
        </button>

        <span className="theo-editor-sep" />

        <button
          type="button"
          className={`theo-editor-btn ${editor.isActive('heading', { level: 1 }) ? 'active' : ''}`}
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
          title="Heading 1"
          aria-label="Heading 1"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 12h8"/><path d="M4 18V6"/><path d="M12 18V6"/><path d="M17 12l3-2v8"/>
          </svg>
        </button>

        <button
          type="button"
          className={`theo-editor-btn ${editor.isActive('heading', { level: 2 }) ? 'active' : ''}`}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          title="Heading 2"
          aria-label="Heading 2"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 12h8"/><path d="M4 18V6"/><path d="M12 18V6"/><path d="M21 18h-4c0-4 4-3 4-6 0-1.5-2-2.5-4-1"/>
          </svg>
        </button>

        <button
          type="button"
          className={`theo-editor-btn ${editor.isActive('heading', { level: 3 }) ? 'active' : ''}`}
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
          title="Heading 3"
          aria-label="Heading 3"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 12h8"/><path d="M4 18V6"/><path d="M12 18V6"/><path d="M17.5 10.5c1.7-1 3.5 0 3.5 1.5a2 2 0 0 1-2 2c1.5 0 2 1 2 2a2 2 0 0 1-3.5 1.5"/>
          </svg>
        </button>

        <span className="theo-editor-sep" />

        <button
          type="button"
          className={`theo-editor-btn ${editor.isActive('link') ? 'active' : ''}`}
          onClick={setLink}
          title="Link"
          aria-label="Insert link"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
        </button>

        <button
          type="button"
          className={`theo-editor-btn ${editor.isActive('blockquote') ? 'active' : ''}`}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
          title="Blockquote"
          aria-label="Blockquote"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z"/><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z"/>
          </svg>
        </button>

        <button
          type="button"
          className={`theo-editor-btn ${editor.isActive('bulletList') ? 'active' : ''}`}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          title="Bullet list"
          aria-label="Bullet list"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
          </svg>
        </button>
      </div>

      {/* Editor content */}
      <div className="theo-editor-content theo-md-body">
        <EditorContent editor={editor} />
      </div>

      {/* Footer */}
      <div className="theo-editor-footer">
        <span className="theo-editor-wordcount">{wordCount.toLocaleString()} words</span>
        <button type="button" className="theo-editor-discard" onClick={onDiscard}>
          Discard
        </button>
        <button type="button" className="theo-editor-save" onClick={handleSave}>
          Save changes
        </button>
      </div>
    </div>
  )
}
