/**
 * JournalArticle — one weekly journal issue as an article: title, meta line,
 * lead-in summary and the body the pipeline's markdown renderer produced.
 *
 * Extracted from ArticlesPage::ArticleFromPayload (2026-09-10) because the
 * homepage Journal window shows the SAME article, not a teaser of it — the
 * lead's payload carries body_html just like /articles/{slug} does, so the
 * markup is one definition.
 *
 * Two slots keep the page's own furniture out of the component: `lead` is
 * what goes above the title (the page puts its breadcrumbs there, the window
 * nothing) and `actions` is the right half of the meta line (share, copy
 * link, Medium — all page state). `children` is the tail below the body.
 */

import { isoDate } from '../../seo/display'
import AiFootnote from './AiFootnote'
import ArticleBody from './ArticleBody'

import '../../styles/journal-article.css'

/** The fields both /articles/{slug} and the homepage journal lead carry. */
export interface JournalArticleData {
  title: string
  summary: string | null
  published_at: string | null
  body_html: string
}

interface Props {
  article: JournalArticleData
  /** h1 on the journal page, h3 inside the homepage window (below its h2 label). */
  headingLevel: 'h1' | 'h3'
  /** Wraps the title in a link — the window's way back to the page. */
  headlineHref?: string
  /**
   * Art.-50 footnote under the body. The journal page marks its text with a
   * page-level <AiNoticeBanner> instead; the homepage window has no page to
   * put a banner on, so the excerpt carries the marking itself.
   */
  aiNotice?: boolean
  lead?: React.ReactNode
  actions?: React.ReactNode
  children?: React.ReactNode
}

export default function JournalArticle({
  article,
  headingLevel,
  headlineHref,
  aiNotice,
  lead,
  actions,
  children,
}: Props) {
  const Heading = headingLevel
  const pubDate = isoDate(article.published_at)
  const summary = (article.summary || '').trim()

  return (
    <article className="articles-reader">
      {lead}
      <Heading className="articles-reader-title">
        {headlineHref ? <a href={headlineHref}>{article.title}</a> : article.title}
      </Heading>
      <div className="articles-reader-meta">
        {pubDate && <span className="articles-reader-date">{pubDate}</span>}
        {actions}
      </div>
      {/* Lead-in summary, exactly like the Python fragment rendered it. */}
      {summary && (
        <p>
          <strong>{summary}</strong>
        </p>
      )}
      <ArticleBody html={article.body_html} className="articles-reader-body" />
      {children}
      {aiNotice && <AiFootnote />}
    </article>
  )
}
