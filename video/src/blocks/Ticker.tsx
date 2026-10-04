/**
 * Evidence counter (top right): how many sourced evidence items the episode
 * has shown so far. Hidden until the first item; the number rolls on change.
 * No series branding (owner rule).
 */
import React from 'react'
import { useCurrentFrame } from 'remotion'

import { tickerAt } from '../captions'
import { LayoutBox } from '../layout/LayoutBox'
import { ZONES } from '../layout/zones'
import { bootIn, digitRoll } from '../motion'
import { colors } from '../theme/colors'
import { hud, overFootage } from '../theme/type'
import type { TickerStep } from '../timeline'

export const Ticker: React.FC<{ steps: readonly TickerStep[] }> = ({ steps }) => {
  const frame = useCurrentFrame()
  const { n, previous, since } = tickerAt(steps, frame)
  if (n === 0) return null
  const shown = digitRoll(previous, n, frame, since, 18)
  const first = steps.find((s) => s.n > 0)?.frame ?? 0
  const z = ZONES.ticker
  return (
    <LayoutBox
      id="ticker"
      kind="text"
      style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 14, ...overFootage, ...bootIn(frame, first) }}
    >
      <span style={hud(20, colors.crt300)}>Evidence</span>
      <span style={{ ...hud(44, colors.green), letterSpacing: '0.04em' }}>{String(shown).padStart(2, '0')}</span>
    </LayoutBox>
  )
}
