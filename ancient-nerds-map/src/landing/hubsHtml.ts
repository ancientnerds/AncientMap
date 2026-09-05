/**
 * Homepage hub lists — static HTML for index.html, built at build time.
 *
 * index.html is a static Vite entry with no server behind it, so the only
 * way its crawlable links can reach the 98 country hubs and the research
 * papers is to bake them in. The data is a DB snapshot committed as
 * src/data/hubs.snapshot.json (scripts/export_hubs.py); the Vite plugin in
 * vite.config.ts (landingHubs) replaces two placeholders in index.html with
 * the output of these builders. Why it matters: in the 2026-09-05 GSC
 * sample 45 % of the country hubs and 11 of 25 papers had never been
 * crawled — Google knew them only from the sitemap, no page linked them.
 *
 * Both builders refuse an empty snapshot: an empty section on the homepage
 * would be a silent regression, a failed build is not.
 */

import { escapeHtml } from '../utils/escapeHtml'

export interface CountryHub {
  country: string
  path: string
  sites: number
}

export interface PaperHub {
  slug: string
  path: string
  title: string
}

export function countryLinksHtml(countries: CountryHub[]): string {
  if (countries.length === 0) throw new Error('hubs snapshot has no countries — run scripts/export_hubs.py')
  return countries
    .map(c => `<a href="${escapeHtml(c.path)}">${escapeHtml(c.country)} <span>${c.sites}</span></a>`)
    .join('')
}

export function paperLinksHtml(papers: PaperHub[]): string {
  if (papers.length === 0) throw new Error('hubs snapshot has no papers — run scripts/export_hubs.py')
  return papers.map(p => `<a href="${escapeHtml(p.path)}">${escapeHtml(p.title)}</a>`).join('')
}
