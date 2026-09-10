/**
 * JournalArticle — one weekly journal issue as an article: title, meta line,
 * lead-in summary and the body the pipeline's markdown renderer produced.
 *
 * Extracted from ArticlesPage::ArticleFromPayload (2026-09-10) so the issue
 * markup is one definition, separate from the page shell around it.
 *
 * Two slots keep the page's own furniture out of the component: `lead` is
 * what goes above the title (the breadcrumbs) and `actions` is the right
 * half of the meta line (share, copy link, Medium — all page state).
 * `children` is the tail below the body.
 */

import { isoDate } from '../../seo/display'
import ArticleBody from './ArticleBody'

import '../../styles/journal-article.css'

/** The fields /articles/{slug} carries. */
export interface JournalArticleData {
  title: string
  summary: string | null
  published_at: string | null
  body_html: string
}

interface Props {
  article: JournalArticleData
  lead?: React.ReactNode
  actions?: React.ReactNode
  children?: React.ReactNode
}

export default function JournalArticle({ article, lead, actions, children }: Props) {
  const pubDate = isoDate(article.published_at)
  const summary = (article.summary || '').trim()

  return (
    <article className="articles-reader">
      {lead}
      <h1 className="articles-reader-title">{article.title}</h1>
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
    </article>
  )
}
