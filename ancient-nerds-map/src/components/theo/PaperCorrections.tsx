/**
 * PaperCorrections — the public corrections log under a paper
 * (result_json.corrections, appended by `theo_publish --correct`).
 *
 * An entry that concerns an evidence paragraph links to it (#ev-NN). An
 * entry that retired an evidence id carries that id itself (holds_anchor,
 * decided in pipeline/research_html_renderer.parse_corrections): video
 * descriptions link #ev-NN for good, and the link then lands here, on the
 * explanation, instead of nowhere.
 *
 * Dates go through longDate, never new Date(): the SSR sidecar runs in UTC
 * and a browser in local time (display.ts, the hydration note at shortDate).
 * Each text is one string child, so the indexed HTML has no <!-- --> splits.
 */

import { longDate } from '../../seo/display'
import type { ResearchCorrection } from '../../types/anRoute'

import '../../styles/paper-extras.css'

export default function PaperCorrections({ corrections }: { corrections: ResearchCorrection[] }) {
  return (
    <section id="corrections" className="theo-paper-corrections" aria-labelledby="corrections-title">
      <h2 id="corrections-title">Corrections</h2>
      <ol>
        {corrections.map((c, i) => {
          const anchorId = c.holds_anchor ? c.evidence_id : null
          const linkId = c.holds_anchor ? null : c.evidence_id
          return (
            <li key={`${c.date}-${i}`} id={anchorId ?? undefined}>
              <time dateTime={c.date}>{longDate(c.date)}</time>
              {` ${c.text}`}
              {linkId && (
                <a className="theo-paper-correction-link" href={`#${linkId}`}>
                  See the corrected passage
                </a>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
