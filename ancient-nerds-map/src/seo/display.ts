/**
 * Anzeige-Helfer der Site-Detailseite — Portierung von _coord_display()
 * und _period_display() aus pipeline/sites_html_renderer.py (react-ssr
 * plan, Task 11). yearDisplay (_year_display) lebt bereits in grouping.ts
 * und wird von dort importiert, nicht dupliziert.
 *
 * Das site-Payload trägt die rohe DB-Zeile (snake_case); wie Periode und
 * Koordinaten dargestellt werden, ist eine Darstellungsentscheidung und
 * lebt deshalb hier. Bis pipeline/seo_pages.py stirbt (Task 16), ist die
 * Python-Seite die maßgebliche Vorlage.
 */

import type { SiteRoute } from '../types/anRoute'

import { yearDisplay } from './grouping'

/**
 * _coord_display(): "37.2231° N, 38.9224° E", leer ohne Position.
 * Bewusste Abweichung: Python emittiert die HTML-Entität &deg; (der
 * Python-Body wird ungeescaped eingesetzt); React escapet Text, also
 * steht hier das °-Zeichen selbst — identisch gerendert.
 */
export function coordDisplay(lat: number | null, lon: number | null): string {
  if (lat === null || lon === null) return ''
  const latDir = lat >= 0 ? 'N' : 'S'
  const lonDir = lon >= 0 ? 'E' : 'W'
  return `${Math.abs(lat).toFixed(4)}° ${latDir}, ${Math.abs(lon).toFixed(4)}° ${lonDir}`
}

/** _period_display(): kuratierter Periodenname, sonst Start-/Endjahr-Spanne. */
export function periodDisplay(
  site: Pick<SiteRoute, 'period_name' | 'period_start' | 'period_end'>,
): string {
  if (site.period_name) return site.period_name
  if (site.period_start === null) return ''
  if (site.period_end === null) return yearDisplay(site.period_start)
  return `${yearDisplay(site.period_start)} – ${yearDisplay(site.period_end)}`
}
