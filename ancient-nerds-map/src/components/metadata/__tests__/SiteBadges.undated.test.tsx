/**
 * The residue label reaches the site as a plain `period_name` with no year: the owner's rung of
 * 2026-10-04 (`pipeline/utils/text.py:UNDATED`) gives a curated site that no source, no Wikidata
 * claim and no `site_type` dates a **visible** entry that says so, and takes no antiquity colour
 * - because there is no year to place on the timeline.
 *
 * This is the frontend half of that rule, pinned because it is reached without any code in
 * `sites.ts` or `colors.ts` learning the label: `resolvePeriod` prefers the stored label, and
 * `SiteBadges` falls through to "raw string" and takes the grey that `getPeriodColor` gives an
 * unknown period. Both are one line each, and a refactor of either would silently drop the badge -
 * a site with no period would look like a site with no period again, which is the state this whole
 * lane exists to end.
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PERIOD_COLORS } from '../../../constants/colors'
import { resolvePeriod } from '../../../data/sites'
import { SiteBadges } from '../SiteBadges'

/** The owner's word, spelled out here rather than imported: the frontend has no Python import. */
const UNDATED = 'Undated'

function html(period: string | null, periodStart: number | null, category: string | null = 'Temple'): string {
  return renderToStaticMarkup(
    <SiteBadges category={category} period={period} periodStart={periodStart} />
  )
}

describe('SiteBadges: the residue label', () => {
  it('shows the label of a site nothing dates, so the entry is visible', () => {
    const markup = html(UNDATED, null)
    expect(markup).toContain(UNDATED)
    expect(markup).toContain('meta-badge')
  })

  it('takes no antiquity colour: it wears the grey an unknown period wears', () => {
    // The rule's `why`: no year means no place on the timeline, so the badge must not be tinted
    // like a bucket. `getPeriodColor` falls back to `Unknown`, and this asserts that grey by value
    // instead of restating the hex.
    expect(html(UNDATED, null)).toContain(PERIOD_COLORS.Unknown)
    for (const [label, color] of Object.entries(PERIOD_COLORS)) {
      if (label === 'Unknown') continue
      expect(html(UNDATED, null)).not.toContain(color)
    }
  })

  it('still shows no badge for a site with no period at all', () => {
    // The fallback that renders `Undated` must not swallow the empty case: that is the state the
    // lane removes, and it has to stay distinguishable while any of it is left. A generic category
    // takes the category badge out of the way, so what is left is the period's doing alone.
    expect(html(null, null, null)).toBe('')
  })

  it('lets the stored label win over a derived one, with no year to derive from', () => {
    expect(resolvePeriod(UNDATED, null)).toBe(UNDATED)
    expect(resolvePeriod(UNDATED, 850)).toBe(UNDATED)
  })
})
