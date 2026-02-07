import { lazy, Suspense } from 'react'
import type { SiteData } from '../data/sites'
import './news/news-cards.css'

const SitePopup = lazy(() => import('./SitePopup'))

export function SitePopupOverlay({ site, onClose }: { site: SiteData; onClose: () => void }) {
  return (
    <div className="news-site-popup-overlay" onClick={onClose}>
      <div className="news-site-popup-inner" onClick={e => e.stopPropagation()}>
        <Suspense fallback={null}>
          <SitePopup site={site} onClose={onClose} isStandalone={true} />
        </Suspense>
      </div>
    </div>
  )
}
