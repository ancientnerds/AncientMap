/**
 * Owner decision D86 (2026-11-05): no M3 tier or score out of 100 on a paper;
 * "Claim-checked" only where the studio's claim check ran.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import QualityBadge from '../QualityBadge'

describe('QualityBadge', () => {
  it('shows Claim-checked for a studio-checked paper, without a score', () => {
    const html = renderToString(<QualityBadge qualityScore={{ badge: 'Claim-checked' }} />)
    expect(html).toContain('Claim-checked')
    expect(html).not.toContain('/100')
  })

  it.each(['Platinum', 'Gold', 'Unverified'])('shows nothing for the M3 tier %s', badge => {
    expect(renderToString(<QualityBadge qualityScore={{ badge }} />)).toBe('')
  })

  it('shows nothing without a quality record', () => {
    expect(renderToString(<QualityBadge qualityScore={undefined} />)).toBe('')
  })
})
