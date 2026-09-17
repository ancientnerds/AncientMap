/**
 * Homepage hub list — static HTML for index.html, built at build time.
 *
 * index.html is a static Vite entry with no server behind it, so the only
 * way its crawlable links can reach the 98 country hubs is to bake them in.
 * The data is a DB snapshot committed as src/data/hubs.snapshot.json
 * (scripts/export_hubs.py); the Vite plugin in vite.config.ts (landingHubs)
 * replaces the placeholder in index.html with the output of the builder.
 * Why it matters: in the 2026-09-05 GSC sample 45 % of the country hubs had
 * never been crawled — Google knew them only from the sitemap, no page
 * linked them. (A paper list lived here too until 2026-09-10; the research
 * portal shows /research/, which links every paper, so the list said it
 * twice.)
 *
 * The builder refuses an empty snapshot: an empty section on the homepage
 * would be a silent regression, a failed build is not.
 */

import { escapeHtml } from '../utils/escapeHtml'

export interface CountryHub {
  country: string
  path: string
  sites: number
}

/**
 * Which snapshot the build reads, first existing wins. The order is a
 * precedence, not a fallback: on the VPS the pipeline rewrites
 * public/data/hubs.snapshot.json at every static export
 * (pipeline/static_exporter.py), so a deploy always bakes in the current
 * list; the committed src/data copy is the baseline that lets a
 * fresh checkout and CI build without a database. No snapshot at all is a
 * build error.
 */
export function pickSnapshotPath(candidates: string[], exists: (path: string) => boolean): string {
  const found = candidates.find(exists)
  if (!found) {
    throw new Error(
      `no hubs snapshot found — run scripts/export_hubs.py --baseline; looked at: ${candidates.join(', ')}`,
    )
  }
  return found
}

export function countryLinksHtml(countries: CountryHub[]): string {
  if (countries.length === 0) throw new Error('hubs snapshot has no countries — run scripts/export_hubs.py')
  return countries
    // data-umami-event: the landing page has no React, so the tracker's own
    // declarative attributes count the hub clicks (event `hub_click`).
    .map(
      c =>
        `<a href="${escapeHtml(c.path)}" data-umami-event="hub_click" data-umami-event-country="${escapeHtml(c.country)}">${escapeHtml(c.country)} <span>${c.sites}</span></a>`
    )
    .join('')
}
