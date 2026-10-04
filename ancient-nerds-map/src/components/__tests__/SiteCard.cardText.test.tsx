/**
 * A site card carries the teaser text, never the wiki description (owner, 2026-10-04: "der
 * kartentext soll nur in den karten stehen! kein wiki text. nur in der search seite in den
 * sites karten").
 *
 * `SiteCard` preferred the teaser but fell back to the site's `description` - the sentence-extracted
 * Wikipedia text - whenever a site had no teaser card. Measured 2026-10-04, read-only: 318 of 5,004
 * curated sites have no card (2,663 of them do carry a lane-WB teaser provenance, which is a
 * different thing: a card that was verified, not a card that exists), so on the search page the same
 * grid mixed two text kinds and the fallback read as the same kind of thing as the teaser.
 *
 * The teaser itself is unchanged - `cardDescription` still wins, and it still gets the `FitText`
 * shrink - and a compact card still shows no text at all, which is what hover tooltips and inline
 * references want.
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { SiteCard } from '../SiteCard'
import type { SiteData } from '../../data/sites'

const TEASER = 'Inhabited since the late Neolithic age, Aartswoud holds a settlement that is an important source for the Beaker culture.'
const WIKI = 'The area of Aartswoud has been inhabited since the late Neolithic age, and a settlement there is an important source for the Beaker culture [1].'

function site(overrides: Partial<SiteData> = {}): SiteData {
  return {
    id: 'a1b2c3d4',
    title: 'Aartswoud',
    location: 'Netherlands',
    category: 'City/town/settlement',
    period: '3000 - 1500 BC',
    periodStart: -2500,
    description: WIKI,
    sourceId: 'ancient_nerds',
    coordinates: [4.95, 52.74],
    ...overrides,
  }
}

function html(props: Partial<SiteData> = {}, compact?: boolean): string {
  return renderToStaticMarkup(<SiteCard site={site(props)} compact={compact} />)
}

describe('SiteCard: which text the card carries', () => {
  it('shows the teaser, and not the wiki text beside it', () => {
    const markup = html({ cardDescription: TEASER })
    expect(markup).toContain(TEASER)
    expect(markup).not.toContain(WIKI)
  })

  it('shows no text at all where a site has no teaser card', () => {
    const markup = html()
    expect(markup).not.toContain(WIKI)
    expect(markup).not.toContain('site-card-desc')
  })

  it('a compact card still carries no text, teaser or not', () => {
    expect(html({ cardDescription: TEASER }, true)).not.toContain(TEASER)
    expect(html({}, true)).not.toContain(WIKI)
  })
})
