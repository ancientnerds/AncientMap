/**
 * LandingWindow — the NERV window chrome the three live sections share.
 *
 * Extracted from LandingStories (2026-09-10) when the Journal and the
 * Papers section became windows too: title bar with the two window buttons
 * from nerv-ui/window.css, a body split into the article on the left and
 * the list of the other issues on the right. One definition, so the three
 * sections cannot drift apart.
 *
 * The window owns nothing but the frame — what runs inside it is the page's
 * own article component (StoryArticle, JournalArticle, PaperArticle) and
 * the section's own list.
 */
import type { ReactNode } from 'react'

interface Props {
  /** Bar caption, e.g. {'>_ stories.log — '}<b>{headline}</b>. */
  title: ReactNode
  /** ↗ — the page this window is running. */
  openHref: string
  openTitle: string
  /** ≡ — the archive of that page type. */
  archiveHref: string
  archiveTitle: string
  article: ReactNode
  /**
   * The element around the article column. 'div' where the component running
   * inside already renders its own <article> — JournalArticle does, and an
   * <article> inside an <article> is two article landmarks for one text.
   */
  articleTag?: 'article' | 'div'
  list: ReactNode
  /** aria-label of the list column — the only per-section word in the frame. */
  listLabel: string
}

export default function LandingWindow({
  title,
  openHref,
  openTitle,
  archiveHref,
  archiveTitle,
  article,
  articleTag: ArticleTag = 'article',
  list,
  listLabel,
}: Props) {
  return (
    <div className="ll-window">
      <div className="ll-window-bar">
        <span className="ll-window-title">{title}</span>
        <span className="popup-window-controls ll-window-controls">
          {/* title alone names nothing for a screen reader: the link text is
              an arrow glyph, so the same words have to be the accessible name. */}
          <a className="popup-window-btn" href={openHref} title={openTitle} aria-label={openTitle}>↗</a>
          <a className="popup-window-btn" href={archiveHref} title={archiveTitle} aria-label={archiveTitle}>≡</a>
        </span>
      </div>
      <div className="ll-window-body">
        <ArticleTag className="ll-window-article">{article}</ArticleTag>
        <nav className="ll-window-list" aria-label={listLabel}>
          {list}
        </nav>
      </div>
    </div>
  )
}
