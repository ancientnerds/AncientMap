/**
 * PaperArticle — one public research paper as an article: hero image,
 * header, meta line, lead-in summary and the report body the pipeline's
 * markdown renderer produced (nh3-sanitized, injected verbatim).
 *
 * Extracted from ResearchPaperPage (2026-09-10) because the homepage Papers
 * window shows the SAME article, not a teaser of it — the lead's payload
 * carries body_html just like /research/{slug} does, so the markup is one
 * definition. Lives under components/theo/ with the rest of Theo's paper
 * rendering (TheoPaperBody, theo.css).
 *
 * Everything that needs page state stays in the page and arrives through a
 * slot: `lead` is what goes above the title (breadcrumbs), `actions` is the
 * tail of the meta line (share, Medium copy, the TTS player — all effect
 * driven), `children` is the tail below the body (back link, Discord CTA).
 */

import SanitizedMarkdownHtml from '../../seo/SanitizedMarkdownHtml'
import { isoDate } from '../../seo/display'
import AiFootnote from '../news/AiFootnote'

import '../../styles/paper-article.css'

/** The fields both /research/{slug} and the homepage paper lead carry. */
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
  /** h1 on the paper page, h3 inside the homepage window (below its h2 label). */
  headingLevel: 'h1' | 'h3'
  /** Wraps the title in a link — the window's way back to the page. */
  headlineHref?: string
  /**
   * Reading time of the WHOLE report, or null to leave the item out. The page
   * measures it off body_html; the homepage window must not, because its
   * body_html is an excerpt — counting that announced "1 min read" for a
   * 28-minute paper. The window passes the payload's own `minutes`.
   */
  minutes: number | null
  /**
   * Art.-50 footnote under the body. The paper page marks its text with a
   * page-level <AiNoticeBanner> instead; the homepage window has no page to
   * put a banner on, so the excerpt carries the marking itself.
   */
  aiNotice?: boolean
  lead?: React.ReactNode
  actions?: React.ReactNode
  children?: React.ReactNode
}

/** ~200 words/min over the visible text of the rendered body HTML. */
export function readingMinutes(bodyHtml: string): number {
  const words = bodyHtml
    .replace(/<[^>]+>/g, ' ')
    .split(/\s+/)
    .filter(Boolean).length
  return Math.max(1, Math.ceil(words / 200))
}

export default function PaperArticle({
  paper,
  headingLevel,
  headlineHref,
  minutes,
  aiNotice,
  lead,
  actions,
  children,
}: Props) {
  const Heading = headingLevel
  const title = paper.title
  const author = paper.author || 'Theo'
  const pubDate = isoDate(paper.published_at)
  const summary = (paper.summary || '').trim()

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
          <Heading className="theo-paper-title">
            {headlineHref ? <a href={headlineHref}>{title}</a> : title}
          </Heading>
          <div className="theo-paper-meta">
            {minutes != null && (
              <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>
                {`${minutes} min read`}
              </span>
            )}
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
        {aiNotice && <AiFootnote />}
      </div>
    </>
  )
}
