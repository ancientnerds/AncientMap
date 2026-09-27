/**
 * Place label over footage, bottom left (zone lowerThird). It sits on its own
 * dark glass so it reads over any capture, including the site's busy UI.
 */
import React from 'react'
import { useCurrentFrame } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import { ZONES } from '../layout/zones'
import { bootIn, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, heading } from '../theme/type'
import type { Label } from './types'

export const LowerThird: React.FC<{ id: string; label: Label; start?: number }> = ({ id, label, start = 12 }) => {
  const frame = useCurrentFrame()
  const z = ZONES.lowerThird
  const bar = progress(frame, start, 14)
  return (
    <div style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, ...bootIn(frame, start) }}>
      <div style={{ position: 'absolute', inset: 0, background: colors.bgPanel }} />
      <div style={{ position: 'absolute', left: 0, top: 0, width: 6, height: z.h * bar, background: colors.green }} />
      <LayoutBox id={id} kind="text" style={{ position: 'absolute', left: 26, top: 8, width: z.w - 44, height: z.h - 16, overflow: 'hidden' }}>
        <div style={{ ...heading(38), whiteSpace: 'nowrap' }}>{label.title}</div>
        {label.subtitle ? <div style={{ ...body(24, colors.crt300), whiteSpace: 'nowrap' }}>{label.subtitle}</div> : null}
      </LayoutBox>
    </div>
  )
}
