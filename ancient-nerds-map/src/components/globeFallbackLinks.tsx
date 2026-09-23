import type { ReactNode } from 'react'
import { BRAND_NAME, BRAND_SUBTITLE, BRAND_ASSETS } from '../constants/brand'

/**
 * The full-screen notices of /globe.html - the phone gate, the unsupported
 * screen and the error screen - share one layout (the phone gate's classes,
 * index.css `.mobile-*`) and one set of links to the pages that work without
 * the 3D globe. One definition, so the three screens cannot drift apart.
 */

export type FallbackPage = 'stories' | 'radar' | 'journal' | 'lyra' | 'db'

interface FallbackLinkDef {
  href: string
  label: string
  icon: ReactNode
}

export const FALLBACK_LINKS: Record<FallbackPage, FallbackLinkDef> = {
  stories: {
    href: '/news.html',
    label: 'Stories',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1m2 13a2 2 0 0 1-2-2V7m2 13a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-2" /></svg>,
  },
  radar: {
    href: '/radar.html',
    label: 'Radar',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83" /></svg>,
  },
  journal: {
    href: '/articles.html',
    label: 'Journal',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>,
  },
  lyra: {
    href: '/lyra.html',
    label: 'Lyra',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>,
  },
  db: {
    href: '/db.html',
    label: 'Database',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2C6.48 2 2 3.79 2 6v12c0 2.21 4.48 4 10 4s10-1.79 10-4V6c0-2.21-4.48-4-10-4zM2 12c0 2.21 4.48 4 10 4s10-1.79 10-4" /></svg>,
  },
}

/** The globe icon of the gate's "3D Globe" button, reused by "Reload the globe". */
export const GLOBE_ICON = <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="M2 12h20" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></svg>

export function FallbackLink({ page, onClick }: { page: FallbackPage; onClick?: () => void }) {
  const link = FALLBACK_LINKS[page]
  return (
    <a className="mobile-action-btn" href={link.href} onClick={onClick}>
      {link.icon}
      {link.label}
    </a>
  )
}

/** The notice layout: brand, message, hint, then rows of actions (children). */
export function GlobeFallbackScreen({ message, hint, children }: { message: ReactNode; hint: ReactNode; children: ReactNode }) {
  return (
    <div className="mobile-overlay">
      <div className="mobile-overlay-content">
        <img src={BRAND_ASSETS.logo} alt="" className="mobile-logo-icon" />
        <div className="mobile-logo-main">{BRAND_NAME}</div>
        <div className="mobile-logo-sub">{BRAND_SUBTITLE}</div>
        <div className="mobile-message">
          {message}
        </div>
        <div className="mobile-hint">
          {hint}
        </div>
        <div className="mobile-actions">
          {children}
        </div>
      </div>
    </div>
  )
}
