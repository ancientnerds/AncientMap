import { describe, expect, it } from 'vitest'

import { chainChips } from '../Journeys'

describe('journey chips', () => {
  it('splits a chain into entry, page and action chips', () => {
    expect(chainChips('google → story → site_open → site')).toEqual([
      { label: 'google', tone: 'entry' },
      { label: 'story', tone: 'page' },
      { label: 'site_open', tone: 'action' },
      { label: 'site', tone: 'page' },
    ])
  })

  it('keeps a lone entry as the whole chain', () => {
    expect(chainChips('direct')).toEqual([{ label: 'direct', tone: 'entry' }])
  })

  // "search" is both a page type (/search.html) and an event name; the chain is
  // a plain string, so the colour cannot tell them apart. Both read as an action.
  it('paints every step that carries an action name as an action', () => {
    expect(chainChips('direct → search → search').map(c => c.tone)).toEqual([
      'entry',
      'action',
      'action',
    ])
  })
})
