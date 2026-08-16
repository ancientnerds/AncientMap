/**
 * Gruppierung der Länderseiten — Portierung von type_sections() und
 * _period_span() (+ _year_display) aus pipeline/seo_pages.py bzw.
 * sites_html_renderer.py (react-ssr plan, Task 10).
 *
 * Seit dem Cutover übergibt /sites/{country} das ROHE sites-Array (die
 * SQL-Zeilen, snake_case); die Gruppierung ist eine Darstellungsentscheidung
 * und lebt deshalb hier — countryMeta und CountrySitesPage teilen sich EINE
 * Definition. Seit Task 16 die einzige: der Python-Renderer und seine
 * Tests (test_seo_country_extras.py) sind gelöscht; die 1:1-Übersetzung
 * in __tests__/grouping.test.ts trägt die Abdeckung allein.
 */

import type { CountrySite } from '../types/anRoute'

/**
 * Type-Sektionen pro Länderseite; der Long Tail landet in "Other sites".
 * England allein trägt 30+ Typen, die meisten mit ein oder zwei Sites —
 * eine Sektion je Typ würde die Liste unter ihrem eigenen Inhaltsverzeichnis
 * begraben.
 */
export const MAX_TYPE_SECTIONS = 12
export const OTHER_TYPES_LABEL = 'Other sites'

export interface TypeSection {
  label: string
  sites: CountrySite[]
}

/** Python-Tupelvergleich für Strings: Codepoint-Ordnung, kein Locale. */
const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)

/** type_sections(): nach Typ gruppieren, größte zuerst, Rest in einer Sektion. */
export function typeSections(sites: CountrySite[]): TypeSection[] {
  const byType = new Map<string, CountrySite[]>()
  for (const site of sites) {
    const label = site.site_type || OTHER_TYPES_LABEL
    const group = byType.get(label)
    if (group) group.push(site)
    else byType.set(label, [site])
  }

  const ranked = [...byType.entries()].sort(
    ([labelA, groupA], [labelB, groupB]) => groupB.length - groupA.length || cmp(labelA, labelB),
  )
  const kept = new Set(
    ranked
      .slice(0, MAX_TYPE_SECTIONS)
      .map(([label]) => label)
      .filter(label => label !== OTHER_TYPES_LABEL),
  )
  const sections: TypeSection[] = ranked
    .filter(([label]) => kept.has(label))
    .map(([label, group]) => ({ label, sites: group }))
  const tail = ranked.filter(([label]) => !kept.has(label)).flatMap(([, group]) => group)
  if (tail.length) {
    sections.push({
      label: OTHER_TYPES_LABEL,
      sites: [...tail].sort((a, b) => cmp(a.name, b.name)),
    })
  }
  return sections
}

/**
 * _year_display(): signiertes Jahr → Ära-Label (-500 → "500 BC").
 * Exportiert für src/seo/display.ts (periodDisplay) — EINE Definition.
 */
export function yearDisplay(year: number): string {
  return `${Math.abs(year)} ${year < 0 ? 'BC' : 'AD'}`
}

/**
 * _period_span(): frühestes bis spätestes Startjahr, z. B. "9000 BC – 1964 AD".
 * Aus period_start statt der period_name-Buckets: die Bucket-Labels sind
 * selbst Spannen, zwei davon verkettet ("< 4500 BC – 500 BC - 1 AD") sind Rauschen.
 */
export function periodSpan(sites: CountrySite[]): string {
  const years = sites
    .map(s => s.period_start)
    .filter((y): y is number => y !== null && y !== undefined)
  if (!years.length) return ''
  const first = yearDisplay(Math.min(...years))
  const last = yearDisplay(Math.max(...years))
  return first === last ? first : `${first} – ${last}`
}
