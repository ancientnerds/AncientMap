/**
 * LandingWindow — the NERV window chrome the three live sections share.
 *
 * Extracted from LandingStories (2026-09-10) when the Journal and the
 * Papers section became windows too: title bar with the window buttons from
 * nerv-ui/window.css, a body split into the portal on the left and the list
 * of the section's items on the right. One definition, so the three
 * sections cannot drift apart.
 *
 * The window owns nothing but the frame — what runs inside it is a
 * <PagePortal> on the section's page and the section's own list.
 */
import type { ReactNode } from 'react'

interface Props {
  /** Bar caption, e.g. {'>_ portal — '}<b>/news.html</b>. */
  title: ReactNode
  /** ↗ — the page this window is showing. */
  openHref: string
  openTitle: string
  /**
   * ≡ — the archive of that page type, when that is a different page.
   * Stories are the only section with one (/news.html vs /news-archive/):
   * the journal hub and the research library ARE their own archive, and a
   * second button on the same href is a link that leads nowhere new.
   */
  archive?: { href: string; title: string }
  /** Left column: the portal. */
  main: ReactNode
  list: ReactNode
  /** aria-label of the list column — the only per-section word in the frame. */
  listLabel: string
}

export default function LandingWindow({
  title,
  openHref,
  openTitle,
  archive,
  main,
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
          {archive && (
            <a className="popup-window-btn" href={archive.href} title={archive.title} aria-label={archive.title}>≡</a>
          )}
        </span>
      </div>
      <div className="ll-window-body">
        <div className="ll-window-main">{main}</div>
        <nav className="ll-window-list" aria-label={listLabel}>
          {list}
        </nav>
      </div>
    </div>
  )
}
