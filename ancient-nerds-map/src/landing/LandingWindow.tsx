/**
 * LandingWindow — the NERV window chrome every portal section shares.
 *
 * Extracted from LandingStories (2026-09-10) when the Journal and the Papers
 * section became windows too; since 2026-09-11 the frame around all four
 * portals (PortalSection.tsx). Title bar `>_ portal — {page}` with the window
 * buttons from nerv-ui/window.css, and a body that is one full-width column.
 * One definition, so the sections cannot drift apart.
 *
 * The window owns nothing but the frame — what runs inside it is a
 * <PagePortal> on `page`. The lists that used to sit beside the portal are
 * gone (owner: "Why do we still have the list of stories, journals and
 * research papers on the right side?").
 */
import type { ReactNode } from 'react'

interface Props {
  /** The page in the window, e.g. "/news.html" — the bar caption and the ↗ target. */
  page: string
  openTitle: string
  /**
   * ≡ — the archive of that page type, when that is a different page.
   * Stories have one (/news.html vs /news-archive/) and the site search has
   * its country hubs (/search.html vs /sites/); the journal hub and the
   * research library ARE their own archive, and a second button on the same
   * href is a link that leads nowhere new.
   */
  archive?: { href: string; title: string }
  /** The window body: the portal. */
  children: ReactNode
}

export default function LandingWindow({ page, openTitle, archive, children }: Props) {
  return (
    <div className="ll-window">
      <div className="ll-window-bar">
        <span className="ll-window-title">
          {'>_ portal — '}
          <b>{page}</b>
        </span>
        <span className="popup-window-controls ll-window-controls">
          {/* title alone names nothing for a screen reader: the link text is
              an arrow glyph, so the same words have to be the accessible name. */}
          <a className="popup-window-btn" href={page} title={openTitle} aria-label={openTitle}>↗</a>
          {archive && (
            <a className="popup-window-btn" href={archive.href} title={archive.title} aria-label={archive.title}>≡</a>
          )}
        </span>
      </div>
      <div className="ll-window-body">{children}</div>
    </div>
  )
}
