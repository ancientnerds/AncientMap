/**
 * DescriptionDisclosure — what a site description says about where its words came from.
 *
 * The 2026-09 remediation writes each description with provenance, and the server derives
 * the disclosure from it (api/services/description_provenance.py). Graded by provenance
 * (EU AI Act Art. 50; CC BY-SA 4.0 section 3(a)):
 *
 * - attribution present (lanes W, S, T: text adapted from a Wikipedia revision): the line
 *   "Text: Wikipedia – '<title>' (revision of <date>), CC BY-SA 4.0 · <change> by an AI
 *   system · source →", in the existing popup-wiki-source-link element — no new styling;
 * - ai === 'generated' (lanes T, R and the legacy lane L): the existing AiFootnote,
 *   unchanged;
 * - nothing without provenance: a text nobody recorded is claimed for by nobody;
 * - cardAi === 'generated' (a teaser card of lane WB, owner decision O10 of 2026-09-26): the
 *   site's card is AI-generated. The card is shown on the SiteCard, which carries only the
 *   machine-readable data-card-ai; the visible notice is here, on the page the card opens -
 *   the same AiFootnote, once, whichever of the two texts is AI-generated.
 *
 * One component for the popup (DescriptionSection) and the crawler record (SitePage), so the
 * two views cannot say it differently. Every anchor carries one string child, so the
 * server-rendered HTML has no <!-- --> separators inside the line.
 */

import type { DescriptionAi, DescriptionAttribution } from '../types/anRoute'
import AiFootnote from './news/AiFootnote'

interface DescriptionDisclosureProps {
  ai?: DescriptionAi | null
  attribution?: DescriptionAttribution | null
  /** The AI mark of the site's card (not shown here): 'generated' for a lane-WB teaser. */
  cardAi?: DescriptionAi | null
}

export default function DescriptionDisclosure({ ai, attribution, cardAi }: DescriptionDisclosureProps) {
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
      {(ai === 'generated' || cardAi === 'generated') && <AiFootnote />}
    </>
  )
}
