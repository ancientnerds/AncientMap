import { useMemo, useEffect, useState, lazy, Suspense } from 'react'

import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import SitePopup from '../components/SitePopup/SitePopup'
import { useSiteDetailData } from '../components/SiteDetail/useSiteDetailData'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import type { LyraContextType } from '../types/ai'
import { anRoute } from '../types/anRoute'

import '../styles/site-page.css'

const LyraChatModal = lazy(() => import('../components/LyraChatModal'))

export default function SitePage() {
  // /sites/{country}/{slug} carries the resolved id; /site.html?id= is the legacy form.
  const siteId = useMemo(() => {
    const route = anRoute()
    if (route?.type === 'site') return route.id
    return new URLSearchParams(window.location.search).get('id')
  }, [])

  const { site, isLoading, error } = useSiteDetailData(siteId)
  const [showLyra, setShowLyra] = useState(false)
  const [lyraContext, setLyraContext] = useState<{ type: LyraContextType; id: string }>({ type: 'global', id: '' })

  useEffect(() => {
    if (site) {
      document.title = `${site.title} - Ancient Nerds`
    }
  }, [site?.title])

  if (isLoading) {
    return (
      <div className="site-page">
        <PageHeader currentPage="site"><span className="page-header-title">Loading...</span></PageHeader>
        <div className="site-page-loading">
          <div className="site-page-spinner" />
          <span>Loading site details...</span>
        </div>
      </div>
    )
  }

  if (error || !site) {
    return (
      <div className="site-page">
        <PageHeader currentPage="site"><span className="page-header-title">Site Not Found</span></PageHeader>
        <div className="site-page-error">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          <h2>{error || 'Site not found'}</h2>
          <p>The archaeological site you're looking for could not be loaded.</p>
          <a href="/globe.html" className="site-page-back-link">Explore the globe</a>
        </div>
      </div>
    )
  }

  const flagUrl = site?.location ? getCountryFlatFlagUrl(site.location) : null

  return (
    <div className="site-page">
      <PageHeader currentPage="site" hideLyra>
        <span className="page-header-title">
          {site.title}
          {site.location && (
            <>
              {' '}&mdash;{' '}
              {flagUrl && (
                <img src={flagUrl} alt="" className="page-header-flag" />
              )}
              {site.location}
            </>
          )}
        </span>
      </PageHeader>
      <SitePopup
        isStandalone={true}
        site={site}
        onClose={() => { window.location.href = '/globe.html' }}
        onAskLyra={(ctxType, ctxId) => {
          setLyraContext({ type: ctxType, id: ctxId })
          setShowLyra(true)
        }}
      />
      <Suspense fallback={null}>
        <LyraChatModal
          isOpen={showLyra}
          onClose={() => setShowLyra(false)}
          contextType={lyraContext.type}
          contextId={lyraContext.id}
        />
      </Suspense>
      {/* In standalone mode SitePopup renders in normal document flow (see
          SitePopup.tsx:969), so the block sits below the record. Without it
          the detail page loses its only way into the globe on hydration —
          37 links before, 12 after (audit 2026-08-09). */}
      <div className="site-page-cta">
        <CommunityCta />
      </div>
    </div>
  )
}
