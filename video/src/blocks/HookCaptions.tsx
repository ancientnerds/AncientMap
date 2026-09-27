/**
 * Burned-in captions, for the hook only (owner rule: afterwards viewers use
 * YouTube's captions from the exact SRT). timeline.captions is empty after the
 * hook; the spoken word is green, the rest of the line white. A line is one row
 * of at most HOOK_LINE_MAX_CHARS characters (captions.ts), which fits the zone for
 * ordinary words; lint.ts reports a wider run of capitals as an overflow.
 */
import React, { useMemo } from 'react'
import { useCurrentFrame } from 'remotion'

import { captionLines, lineAt } from '../captions'
import { LayoutBox } from '../layout/LayoutBox'
import { ZONES } from '../layout/zones'
import { colors } from '../theme/colors'
import { heading, overFootage } from '../theme/type'
import type { Caption } from '../timeline'

export const HookCaptions: React.FC<{ captions: readonly Caption[] }> = ({ captions }) => {
  const frame = useCurrentFrame()
  const lines = useMemo(() => captionLines(captions), [captions])
  const line = lineAt(lines, frame)
  if (!line) return null
  const z = ZONES.caption
  return (
    <LayoutBox
      id="captions"
      kind="text"
      style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <div style={{ ...heading(64), textAlign: 'center', whiteSpace: 'nowrap', ...overFootage }}>
        {line.words.map((w, i) => (
          <span key={`${w.from}-${i}`} style={{ color: frame >= w.from && frame < w.to ? colors.green : colors.white }}>
            {i > 0 ? ' ' : ''}
            {w.text}
          </span>
        ))}
      </div>
    </LayoutBox>
  )
}
