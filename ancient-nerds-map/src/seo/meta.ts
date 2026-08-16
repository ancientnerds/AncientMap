/**
 * Head-Tags für jede indexierte Seite — die TypeScript-Portierung von
 * _meta_head() und den neun Seitenfunktionen aus pipeline/seo_pages.py.
 *
 * Reine Funktionen ohne React: der SSR-Dienst ruft renderHead() direkt
 * auf, Vitest vergleicht die Ausgabe byte-genau gegen die Python-Referenz
 * (src/seo/__tests__/pyref/, erzeugt von scripts/gen_meta_reference.py).
 * Solange pipeline/seo_pages.py lebt, ist es die maßgebliche Quelle —
 * Änderungen dort müssen hier nachgezogen und die Referenz neu erzeugt
 * werden.
 *
 * Einzige bewusste Abweichung von Python: der <style>{SSR_CSS}</style>-
 * Block wird NICHT eingebettet — nach dem Cutover kommt das CSS aus dem
 * gebauten Vite-Bundle, nicht aus dem Head-Fragment. (renderHead maskiert
 * < zusätzlich am Sink; byte-identisch, weil jsonStr schon maskiert.)
 */

import type {
  ArticleIndexRoute,
  ArticleRoute,
  CountryRoute,
  ResearchIndexRoute,
  ResearchRoute,
  SiteRoute,
  SitesIndexRoute,
  StoryArchiveRoute,
  StoryRoute,
} from '../types/anRoute'
import { isoDate } from './display'
import { periodSpan, typeSections } from './grouping'
import { blurb, collapse, cut } from './text'

const BASE_URL = 'https://ancientnerds.com'
const DEFAULT_OG_IMAGE = `${BASE_URL}/landing/og-image.png`

export interface PageMeta {
  /**
   * Roher Title OHNE " | Ancient Nerds". Das Suffix hängt renderHead()
   * an — und zwar nur im <title>: og:title und twitter:title tragen es in
   * _meta_head() nicht, und die Byte-Parität dorthin ist der Vertrag.
   */
  title: string
  description: string
  canonical: string
  ogType?: string
  image?: string
  schema?: string
}

/** Python html.escape(): &, <, >, " und — anders als viele JS-Helfer — auch '. */
const esc = (s: string) =>
  s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')

/** _json_str(): JSON-String, dessen < ein </script>-Ausbruch unmöglich macht. */
const jsonStr = (s: string) => JSON.stringify(s).replace(/</g, '\\u003c')

/** Python f"{n:,}": Tausendertrennung mit Komma. */
const thousands = (n: number) => n.toLocaleString('en-US')

// ---------------------------------------------------------------------------
// URL-Helfer — Portierungen aus article_html_renderer.py / sites_html_renderer.py.
// Die Meta-Funktionen bauen Canonicals selbst, weil die Payloads (bewusst)
// nur Rohdaten tragen: slug, id, name — nie fertige absolute URLs.
// ---------------------------------------------------------------------------

/**
 * slugify(): \p{L}\p{N}_ entspricht Pythons Unicode-\w — ö/ü/é bleiben
 * erhalten, wie in den Server-Slugs. Exportiert, weil ArticlesPage daraus
 * Canonical- und /medium-URLs baut; bis 2026-08-16 hatte sie eine eigene
 * ASCII-\w-Kopie, die Umlaute strippte und damit vom Server abwich.
 */
export function slugify(title: string): string {
  let slug = title.toLowerCase().trim()
  slug = slug.replace(/[^\p{L}\p{N}_\s-]/gu, '')
  slug = slug.replace(/[\s_]+/g, '-')
  slug = slug.replace(/-+/g, '-')
  slug = slug.replace(/^-|-$/g, '')
  return cut(slug, 120)
}

function storySlug(headline: string, id: number): string {
  return `${slugify(headline)}-${id}`
}

/** country_path(): Länderpfad. Exportiert für SitePage (Crumb + Geschwister-Block). */
export function countryPath(country: string): string {
  return `/sites/${slugify(country)}`
}

/**
 * site_path(): Detailpfad einer kuratierten Site. Exportiert für StoryPage,
 * die den Chip zur Site-Seite seit dem Story-Cutover (Task 14) selbst baut —
 * gegated auf site_curated, sonst wäre der Link ein 404.
 */
export function sitePath(country: string, name: string, siteId: string): string {
  const stem = slugify(name)
  const suffix = siteId.replace(/-/g, '').slice(0, 8)
  return `${countryPath(country)}/${stem ? `${stem}-${suffix}` : suffix}`
}

/**
 * story_page(): relative Screenshot-Pfade werden absolut — og:image und das
 * NewsArticle-Schema verlangen absolute URLs; StoryPage nutzt dieselbe Form.
 */
export function absoluteUrl(path: string | null): string {
  if (!path) return ''
  return path.startsWith('/') ? `${BASE_URL}${path}` : path
}

/**
 * urllib.parse.quote(path): encodeURIComponent je Segment, plus die
 * Zeichen !'()* die encodeURIComponent — anders als quote() — durchlässt.
 * Slugs enthalten sie nie; der Ersatz hält die Parität trotzdem exakt.
 */
function encodePath(path: string): string {
  return path
    .split('/')
    .map(seg =>
      encodeURIComponent(seg).replace(
        /[!'()*]/g,
        c => '%' + c.charCodeAt(0).toString(16).toUpperCase(),
      ),
    )
    .join('/')
}

// ---------------------------------------------------------------------------
// _meta_head()
// ---------------------------------------------------------------------------

/**
 * Der gemeinsame Head-Block. Eine leere Description lässt die
 * description/og:description/twitter:description-Tags KOMPLETT weg (seit
 * b4690a3): ein leeres content="" zeigt Google wörtlich an, statt selbst
 * ein Snippet aus der Seite zu schreiben.
 */
export function renderHead(m: PageMeta): string {
  const t = esc(m.title)
  const d = esc(cut(collapse(m.description), 300))
  const img = esc(m.image ?? DEFAULT_OG_IMAGE)
  const canonical = esc(m.canonical)
  const schemaTag = m.schema
    ? `\n<script type="application/ld+json">${m.schema.replace(/</g, '\\u003c')}</script>`
    : ''
  const descTag = d ? `\n<meta name="description" content="${d}">` : ''
  const ogDescTag = d ? `\n<meta property="og:description" content="${d}">` : ''
  const twDescTag = d ? `\n<meta name="twitter:description" content="${d}">` : ''
  return `<title>${t} | Ancient Nerds</title>${descTag}
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="${canonical}">
<meta property="og:type" content="${m.ogType ?? 'website'}">
<meta property="og:url" content="${canonical}">
<meta property="og:site_name" content="Ancient Nerds">
<meta property="og:title" content="${t}">${ogDescTag}
<meta property="og:image" content="${img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${t}">${twDescTag}
<meta name="twitter:image" content="${img}">
<meta name="twitter:site" content="@AncientNerdsDAO">${schemaTag}`
}

// ---------------------------------------------------------------------------
// Die neun Seitentypen
// ---------------------------------------------------------------------------

/** story_page(): Description aus post_text (nicht summary), unter 150 Zeichen gar keine. */
export function storyMeta(route: StoryRoute): PageMeta {
  const canonical = `${BASE_URL}/news-archive/${encodePath(storySlug(route.headline, route.id))}`
  const summary = route.summary.trim()
  const screenshot = absoluteUrl(route.screenshot_url)
  const schema =
    '{"@context": "https://schema.org", "@type": "NewsArticle", ' +
    `"headline": ${jsonStr(route.headline)}, ` +
    `"description": ${jsonStr(cut(summary, 300))}, ` +
    `"datePublished": "${isoDate(route.published_at)}", ` +
    `"image": "${esc(screenshot || DEFAULT_OG_IMAGE)}", ` +
    '"author": {"@type": "Organization", "name": "Ancient Nerds", ' +
    `"url": "${BASE_URL}"}, ` +
    '"publisher": {"@type": "Organization", "name": "Ancient Nerds", ' +
    `"url": "${BASE_URL}"}, ` +
    `"mainEntityOfPage": "${canonical}", "url": "${canonical}"}`
  const postText = collapse(route.post_text)
  return {
    title: route.headline,
    description: Array.from(postText).length >= 150 ? blurb(postText, 300) : '',
    canonical,
    ogType: 'article',
    image: screenshot || undefined,
    schema,
  }
}

export function storyArchiveMeta(route: StoryArchiveRoute): PageMeta {
  const suffix = route.page > 1 ? ` — page ${route.page}` : ''
  const canonical =
    route.page === 1 ? `${BASE_URL}/news-archive/` : `${BASE_URL}/news-archive/page/${route.page}`
  return {
    title: `Story Archive${suffix}`,
    description:
      `${thousands(route.total)} archaeology stories from the Ancient Nerds video digest — ` +
      'excavations, dating results, and reinterpretations, each with its source.',
    canonical,
  }
}

/** site_detail_page(): das Payload trägt die rohe Zeile — Defaults entstehen hier. */
export function siteMeta(route: SiteRoute): PageMeta {
  const canonical = `${BASE_URL}${encodePath(sitePath(route.country, route.name, route.id))}`
  const siteType = route.site_type || 'Archaeological site'
  const description = (route.description || '').trim()
  const ogImage = route.image ? `${BASE_URL}${route.image.url}` : undefined

  const place = [
    '"@type": "Place"',
    `"name": ${jsonStr(route.name)}`,
    `"url": "${canonical}"`,
    `"address": {"@type": "PostalAddress", "addressCountry": ${jsonStr(route.country)}}`,
  ]
  if (description) place.push(`"description": ${jsonStr(cut(description, 500))}`)
  if (route.lat !== null && route.lon !== null) {
    place.push(
      `"geo": {"@type": "GeoCoordinates", "latitude": ${route.lat}, ` +
        `"longitude": ${route.lon}}`,
    )
  }
  if (ogImage) place.push(`"image": "${ogImage}"`)

  const crumbs: [string, string][] = [
    ['Home', `${BASE_URL}/`],
    ['Sites', `${BASE_URL}/sites/`],
    [route.country, `${BASE_URL}${encodePath(countryPath(route.country))}`],
    [route.name, canonical],
  ]
  const crumbItems = crumbs
    .map(
      ([label, url], i) =>
        `{"@type": "ListItem", "position": ${i + 1}, "name": ${jsonStr(label)}, "item": "${url}"}`,
    )
    .join(', ')
  const schema =
    `[{"@context": "https://schema.org", ${place.join(', ')}}, ` +
    '{"@context": "https://schema.org", "@type": "BreadcrumbList", ' +
    `"itemListElement": [${crumbItems}]}]`

  return {
    title: `${route.name} — ${route.country} · ${siteType}`,
    description: description || `${route.name}: ${siteType.toLowerCase()} in ${route.country}.`,
    canonical,
    ogType: 'place',
    image: ogImage,
    schema,
  }
}

export function sitesIndexMeta(route: SitesIndexRoute): PageMeta {
  const total = route.countries.reduce((sum, c) => sum + c.count, 0)
  return {
    title: 'Archaeological Sites by Country',
    description:
      `${thousands(total)} curated archaeological sites across ${route.countries.length} countries: ` +
      'settlements, temples, tombs, megaliths and rock art, each with location and sources.',
    canonical: `${BASE_URL}/sites/`,
  }
}

export function countryMeta(route: CountryRoute): PageMeta {
  const canonical = `${BASE_URL}${encodePath(countryPath(route.country))}`
  // Das Payload trägt die rohen Zeilen; Sektionen und Zeitspanne entstehen
  // hier — mit derselben Gruppierung, die CountrySitesPage rendert, damit
  // das ItemList-Schema die tatsächlich servierte Reihenfolge beschreibt.
  const sections = typeSections(route.sites)
  const ordered = sections.flatMap(s => s.sites)
  const total = route.sites.length
  const span = periodSpan(route.sites)
  const items = ordered
    .slice(0, 50)
    .map(
      (s, i) =>
        `{"@type": "ListItem", "position": ${i + 1}, "name": ${jsonStr(s.name)}, ` +
        `"url": "${BASE_URL}${encodePath(s.path)}"}`,
    )
    .join(', ')
  const schema =
    '{"@context": "https://schema.org", "@type": "ItemList", ' +
    `"name": ${jsonStr(`Archaeological Sites in ${route.country}`)}, ` +
    `"numberOfItems": ${total}, "itemListElement": [${items}]}`

  const namedTypes = sections
    .slice(0, 3)
    .map(s => s.label.toLowerCase())
    .join(', ')
  const hero = ordered.find(s => s.thumbnail_url)?.thumbnail_url
  return {
    title: `Archaeological Sites in ${route.country} (${total})`,
    description:
      `${total} curated archaeological sites in ${route.country}` +
      (namedTypes ? ` — ${namedTypes} and more` : '') +
      (span ? `. Spanning ${span}` : '') +
      '. Each with location, historical context and sources.',
    canonical,
    image: hero ? `${BASE_URL}${hero}` : undefined,
    schema,
  }
}

/** research_page(): das Payload trägt die rohen Zeilenfelder — Defaults entstehen hier. */
export function researchMeta(route: ResearchRoute): PageMeta {
  const canonical = `${BASE_URL}/research/${encodePath(route.slug)}`
  const summary = (route.summary || '').trim()
  const author = route.author || 'Theo'
  // Theo ist eine Pipeline, keine Person — im JSON-LD eine Organization.
  const authorSchema =
    author === 'Theo'
      ? '{"@type": "Organization", "name": "Ancient Nerds", "description": "AI research pipeline"}'
      : `{"@type": "Person", "name": ${jsonStr(author)}}`
  const schema =
    '{"@context": "https://schema.org", "@type": "ScholarlyArticle", ' +
    `"headline": ${jsonStr(route.title)}, "description": ${jsonStr(cut(summary, 300))}, ` +
    `"datePublished": "${isoDate(route.published_at)}", "author": ${authorSchema}, ` +
    '"license": "https://creativecommons.org/licenses/by/4.0/", ' +
    `"mainEntityOfPage": "${canonical}", "url": "${canonical}"}`
  return {
    title: route.title,
    description: summary || route.title,
    canonical,
    ogType: 'article',
    image: route.hero_image_url || undefined,
    schema,
  }
}

export function researchIndexMeta(route: ResearchIndexRoute): PageMeta {
  return {
    title: 'Research Library',
    description:
      `${route.papers.length} open-access archaeological research papers with full citations, ` +
      'published under CC BY 4.0.',
    canonical: `${BASE_URL}/research/`,
  }
}

/** article_page(): das Payload trägt die rohen Zeilenfelder — Defaults entstehen hier. */
export function articleMeta(route: ArticleRoute): PageMeta {
  const canonical = `${BASE_URL}/articles/${encodePath(route.slug)}`
  const summary = (route.summary || '').trim()
  const schema =
    '{"@context": "https://schema.org", "@type": "Article", ' +
    `"headline": ${jsonStr(route.title)}, "description": ${jsonStr(cut(summary, 300))}, ` +
    `"datePublished": "${isoDate(route.published_at)}", ` +
    '"author": {"@type": "Organization", "name": "Ancient Nerds"}, ' +
    `"mainEntityOfPage": "${canonical}", "url": "${canonical}"}`
  return {
    title: route.title,
    description: summary || route.title,
    canonical,
    ogType: 'article',
    image: route.hero_image_url || undefined,
    schema,
  }
}

export function articleIndexMeta(route: ArticleIndexRoute): PageMeta {
  return {
    title: 'Weekly Archaeology Journal',
    description:
      `${route.articles.length} weekly journals covering the biggest archaeological ` +
      'discoveries, each sourced and cited.',
    canonical: `${BASE_URL}/articles/`,
  }
}
