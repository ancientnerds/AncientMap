/**
 * Breadcrumbs — die Krümelnavigation JEDER indexierten Seite, plus das
 * BreadcrumbList-Schema aus derselben Liste.
 *
 * Vorher stand die Kette in sieben Seiten handgeschrieben: eigene Slashes,
 * eigene <a>-Tags, und nirgends ein Schema. Google baut aus BreadcrumbList
 * die Pfadzeile im Suchergebnis — ohne sie steht dort die nackte URL.
 *
 * Markup und Schema kommen aus DERSELBEN Liste, damit sie nicht
 * auseinanderlaufen können: was der Leser sieht, ist was der Crawler liest.
 * Das JSON-LD steht bewusst im Body und nicht im <head>: die Head-Ausgabe
 * ist byte-genau gegen die eingefrorenen pyref-Referenzen getestet
 * (seo/meta.ts), und ein zweites Schema dort hätte zehn Referenzdateien
 * angefasst, ohne dass Google es anders bewertet.
 */

const BASE_URL = 'https://ancientnerds.com'

export interface Crumb {
  name: string
  /** Ohne Pfad = die aktuelle Seite: kein Link, aber Teil der Kette. */
  path?: string
}

export default function Breadcrumbs({ trail }: { trail: Crumb[] }) {
  const schema = JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((crumb, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: crumb.name,
      ...(crumb.path ? { item: `${BASE_URL}${crumb.path}` } : {}),
    })),
  }).replace(/</g, '\\u003c')

  return (
    <>
      <nav className="story-crumb">
        {trail.map((crumb, i) => (
          <span key={`${crumb.name}-${i}`}>
            {i > 0 && ' / '}
            {crumb.path ? <a href={crumb.path}>{crumb.name}</a> : crumb.name}
          </span>
        ))}
      </nav>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: schema }} />
    </>
  )
}
