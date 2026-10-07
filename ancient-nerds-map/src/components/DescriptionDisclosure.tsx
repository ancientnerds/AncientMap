/**
 * DescriptionDisclosure — the source line under a site description.
 *
 * The 2026-09 remediation writes each description with provenance, and the server derives
 * the disclosure from it (api/services/description_provenance.py). For lanes W, S and T the
 * text was adapted from a pinned Wikipedia revision, and CC BY-SA 4.0 section 3(a) requires
 * the attribution: the line
 * "Text: Wikipedia – '<title>' (revision of <date>), CC BY-SA 4.0 · <change> by an AI
 * system · source →", in the existing popup-wiki-source-link element — no new styling.
 * A description without provenance is claimed for by nobody and renders nothing.
 *
 * Owner decision of 2026-10-07: the AI notice that stood here is gone. AiFootnote ("AI-
 * generated text · images from the original sources · always verify with the sources") used
 * to appear on the site's page and in its popup whenever the description or the teaser card
 * was AI-generated, for every card of the site. A card now carries only its text: nothing in
 * the card's two views says the text is AI-generated, and neither does the SiteCard, whose
 * data-description-ai / data-card-ai attributes stay as machine-readable provenance.
 *
 * The CC BY-SA line above stays, including its "by an AI system" clause: it is a licence duty
 * of the adapted text, not an AI notice, and removing it would break the attribution. So do
 * the notices of the areas a card is not part of — Theo papers, news videos, YouTube shorts.
 *
 * One component for the popup (DescriptionSection) and the crawler record (SitePage), so the
 * two views cannot say it differently. Every anchor carries one string child, so the
 * server-rendered HTML has no <!-- --> separators inside the line.
 */

import type { DescriptionAi, DescriptionAttribution } from '../types/anRoute'

interface DescriptionDisclosureProps {
  ai?: DescriptionAi | null
  attribution?: DescriptionAttribution | null
}

export default function DescriptionDisclosure({ ai, attribution }: DescriptionDisclosureProps) {
  // Without provenance the server sends neither field, so both branches below stay empty.
  const revision = attribution?.revisionDate ? ` (revision of ${attribution.revisionDate})` : ''
  return (
    <>
      {attribution && (
        <span data-description-attribution="true" data-description-ai={ai}>
          <a
            href={attribution.url}
            target="_blank"
            rel="noopener noreferrer"
            className="popup-wiki-source-link"
          >
            {`Text: Wikipedia – '${attribution.title}'${revision},`}
          </a>{' '}
          <a
            href={attribution.licenceUrl}
            target="_blank"
            rel="license noopener noreferrer"
            className="popup-wiki-source-link"
          >
            {attribution.licence}
          </a>{' '}
          <a
            href={attribution.url}
            target="_blank"
            rel="noopener noreferrer"
            className="popup-wiki-source-link"
          >
            {`· ${attribution.changes} by an AI system · source →`}
          </a>
        </span>
      )}
    </>
  )
}
