/**
 * Owner decision 2026-10-07: the AI notice that used to stand under a card's text is gone.
 *
 * Lane WB (decision O10, 2026-09-26) marked a teaser card AI-generated and the popup showed an
 * AiFootnote for it - exactly once, also where the description was AI-generated itself. That
 * notice applied to every card of the site and is removed from both views: a card carries only
 * its text. The card keeps its machine-readable mark (`data-card-ai` on the SiteCard, `card_ai`
 * in the SSR payload), which no longer reaches this component at all.
 *
 * What stays is the CC BY-SA 4.0 attribution of an adapted description, including its
 * "by an AI system" clause: that is a licence duty of the text, not an AI notice.
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

function html(props: Partial<DescriptionSectionProps>): string {
  return renderToStaticMarkup(<DescriptionSection {...BASE} {...props} />)
}

describe('DescriptionSection: a card carries only its text', () => {
  it('no notice for a plain description', () => {
    expect(html({})).not.toContain('data-ai-generated')
  })

  it('no notice for an AI-generated description', () => {
    expect(html({ descriptionAi: 'generated' })).not.toContain('data-ai-generated')
  })

  it('no notice for a description selected from a Wikipedia revision', () => {
    expect(html({ descriptionAi: 'selected' })).not.toContain('data-ai-generated')
  })

  it('the CC BY-SA attribution stays, with its AI clause', () => {
    const markup = html({
      descriptionAi: 'selected',
      descriptionAttribution: {
        title: 'Skara Brae',
        url: 'https://en.wikipedia.org/w/index.php?title=Skara_Brae&oldid=1234567',
        licence: 'CC BY-SA 4.0',
        licenceUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
        changes: 'sentences selected and shortened',
        revisionDate: '2026-09-01',
      },
    })
    expect(markup).toContain('data-description-attribution="true"')
    expect(markup).toContain('CC BY-SA 4.0')
    expect(markup).toContain('by an AI system')
    expect(markup).not.toContain('data-ai-generated')
  })
})