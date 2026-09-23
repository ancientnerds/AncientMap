/**
 * The machine-readable half of the description disclosure, and which disclosure the popup
 * shows (2026-09 remediation, design entry [6], licensing_and_ai_act).
 *
 * - JSON-LD: text adapted from a Wikipedia revision carries isBasedOn = the permalink and
 *   license = the CC BY-SA 4.0 URL; text an AI system wrote carries the IPTC
 *   trainedAlgorithmicMedia type, as the story, research and journal pages do; a description
 *   without provenance carries neither (the frozen pyref head stays byte-identical).
 * - The popup: a disclosure stands only under the text it describes. The globe's records
 *   come from the static export, which lags the database, so the popup's own API answer is
 *   used only when its description is the one on screen.
 */

import { describe, expect, it } from 'vitest'

import { disclosureFor } from '../../components/SitePopup/descriptionDisclosure'
import type { DescriptionAttribution, SiteRoute } from '../../types/anRoute'
import { siteMeta } from '../meta'
import { FIXTURES } from './fixtures'

const IPTC = 'https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia'
const attribution: DescriptionAttribution = {
  title: 'Göbekli Tepe',
  url: 'https://en.wikipedia.org/w/index.php?title=G%C3%B6bekli_Tepe&oldid=1234567',
  licence: 'CC BY-SA 4.0',
  licenceUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  changes: 'sentences selected and shortened',
  revisionDate: '2026-09-01',
}

function schemaOf(route: SiteRoute): Record<string, unknown> {
  return JSON.parse(siteMeta(route).schema as string) as Record<string, unknown>
}

describe('site JSON-LD: graded by provenance', () => {
  it('selected text: isBasedOn and license, no IPTC type', () => {
    const work = schemaOf({ ...FIXTURES.site, description_ai: 'selected', description_attribution: attribution })
      .subjectOf as Record<string, unknown>
    expect(work).toEqual({ '@type': 'CreativeWork', isBasedOn: attribution.url, license: attribution.licenceUrl })
  })

  it('translated text: isBasedOn, license and the IPTC type', () => {
    const work = schemaOf({ ...FIXTURES.site, description_ai: 'generated', description_attribution: attribution })
      .subjectOf as Record<string, unknown>
    expect(work.digitalSourceType).toBe(IPTC)
    expect(work.isBasedOn).toBe(attribution.url)
  })

  it('restated or legacy text: the IPTC type only', () => {
    const work = schemaOf({ ...FIXTURES.site, description_ai: 'generated', description_attribution: null })
      .subjectOf as Record<string, unknown>
    expect(work).toEqual({ '@type': 'CreativeWork', digitalSourceType: IPTC })
  })

  it('no provenance: no subjectOf at all', () => {
    expect(schemaOf(FIXTURES.site)).not.toHaveProperty('subjectOf')
  })
})

describe('the popup shows a disclosure only under the text it describes', () => {
  const fromApi = { description: 'The new text [1].', ai: 'selected' as const, attribution }

  it("a live record's own disclosure wins", () => {
    const site = { description: 'The new text [1].', descriptionAi: 'generated' as const, descriptionAttribution: null }
    expect(disclosureFor(site, fromApi)).toEqual({ ai: 'generated', attribution: null })
  })

  it("the API's disclosure stands under the API's text", () => {
    expect(disclosureFor({ description: 'The new text [1].' }, fromApi)).toEqual({ ai: 'selected', attribution })
  })

  it('a stale static text gets no disclosure of the new one', () => {
    expect(disclosureFor({ description: 'The March text.' }, fromApi)).toBeNull()
    expect(disclosureFor({ description: 'The March text.' }, null)).toBeNull()
  })
})
