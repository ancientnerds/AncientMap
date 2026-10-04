/**
 * A verdict stamp that slams in at `start` (VERIFIED, WEAKENED, REFUTED ...).
 * The measured LayoutBox is the transformed element itself, so the lint sees
 * the rotated, scaled stamp exactly as drawn.
 */
import React from 'react'
import type { CSSProperties } from 'react'
import { useCurrentFrame, useVideoConfig } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import { stampSlam } from '../motion'
import { heading } from '../theme/type'

export const Stamp: React.FC<{ id: string; text: string; color: string; start: number; size?: number; style?: CSSProperties }> = ({
  id,
  text,
  color,
  start,
  size = 34,
  style,
}) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  if (frame < start) return null
  return (
    <LayoutBox
      id={id}
      kind="text"
      style={{
        position: 'absolute',
        ...heading(size, color),
        padding: '6px 18px',
        border: `4px solid ${color}`,
        borderRadius: 6,
        whiteSpace: 'nowrap',
        background: 'rgba(10, 14, 20, 0.6)',
        ...style,
        ...stampSlam(frame, start, fps),
      }}
    >
      {text}
    </LayoutBox>
  )
}
