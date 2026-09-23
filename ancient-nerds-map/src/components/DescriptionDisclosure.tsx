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
 * - nothing without provenance: a text nobody recorded is claimed for by nobody.
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
      {ai === 'generated' && <AiFootnote />}
    </>
  )
}
