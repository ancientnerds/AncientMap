/**
 * Beschreibungstext mit auflösbaren Fußnoten — eine Implementierung für die
 * interaktive Ansicht UND die indexierte Seite.
 *
 * Die Marker `[1]`, `[2]` stammen aus der Anreicherung; die zugehörigen
 * Belege liegen als raw_data.description_citations im selben Payload. In
 * SitePopup wurden sie seit jeher zu Links aufgelöst — die crawlerbare
 * SiteRecord-Ansicht auf /sites/{country}/{slug} zeigte dagegen die nackte
 * Zahl ohne jede Referenz. Bei 2.141 der 5.004 kuratierten Sites las Google
 * also "…in the Giza Governorate of Egypt [1]." und fand nichts, worauf die
 * 1 zeigt (geprüft 12.09.2026).
 *
 * Die Render-Logik lag vorher privat in DescriptionSection.tsx. Sie steht
 * jetzt hier, damit beide Ansichten dieselbe Ausgabe erzeugen — inklusive
 * der Klasse `popup-citation-sup`, die in styles/index.css definiert ist und
 * von siteMain.tsx auch für die SEO-Seite geladen wird.
 */

import type { ReactNode } from 'react'

import type { DescriptionCitation } from '../types/anRoute'

/** `n` → Beleg. Fehlt ein Marker in der Liste, bleibt er unverlinkt. */
export function buildCitationMap(
  citations?: DescriptionCitation[] | null,
): Map<number, DescriptionCitation> {
  const map = new Map<number, DescriptionCitation>()
  for (const c of citations ?? []) map.set(c.n, c)
  return map
}

/** Trägt der Text überhaupt Marker? Steuert in SitePopup den Umschalter. */
export function hasCitationMarkers(text: string | null | undefined): boolean {
  return /\[\d+\]/.test(text || '')
}

export function citationNodes(
  text: string,
  citationMap: Map<number, DescriptionCitation>,
): ReactNode[] {
  const parts: ReactNode[] = []
  const regex = /\[(\d+)\]/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index))
    const num = parseInt(match[1], 10)
    const cite = citationMap.get(num)
    // EIN String-Kind, nicht `[{num}]`: drei Kinder trennt renderToString mit
    // <!-- --> und schreibt damit `[<!-- -->1<!-- -->]` in jede der 2.141
    // indexierten Seiten.
    const label = `[${num}]`
    parts.push(
      cite ? (
        <a
          key={`cite-${match.index}`}
          href={cite.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="popup-citation-sup"
          title={cite.title}
        >
          {label}
        </a>
      ) : (
        // Ohne Beleg bleibt die Zahl stehen, aber als Hochstellung statt als
        // Link ins Leere — der Text behält seine Nummerierung.
        <sup key={`cite-${match.index}`} className="popup-citation-sup">
          {label}
        </sup>
      ),
    )
    lastIndex = regex.lastIndex
  }

  if (lastIndex < text.length) parts.push(text.slice(lastIndex))
  return parts
}

/**
 * Ein Textabschnitt mit aufgelösten Fußnoten.
 *
 * `rel="nofollow"` auf den Belegen: es sind fremde Quellen, die die
 * Anreicherung ausgewählt hat, keine redaktionelle Empfehlung.
 */
export default function CitationText({
  text,
  citations,
}: {
  text: string
  citations?: DescriptionCitation[] | null
}) {
  return <>{citationNodes(text, buildCitationMap(citations))}</>
}
