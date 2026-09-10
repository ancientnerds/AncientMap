/**
 * PaperArticle — one public research paper as an article: hero image,
 * header, meta line, lead-in summary and the report body the pipeline's
 * markdown renderer produced (nh3-sanitized, injected verbatim).
 *
 * Extracted from ResearchPaperPage (2026-09-10) so the paper markup is one
 * definition, separate from the page shell around it. Lives under
 * components/theo/ with the rest of Theo's paper rendering (TheoPaperBody,
 * theo.css).
 *
 * Everything that needs page state stays in the page and arrives through a
 * slot: `lead` is what goes above the title (breadcrumbs), `actions` is the
 * tail of the meta line (share, Medium copy, the TTS player — all effect
 * driven), `children` is the tail below the body (back link, Discord CTA).
 */

import SanitizedMarkdownHtml from '../../seo/SanitizedMarkdownHtml'
import { isoDate } from '../../seo/display'

import '../../styles/paper-article.css'

/** The fields /research/{slug} carries. */
export interface PaperArticleData {
  title: string
  summary: string | null
  /** published_by; null means the Theo pipeline. */
  author: string | null
  published_at: string | null
  hero_image_url: string | null
  body_html: string
}

interface Props {
  paper: PaperArticleData
  lead?: React.ReactNode
  actions?: React.ReactNode
  children?: React.ReactNode
}

/** ~200 words/min over the visible text of the rendered body HTML. */
function readingMinutes(bodyHtml: string): number {
  const words = bodyHtml
    .replace(/<[^>]+>/g, ' ')
    .split(/\s+/)
    .filter(Boolean).length
  return Math.max(1, Math.ceil(words / 200))
}

export default function PaperArticle({ paper, lead, actions, children }: Props) {
  const title = paper.title
  const author = paper.author || 'Theo'
  const pubDate = isoDate(paper.published_at)
  const summary = (paper.summary || '').trim()
  const minutes = readingMinutes(paper.body_html)

  return (
    <>
      {paper.hero_image_url && (
        <figure className="theo-paper-hero">
          <img src={paper.hero_image_url} alt={title} className="theo-paper-hero-img" />
        </figure>
      )}

      <div className="theo-paper-page">
        {/* Paper header */}
        <div className="theo-paper-header">
          {lead}
          <h1 className="theo-paper-title">{title}</h1>
          <div className="theo-paper-meta">
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>
              {`${minutes} min read`}
            </span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {`by ${author}${author === 'Theo' ? ' · AI research agent' : ''}`}
            </span>
            {pubDate && (
              <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>{pubDate}</span>
            )}
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>CC BY 4.0</span>
            {actions}
          </div>
        </div>

        {/* Lead-in summary, exactly like the Python fragment rendered it. */}
        {summary && (
          <p>
            <strong>{summary}</strong>
          </p>
        )}

        {/* Paper body — the pipeline's markdown rendering, verbatim. */}
        <SanitizedMarkdownHtml
          html={paper.body_html}
          className="theo-paper-body theo-md-body"
        />

        {children}
      </div>
    </>
  )
}
