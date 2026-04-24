/**
 * wordpadMarkdown — markdown <-> HTML converters for per-block TipTap editors.
 *
 * Each function operates on ONE block at a time (paragraph / heading / list /
 * blockquote) — never on a whole paper. That keeps the regex surface small
 * and avoids the lossy whole-doc conversion that made the old TheoEditor
 * mangle citation markers and figure syntax.
 *
 * Citation markers like `[1]` pass through as literal text (no rule matches
 * them). site:, lyra-video:, and other custom protocols also pass through —
 * TipTap's Link extension just stores them as href.
 */

export function markdownToHtml(md: string): string {
  let html = md

  // Escape HTML entities first (except ones we'll produce)
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Blockquotes: gather consecutive > lines into a single blockquote
  html = html.replace(/(?:^|\n)((?:&gt; ?.+(?:\n|$))+)/g, (_match, block: string) => {
    const inner = block.replace(/^&gt; ?/gm, '').trim()
    return `\n<blockquote>${inner}</blockquote>\n`
  })

  // Headings (# ## ###)
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')

  // Images ![alt](url) — must run before the link rule so ! is seen first
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" />')

  // Bold + italic combined
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // Italic
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')

  // Links [text](url) — matches citation link anchors too; they are preserved
  // because the text inside [] has been escaped already and TipTap stores the
  // href verbatim.
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
      // Already a block element — don't double-wrap
      if (/^<(?:h[1-6]|ul|ol|li|blockquote|p)[\s>]/i.test(trimmed)) return trimmed
      return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`
    })
    .filter(Boolean)
    .join('\n')

  return html
}

export function htmlToMarkdown(html: string): string {
  let md = html

  // Headings
  md = md.replace(/<h1[^>]*>([\s\S]*?)<\/h1>/gi, '# $1\n\n')
  md = md.replace(/<h2[^>]*>([\s\S]*?)<\/h2>/gi, '## $1\n\n')
  md = md.replace(/<h3[^>]*>([\s\S]*?)<\/h3>/gi, '### $1\n\n')

  // Images (handle both src-first and alt-first attribute order)
  md = md.replace(/<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*\/?>/gi, '![$2]($1)')
  md = md.replace(/<img[^>]*alt="([^"]*)"[^>]*src="([^"]*)"[^>]*\/?>/gi, '![$1]($2)')
  md = md.replace(/<img[^>]*src="([^"]*)"[^>]*\/?>/gi, '![]($1)')

  // Bold and italic
  md = md.replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, '**$1**')
  md = md.replace(/<em[^>]*>([\s\S]*?)<\/em>/gi, '*$1*')

  // Links
  md = md.replace(/<a[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi, '[$2]($1)')

  // List items and lists. TipTap emits <ul><li><p>text</p></li>...</ul>; the
  // paragraph wrap gets stripped first, then each li becomes a "- text\n" line.
  md = md.replace(/<li[^>]*><p[^>]*>([\s\S]*?)<\/p><\/li>/gi, '- $1\n')
  md = md.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, '- $1\n')
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

  return md.trim()
}

/**
 * Compare a TipTap editor's current markdown output against the original
 * block content. Returns true if the content has meaningfully changed
 * (ignoring cosmetic whitespace differences TipTap introduces).
 */
export function isDirty(editorHtml: string, originalMarkdown: string): boolean {
  const current = htmlToMarkdown(editorHtml).trim()
  const original = originalMarkdown.trim()
  return current !== original
}
