import { lazy, Suspense, useCallback } from 'react'
import type { SiteData } from '../data/sites'
import './news/news-cards.css'

const SitePopup = lazy(() => import('./SitePopup'))

export function SitePopupOverlay({ site, onClose }: { site: SiteData; onClose: () => void }) {
  const handleAskLyra = useCallback((_type: string, id: string) => {
    window.open(`/lyra.html?site=${id}`, '_blank')
  }, [])

  return (
    <div className="news-site-popup-overlay" onClick={onClose}>
      <div className="news-site-popup-inner" onClick={e => e.stopPropagation()}>
        <Suspense fallback={null}>
          <SitePopup
            site={site}
            onClose={onClose}
            isStandalone={true}
            onAskLyra={handleAskLyra}
          />
        </Suspense>
      </div>
    </div>
  )
}
