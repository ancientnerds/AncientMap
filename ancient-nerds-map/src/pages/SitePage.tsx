/**
 * SitePage — /sites/{country}/{slug}, the standalone view of one curated site.
 *
 * Since react-ssr Task 11 the route payload carries the whole record
 * (SiteRoute: raw row + related content), so the FIRST render — the one
 * renderToString and every crawler sees — needs no fetch: SiteRecord and
 * the related blocks below carry everything the old Python fragment had
 * (hero with Commons attribution, alt names, facts, news, resources,
 * parent, siblings, globe CTA). ~1,600 of these pages were filed as Soft
 * 404 while the first render was a loading spinner.
 *
 * SitePopup (map, gallery, admin) reads browser APIs during render
 * (localStorage, window.location), so it mounts only in the browser via
 * the `interactive` flag and replaces the static record — the related
 * links below stay, which is exactly what the 2026-08-09 audit demanded
 * (37 → 12 links lost on mount back then).
 */

import { useEffect, useMemo, useState, lazy, Suspense, Fragment } from 'react'

import Breadcrumbs from '../components/layout/Breadcrumbs'
import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import SitePopup from '../components/SitePopup/SitePopup'
import { globeUrlForSite } from '../constants/brand'
import { DataStore } from '../data/DataStore'
import { OfflineFetch } from '../services/OfflineFetch'
import { coordDisplay, periodDisplay } from '../seo/display'
import { countryPath } from '../seo/meta'
import { useRoute } from '../seo/RouteContext'
import type { LyraContextType } from '../types/ai'
import type { SiteRoute } from '../types/anRoute'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { apiDetailToSiteData } from '../utils/siteApi'

import '../styles/story-page.css'
import '../styles/site-page.css'

const LyraChatModal = lazy(() => import('../components/LyraChatModal'))

/**
 * The crawler/no-JS record: the payload rendered the way
 * pipeline/seo_pages.py::site_detail_page() rendered it. In the browser it
 * shows until SitePopup mounts (and forever without JavaScript).
 */
function SiteRecord({ site }: { site: SiteRoute }) {
  const siteType = site.site_type || 'Archaeological site'
  const period = periodDisplay(site)
  const coords = coordDisplay(site.lat, site.lon)
  const paragraphs = (site.description || '').split('\n').map(p => p.trim()).filter(Boolean)
  const altNames = site.alt_names.filter(n => n && n !== site.name).slice(0, 12)
  const image = site.image
  const credit = image ? [image.author, image.license].filter(Boolean).join(' · ') : ''

  return (
    <main className="story-main site-record">
      <h1 className="story-title">{site.name}</h1>
      <div className="story-meta">
        {siteType}
        {period && ` · ${period}`} · {site.country}
      </div>
      {image && (
        <figure>
          <img src={image.url} alt={site.name} loading="lazy" />
          {/* Commons licence attribution — required, not decorative. Without
              any credit content the Python fragment omitted the figcaption
              entirely; an empty <figcaption></figcaption> is markup noise. */}
          {(credit || image.commons_url) && (
            <figcaption>
              {image.commons_url ? (
                <a href={image.commons_url} target="_blank" rel="noopener noreferrer">
                  {credit || 'Wikimedia Commons'}
                </a>
              ) : (
                credit
              )}
            </figcaption>
          )}
        </figure>
      )}
      {altNames.length > 0 && (
        <p>
          <strong>Also known as:</strong> {altNames.join(', ')}
        </p>
      )}
      <div className="story-body">
        {paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </div>
      <table className="site-record-facts">
        <tbody>
          <tr>
            <th scope="row">Type</th>
            <td>{siteType}</td>
          </tr>
          {period && (
            <tr>
              <th scope="row">Period</th>
              <td>{period}</td>
            </tr>
          )}
          <tr>
            <th scope="row">Country</th>
            <td>
              <a href={countryPath(site.country)}>{site.country}</a>
            </td>
          </tr>
          {coords && (
            <tr>
              <th scope="row">Coordinates</th>
              <td>{coords}</td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  )
}

/**
 * Related content below the record. Rendered on the server AND kept after
 * SitePopup mounts — these internal links must survive hydration.
 */
function SiteRelatedContent({ site }: { site: SiteRoute }) {
  const links = site.links.filter(l => l.url)
  return (
    <div className="story-main site-related">
      {/* Derselbe Button wie im Abschlussblock — eine Klasse, eine Stufe in
          nerv-ui/button.css, kein zweiter Globus-Knopf mit eigenem Look. */}
      <div className="community-cta-actions">
        <a className="community-cta-btn" href={globeUrlForSite(site.id)}>
          Show this site on the globe
        </a>
      </div>
      {site.parent && (
        <p>
          Part of <a href={site.parent.path}>{site.parent.name}</a>
        </p>
      )}
      {site.news.length > 0 && (
        <section className="story-related">
          <h2>Stories about {site.name}</h2>
          <ul>
            {site.news.slice(0, 10).map(n => (
              <li key={n.slug}>
                <a href={`/news-archive/${n.slug}`}>{n.headline}</a>
              </li>
            ))}
          </ul>
        </section>
      )}
      {links.length > 0 && (
        <section className="story-related">
          <h2>Related resources</h2>
          <ul>
            {links.slice(0, 15).map(l => (
              <li key={l.url}>
                <a href={l.url} target="_blank" rel="noopener noreferrer">
                  {l.title || l.url}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
      {site.siblings.length > 0 && (
        <section className="story-related">
          <h2>More sites in {site.country}</h2>
          <p>
            {site.siblings.slice(0, 24).map((s, i) => (
              <Fragment key={s.path}>
                {i > 0 && ' · '}
                <a href={s.path}>{s.name}</a>
              </Fragment>
            ))}
          </p>
          <p>
            <a href={countryPath(site.country)}>All sites in {site.country} →</a>
          </p>
        </section>
      )}
      <CommunityCta />
    </div>
  )
}

export default function SitePage() {
  // /sites/{country}/{slug} carries the full record. The legacy
  // /site.html?id= form answers 301 since 1ad85ed, so the route payload is
  // the only source — and reading it from context keeps the render free of
  // window access.
  const route = useRoute()
  const site = route?.type === 'site' ? route : null

  // Browser-only gate: SitePopup reads localStorage/window during render
  // and cannot go through renderToString. Server and first client render
  // agree on the static record, then the effect swaps in the popup.
  const [interactive, setInteractive] = useState(false)
  useEffect(() => {
    // Standalone page loaded over HTTP — force online mode so SitePopup's
    // gallery/content fetches fire, and load the source metadata its header
    // shows (both lived in useSiteDetailData before react-ssr Task 11).
    OfflineFetch.setOfflineMode(false)
    let cancelled = false
    DataStore.loadSources().finally(() => {
      if (!cancelled) setInteractive(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const [showLyra, setShowLyra] = useState(false)
  const [lyraContext, setLyraContext] = useState<{ type: LyraContextType; id: string }>({ type: 'global', id: '' })

  // Same mapping the /api/sites/{id} response went through before Task 11 —
  // one definition (apiDetailToSiteData), fed from the payload instead.
  const popupSite = useMemo(
    () =>
      site
        ? apiDetailToSiteData({
            id: site.id,
            name: site.name,
            lat: site.lat ?? NaN,
            lon: site.lon ?? NaN,
            sourceId: 'ancient_nerds',
            type: site.site_type ?? undefined,
            periodStart: site.period_start,
            periodName: site.period_name ?? undefined,
            country: site.country,
            description: site.description ?? undefined,
            thumbnailUrl: site.image?.url,
            sourceUrl: site.source_url ?? undefined,
            bestWikiUrl: site.best_wiki_url ?? undefined,
            sourceLanguage: site.source_language ?? undefined,
            descriptionCitations: site.description_citations ?? undefined,
          })
        : null,
    [site],
  )

  if (!site || !popupSite) {
    return (
      <div className="site-page">
        <PageHeader currentPage="site"><span className="page-header-title">Site Not Found</span></PageHeader>
        <div className="site-page-error">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          <h2>Site not found</h2>
          <p>The archaeological site you're looking for could not be loaded.</p>
          <a href="/globe.html" className="site-page-back-link">Explore the globe</a>
        </div>
      </div>
    )
  }

  const flagUrl = getCountryFlatFlagUrl(site.country)

  return (
    <div className="site-page">
      <PageHeader currentPage="site" hideLyra>
        <span className="page-header-title">
          {site.name}
          {' '}&mdash;{' '}
          {flagUrl && (
            <img src={flagUrl} alt="" className="page-header-flag" />
          )}
          {site.country}
        </span>
      </PageHeader>
      {/* Ausserhalb des interactive-Zweigs: SiteRecord wird beim Mount durch
          SitePopup ersetzt, und mit ihm verschwand die Krümelnavigation samt
          BreadcrumbList-Schema — gemessen 2026-08-21, dieselbe Falle wie bei
          der h1. Google rendert JS, also muss beides beide Zustände
          überleben. */}
      <div className="story-main site-crumb-bar">
        <Breadcrumbs
          trail={[
            { name: 'Home', path: '/' },
            { name: 'Sites', path: '/sites/' },
            { name: site.country, path: countryPath(site.country) },
            { name: site.name },
          ]}
        />
      </div>
      {interactive ? (
        <SitePopup
          isStandalone={true}
          site={popupSite}
          onClose={() => { window.location.href = '/globe.html' }}
          onAskLyra={(ctxType, ctxId) => {
            setLyraContext({ type: ctxType, id: ctxId })
            setShowLyra(true)
          }}
        />
      ) : (
        <SiteRecord site={site} />
      )}
      {interactive && (
        <Suspense fallback={null}>
          <LyraChatModal
            isOpen={showLyra}
            onClose={() => setShowLyra(false)}
            contextType={lyraContext.type}
            contextId={lyraContext.id}
          />
        </Suspense>
      )}
      <SiteRelatedContent site={site} />
    </div>
  )
}
