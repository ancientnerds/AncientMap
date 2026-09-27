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
 *
 * A Claude-written paper (studio spec 2026-09-26 §2.7, §3.7) adds three
 * optional parts: the writer disclosure under the meta line, its videos
 * between summary and body, and the corrections log after the body. Its
 * evidence anchors are already inside body_html. A paper without these
 * fields renders exactly the markup it always did.
 */

import SanitizedMarkdownHtml from '../../seo/SanitizedMarkdownHtml'
import { isoDate } from '../../seo/display'
import type { ResearchCorrection, ResearchVideo, ResearchWriter } from '../../types/anRoute'
import PaperCorrections from './PaperCorrections'
import PaperDisclosure from './PaperDisclosure'
import PaperVideo from './PaperVideo'
import { latestCorrectionDate } from './paperExtras'

import '../../styles/paper-article.css'
import '../../styles/paper-extras.css'

/** The fields /research/{slug} carries. */
export interface PaperArticleData {
  title: string
  summary: string | null
  /** published_by; null means the Theo pipeline. */
  author: string | null
  published_at: string | null
  hero_image_url: string | null
  body_html: string
  videos?: ResearchVideo[]
  corrections?: ResearchCorrection[]
  writer?: ResearchWriter
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
  const corrections = paper.corrections ?? []
  const correctedOn = corrections.length > 0 ? latestCorrectionDate(corrections) : ''

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
            {correctedOn && (
              <a href="#corrections" className="theo-paper-corrected">{`Corrected ${correctedOn}`}</a>
            )}
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>CC BY 4.0</span>
            {actions}
          </div>
          {paper.writer && <PaperDisclosure writer={paper.writer} />}
        </div>

        {/* Lead-in summary, exactly like the Python fragment rendered it. */}
        {summary && (
          <p>
            <strong>{summary}</strong>
          </p>
        )}

        {paper.videos?.map((video, i) => (
          <PaperVideo key={`${video.youtube_id}-${i}`} video={video} />
        ))}

        {/* Paper body — the pipeline's markdown rendering, verbatim. */}
        <SanitizedMarkdownHtml
          html={paper.body_html}
          className="theo-paper-body theo-md-body"
        />

        {corrections.length > 0 && <PaperCorrections corrections={corrections} />}

        {children}
      </div>
    </>
  )
}
