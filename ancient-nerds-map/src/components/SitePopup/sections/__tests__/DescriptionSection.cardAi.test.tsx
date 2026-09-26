/**
 * Lane WB (owner decision O10, 2026-09-26): SitePopup passes the card's AI mark that
 * /api/sites/{id} reports (cardAi) to DescriptionSection, which hands it on to
 * DescriptionDisclosure. A teaser card adds the AI footnote - exactly once, also where the
 * description is AI-generated itself - and a card without teaser provenance adds none.
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { DescriptionSection } from '../DescriptionSection'
import type { DescriptionSectionProps } from '../../types'

const BASE: DescriptionSectionProps = {
  description: 'Skara Brae is a stone-built Neolithic settlement on the Bay of Skaill, Orkney.',
  sourceId: 'ancient_nerds',
  rawData: null,
  rawDataLoading: false,
  onAdminClick: () => {},
}

function footnotes(props: Partial<DescriptionSectionProps>): number {
  const html = renderToStaticMarkup(<DescriptionSection {...BASE} {...props} />)
  return html.split('data-ai-generated="true"').length - 1
}

describe('DescriptionSection: the AI mark of the site card', () => {
  it('a teaser card adds exactly one AI footnote', () => {
    expect(footnotes({ cardAi: 'generated' })).toBe(1)
  })

  it('an AI-generated description with a teaser card still shows one footnote', () => {
    expect(footnotes({ cardAi: 'generated', descriptionAi: 'generated' })).toBe(1)
  })

  it('a card without teaser provenance adds no footnote', () => {
    expect(footnotes({})).toBe(0)
    expect(footnotes({ cardAi: undefined, descriptionAi: 'selected' })).toBe(0)
  })
})
