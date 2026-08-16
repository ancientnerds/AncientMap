/**
 * SiteListingPage — the crawlable browse hubs at /sites/ and /sites/{country}.
 *
 * These are the link path from the homepage down to each of the ~5,000
 * curated site pages. The listing arrives pre-rendered in the
 * server-injected route, so there is no fetch on mount.
 */

import { useMemo, useState } from 'react'

import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import { periodSpan, typeSections } from '../seo/grouping'
import { slugify } from '../seo/meta'
import { useRoute } from '../seo/RouteContext'
import { blurb } from '../seo/text'
import type { CountrySite } from '../types/anRoute'

import '../styles/story-page.css'

export function SitesIndexPage() {
  // Das Payload kommt aus dem Route-Kontext; die Typen aus SitesIndexRoute.
  const route = useRoute()
  if (route?.type !== 'sitesIndex') return null
  const { countries } = route
  const total = countries.reduce((sum, c) => sum + c.count, 0)

  return (
    <div className="story-page">
      <PageHeader currentPage="search">
        <span className="page-header-title">Sites</span>
      </PageHeader>
      <main className="story-main">
        <nav className="story-crumb">
          <a href="/">Home</a> / Sites
        </nav>
        <h1 className="story-title">Archaeological Sites by Country</h1>
        <div className="story-meta">
          {/* Explizites en-US wie in StoryArchivePage: das Default-Locale wäre
              das des SSR-Hosts — Pythons f"{total:,}" schrieb "5,012". */}
          {total.toLocaleString('en-US')} curated sites in {countries.length} countries
        </div>
        <div className="site-country-grid">
          {countries.map(c => (
            <a key={c.path} className="site-country-card" href={c.path}>
              <span>{c.name}</span>
              <span className="site-country-count">{c.count}</span>
            </a>
          ))}
        </div>
        <CommunityCta />
      </main>
    </div>
  )
}

function SiteCard({ site }: { site: CountrySite }) {
  const meta = [site.site_type, site.period_name].filter(Boolean).join(' · ')
  const summary = blurb(site.description)
  return (
    <a className="story-archive-card site-list-card" href={site.path}>
      {site.thumbnail_url && (
        <img className="site-list-card-thumb" src={site.thumbnail_url} alt={site.name} loading="lazy" />
      )}
      <div className="site-list-card-body">
        <h3>{site.name}</h3>
        {summary && <p>{summary}</p>}
        {meta && <div className="site-list-card-meta">{meta}</div>}
      </div>
    </a>
  )
}

export function CountrySitesPage() {
  const route = useRoute()
  // The crawler fragment can only offer anchor jumps; with JS the same chips
  // narrow the list instead of scrolling to it. (Hooks vor dem Type-Guard —
  // Hooks dürfen nicht hinter einem konditionalen return stehen.)
  const [activeType, setActiveType] = useState<string | null>(null)
  // Das Payload trägt die rohen Zeilen (react-ssr Task 10); gruppiert wird
  // hier — mit derselben typeSections()-Definition wie in countryMeta.
  const sites = route?.type === 'country' ? route.sites : []
  const sections = useMemo(() => typeSections(sites), [sites])
  if (route?.type !== 'country') return null
  const { country } = route
  const total = sites.length
  const span = periodSpan(sites)
  const shown = activeType ? sections.filter(s => s.label === activeType) : sections

  return (
    <div className="story-page">
      <PageHeader currentPage="search">
        <span className="page-header-title">{country}</span>
      </PageHeader>
      <main className="story-main">
        <nav className="story-crumb">
          <a href="/">Home</a> / <a href="/sites/">Sites</a> / {country}
        </nav>
        <h1 className="story-title">Archaeological Sites in {country}</h1>
        <div className="story-meta">
          {total} curated sites{span && ` · ${span}`}
        </div>
        {sections.length > 1 && (
          <div className="site-type-chips">
            <button
              type="button"
              className={`site-type-chip${activeType === null ? ' is-active' : ''}`}
              onClick={() => setActiveType(null)}
            >
              All <span className="site-type-count">{total}</span>
            </button>
            {sections.map(s => (
              <button
                key={s.label}
                type="button"
                className={`site-type-chip${activeType === s.label ? ' is-active' : ''}`}
                onClick={() => setActiveType(activeType === s.label ? null : s.label)}
              >
                {s.label} <span className="site-type-count">{s.sites.length}</span>
              </button>
            ))}
          </div>
        )}
        {shown.map(section => (
          <section key={section.label}>
            <h2 className="site-section-title" id={slugify(section.label)}>
              {section.label} in {country} ({section.sites.length})
            </h2>
            <div className="story-archive-list">
              {section.sites.map(s => (
                <SiteCard key={s.path} site={s} />
              ))}
            </div>
          </section>
        ))}
        <CommunityCta />
      </main>
    </div>
  )
}
