/**
 * Anzeige-Helfer der Payload-Seiten — Portierung von _coord_display()
 * und _period_display() aus pipeline/sites_html_renderer.py (react-ssr
 * plan, Task 11) und beider Hälften von _date_parts() aus seo_pages.py
 * (isoDate: Tasks 12/13, longDate: Task 14). yearDisplay (_year_display)
 * lebt bereits in grouping.ts und wird von dort importiert, nicht
 * dupliziert.
 *
 * Die Payloads tragen rohe DB-Zeilen (snake_case); wie Periode,
 * Koordinaten und Datum dargestellt werden, ist eine
 * Darstellungsentscheidung und lebt deshalb hier — seit Task 16 als
 * einzige Definition (der Python-Renderer und seine Display-Helfer sind
 * gelöscht).
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

/**
 * _date_parts()[0]: "YYYY-MM-DD" aus einem rohen ISO-Timestamp, "" ohne
 * Wert. Python parst per fromisoformat und strftime("%Y-%m-%d") — für
 * jeden ISO-String identisch mit den ersten 10 Zeichen, und genau darauf
 * fällt Python bei unparsbaren Strings ohnehin zurück (value[:10]).
 */
export function isoDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : ''
}

const NAIVE_ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/

/**
 * Ein zonenloser Payload-Timestamp als ISO 8601 mit UTC-Offset, z. B.
 * "2026-10-18T14:03:00+00:00". Die Spalten sind `timestamp without time
 * zone` und halten UTC (Server-Zeitzone Etc/UTC, psql 2026-10-20; Python
 * isoformat() schreibt sie ohne Offset). Google wertete das blosse Datum im
 * VideoObject als "Datetime property uploadDate is missing a timezone"
 * (GSC 16.-19.10.2026, tech-3). Ein String mit Offset oder ohne Uhrzeit ist
 * ein Fehler im Payload-Builder und soll auffallen, wie bei shortDate.
 */
export function utcDateTime(value: string): string {
  if (!NAIVE_ISO_DATETIME.test(value)) {
    throw new Error(`utcDateTime: not a zoneless ISO date-time: ${value}`)
  }
  return `${value}+00:00`
}

/**
 * Kurze Lesefassung der site_type-Taxonomie fuer den Seitentitel. Der
 * Rohwert ("City/town/settlement", "Cave Structures") stand bis 2026-10-20
 * im <title> und verlaengerte ihn: 286 der 4.900 Ortstitel waren laenger als
 * 60 Zeichen (ohne " | Ancient Nerds"), mit diesen Labels sind es 98 und ohne
 * Typ, wo er nicht mehr passt, 14 (psql 2026-10-20). Die Schluessel sind
 * alle 87 Werte der gezeigten ancient_nerds-Orte am 2026-10-20; ein Wert,
 * der hier fehlt, ist schon ein kurzer Name ("Temple", "Dolmen") und steht
 * unveraendert im Titel. Die sichtbare Typzeile der Seite bleibt beim Rohwert.
 */
export const SITE_TYPE_LABELS: Readonly<Record<string, string>> = {
  'City/town/settlement': 'Settlement',
  'City/town/settlement, Pyramid complex': 'Settlement',
  'Fortress/citadel': 'Fortress',
  'Cave Structures': 'Cave site',
  'Necropolis/tombs complex': 'Necropolis',
  'Residence/villa/farmhouse': 'Residence',
  'Megalithic stones': 'Megaliths',
  'Megalithic structures': 'Megalithic site',
  Megalithic: 'Megalithic site',
  'Gate/archway/bridge': 'Gate or bridge',
  'Mound/tumulus': 'Tumulus',
  'Road/avenue/trackway': 'Ancient road',
  Road: 'Ancient road',
  'Rock relief/carving': 'Rock relief',
  'Reservoir/aqueduct/canal': 'Waterworks',
  'Minaret/tower': 'Tower',
  'Castle/palace': 'Castle or palace',
  'Mine/quarry': 'Mine or quarry',
  'Church/cathedral': 'Church',
  'Geological interest': 'Geological site',
  'Natural feature': 'Natural site',
  'Underwater structures': 'Underwater site',
  'Sculptured stone': 'Carved stone',
  Bath: 'Baths',
  Burial: 'Burial site',
  Funerary: 'Funerary site',
  Religious: 'Religious site',
  Military: 'Military site',
  Ruin: 'Ruins',
  Urban: 'City',
  Theater: 'Theatre',
  Harbor: 'Harbour',
}

/** Der Typ im Titel: das Label der Taxonomie, ohne Typ "Archaeological site". */
export function siteTypeLabel(siteType: string | null): string {
  if (!siteType) return 'Archaeological site'
  return SITE_TYPE_LABELS[siteType] ?? siteType
}

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

/**
 * _date_parts()[1]: "March 14, 2026" — Python strftime("%B %d, %Y"), der
 * Tag zweistellig ("March 05"). Unparsbare Strings fallen wie in Python
 * auf value[:10] zurück (der ValueError-Zweig von _date_parts).
 */
export function longDate(value: string | null | undefined): string {
  if (!value) return ''
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})/)
  const month = m ? MONTHS[Number(m[2]) - 1] : undefined
  if (!m || !month) return value.slice(0, 10)
  return `${month} ${m[3]}, ${m[1]}`
}

/**
 * "Sep 7" — dieselbe Lesart wie longDate: die Felder verbatim aus dem
 * ISO-String, nie durch `new Date()`.
 *
 * Die Payload-Timestamps tragen keine Zone ("2026-08-31T00:00:00"), und JS
 * parst die als LOKALZEIT: `new Date(iso).getUTCDate()` verschiebt den Tag
 * dann um den Offset des Renderers — der SSR-Sidecar (UTC) druckte
 * "Aug 30", wo ein Browser in CEST "Aug 31" zeigt, und die Hydration
 * bricht. Anders als longDate fällt hier nichts zurück: die
 * Landing-Payloads garantieren ISO-Timestamps, ein anderer String ist ein
 * Fehler im Payload-Builder und soll auffallen.
 */
export function shortDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  const month = m ? MONTHS[Number(m[2]) - 1] : undefined
  if (!m || !month) throw new Error(`shortDate: not an ISO date: ${iso}`)
  return `${month.slice(0, 3)} ${Number(m[3])}`
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

/**
 * Die Fußzeile einer Paper-Karte: "by {Autor} · {Datum} · {n} sources ·
 * {n} words" — die Zeile, die die Forschungsbibliothek unter jeder Karte
 * druckt (PaperCard.tsx trägt nur den Kasten, der Text ist Anzeige und
 * lebt deshalb hier).
 *
 * `published_at` und `words` sind nullbar; die Zeile entsteht aus den
 * Teilen, die es gibt, damit nie ein Trenner ins Leere zeigt. Fehlt
 * `published_by`, hat Theo selbst publiziert — dieser Default ist eine
 * Anzeigeentscheidung und steht bewusst nicht im Payload.
 */
export function paperCardFooter(paper: {
  author: string | null
  published_at: string | null
  cited_sources: number
  words: number | null
}): string {
  return [
    `by ${paper.author ?? 'Theo'}`,
    paper.published_at && shortDate(paper.published_at),
    paper.cited_sources > 0 && `${paper.cited_sources.toLocaleString('en-US')} cited sources`,
    paper.words != null && `${paper.words.toLocaleString('en-US')} words`,
  ]
    .filter(Boolean)
    .join(' · ')
}
