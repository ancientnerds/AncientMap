/**
 * raw_data._description_provenance never renders in the "more info" panel.
 *
 * The 2026-09 remediation writes the description's provenance into raw_data under a key with
 * a leading underscore. The generic raw_data panel (curated sites have no field config) must
 * not show it: two rules keep it out - keys starting with '_' are skipped, and nested objects
 * are never formatted. Each rule is pinned on its own, so removing either one fails a test.
 */

import { describe, expect, it } from 'vitest'

import { getDisplayableFields, hasDisplayableRawData } from '../sourceFields'

const provenance = {
  v: 1,
  lane: 'W',
  ai: 'selected',
  sources: [{ id: 'W', url: 'https://en.wikipedia.org/w/index.php?title=X&oldid=1' }],
}

describe('the description provenance key', () => {
  it('never renders for a curated site', () => {
    const fields = getDisplayableFields('ancient_nerds', {
      _description_provenance: provenance,
      excavated_by: 'Themistocles Zammit',
    })
    expect(fields.map(f => f.config.key)).toEqual(['excavated_by'])
    expect(hasDisplayableRawData('ancient_nerds', { _description_provenance: provenance })).toBe(false)
  })

  it('an underscore key is skipped even when its value would render', () => {
    expect(getDisplayableFields('ancient_nerds', { _internal: 'plain text' })).toEqual([])
  })

  it('a nested object is skipped even without the underscore', () => {
    expect(getDisplayableFields('ancient_nerds', { provenance })).toEqual([])
  })
})
