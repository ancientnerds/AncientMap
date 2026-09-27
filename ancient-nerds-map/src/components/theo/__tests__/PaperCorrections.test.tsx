/**
 * The corrections log under a paper: a correction of a current evidence
 * paragraph links to it, one that retired an evidence id carries the id
 * itself (so old video links land on it), and dates render in the fixed
 * longDate format that hydrates identically in the UTC sidecar and a browser.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ResearchCorrection } from '../../../types/anRoute'
import PaperCorrections from '../PaperCorrections'

const CORRECTIONS: ResearchCorrection[] = [
  { date: '2026-10-02', text: 'Quarry date re-sourced.', evidence_id: 'ev-02', holds_anchor: false },
  { date: '2026-10-04', text: 'Fourth monolith removed.', evidence_id: 'ev-05', holds_anchor: true },
  { date: '2026-10-05', text: 'Typo in a date.', evidence_id: null, holds_anchor: false },
]

describe('PaperCorrections', () => {
  const html = renderToString(<PaperCorrections corrections={CORRECTIONS} />)

  it('is a section with an h2, the target of the meta line link', () => {
    expect(html).toContain('<section id="corrections" class="theo-paper-corrections"')
    expect(html).toContain('<h2 id="corrections-title">Corrections</h2>')
  })

  it('a correction of a current paragraph links to it', () => {
    expect(html).toContain(
      '<li><time dateTime="2026-10-02">October 02, 2026</time> Quarry date re-sourced.' +
        '<a class="theo-paper-correction-link" href="#ev-02">See the corrected passage</a></li>',
    )
  })

  it('a correction that retired an id carries the id itself', () => {
    expect(html).toContain(
      '<li id="ev-05"><time dateTime="2026-10-04">October 04, 2026</time> Fourth monolith removed.</li>',
    )
  })

  it('a correction without an evidence id has neither', () => {
    expect(html).toContain(
      '<li><time dateTime="2026-10-05">October 05, 2026</time> Typo in a date.</li>',
    )
  })
})
