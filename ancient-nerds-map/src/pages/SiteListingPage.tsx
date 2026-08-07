/**
 * SiteListingPage — the crawlable browse hubs at /sites/ and /sites/{country}.
 *
 * These are the link path from the homepage down to each of the ~5,000
 * curated site pages. The listing arrives pre-rendered in
 * window.__AN_ROUTE__, so there is no fetch on mount.
 */

import PageHeader from '../components/layout/PageHeader'

import '../styles/story-page.css'

export interface CountryEntry {
  name: string
  count: number
  path: string
}

export interface SiteEntry {
  name: string
  path: string
  summary: string
}

export function SitesIndexPage({ countries }: { countries: CountryEntry[] }) {
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
          {total.toLocaleString()} curated sites in {countries.length} countries
        </div>
        <div className="site-country-grid">
          {countries.map(c => (
            <a key={c.path} className="site-country-card" href={c.path}>
              <span>{c.name}</span>
              <span className="site-country-count">{c.count}</span>
            </a>
          ))}
        </div>
      </main>
    </div>
  )
}

export function CountrySitesPage({ country, sites }: { country: string; sites: SiteEntry[] }) {
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
        <div className="story-meta">{sites.length} curated sites</div>
        <div className="story-archive-list">
          {sites.map(s => (
            <a key={s.path} className="story-archive-card" href={s.path}>
              <h3>{s.name}</h3>
              {s.summary && <p>{s.summary}</p>}
            </a>
          ))}
        </div>
      </main>
    </div>
  )
}
