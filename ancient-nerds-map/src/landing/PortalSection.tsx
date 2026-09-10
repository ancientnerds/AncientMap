/**
 * PortalSection — one homepage section: label, NERV window, portal, foot.
 *
 * The four sections (Stories, Journal, Papers, Sites) have the same shape and
 * differ only in what they point at, so the shape is written once (owner,
 * 2026-09-11: "unified code, no spaghetti") and LandingLive.tsx lists the
 * four as data. A section is a portal on ONE page: that page is the window
 * caption, the ↗ button, the frame source, the CTA target and the foot link —
 * one prop, `page`, so the five cannot drift apart. What a section has beyond
 * the shape — the Theo line under the papers — comes in as children, between
 * the window and the foot.
 */
import type { ReactNode } from 'react'

import LandingWindow from './LandingWindow'
import PagePortal from './PagePortal'
import SectionHead from './SectionHead'

export interface PortalSectionProps {
  /** DOM id, e.g. "stories-live" — the scroll target of in-page links. */
  id: string
  fig: number
  /** The name in the `>_ [ fig. N — name ]` label, e.g. "stories, live". */
  name: string
  /** The status beside it, e.g. "3,189 stories · newest first". */
  status: string
  /** The page this section is a portal on, e.g. "/news.html". */
  page: string
  /**
   * What the frame and the poster show when that is not the bare page:
   * "/search.html?random" opens the search on a random draw, because an
   * empty search bar is a view of nothing. Every link still leads to `page`.
   */
  view?: string
  /** Its screenshot under /data/previews/, e.g. "/data/previews/news.jpg". */
  poster: string
  /** The page's name for people — poster alt and frame title. */
  title: string
  /** "Open stories" — the ↗ button, the CTA and both their accessible names. */
  openLabel: string
  /** The ≡ button, only where the archive is a different page (LandingWindow). */
  archive?: { href: string; title: string }
  /** The foot: a note on the left, the link into `page` on the right. */
  foot: { note: string; link: string }
  children?: ReactNode
}

export default function PortalSection({
  id,
  fig,
  name,
  status,
  page,
  view,
  poster,
  title,
  openLabel,
  archive,
  foot,
  children,
}: PortalSectionProps) {
  return (
    <section className="ll-section" id={id} aria-labelledby={`ll-fig-${fig}`}>
      <SectionHead fig={fig} name={name} status={status} />
      <LandingWindow page={page} openTitle={openLabel} archive={archive}>
        <PagePortal src={view ?? page} poster={poster} title={title} openHref={page} openLabel={openLabel} />
      </LandingWindow>
      {children}
      <div className="ll-foot">
        <span>{foot.note}</span>
        <a href={page}>{foot.link}</a>
      </div>
    </section>
  )
}
