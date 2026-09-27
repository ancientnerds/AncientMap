/**
 * NERV panel frame for the card blocks: dark glass, an outline traced in
 * (border-trace), corner brackets and one light sweep across after the panel
 * has opened (crt-open).
 */
import React from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useCurrentFrame } from 'remotion'

import type { Rect } from '../layout/geometry'
import { borderTrace, crtOpen, sweep } from '../motion'
import { colors } from '../theme/colors'

const BRACKET = 22

export const Panel: React.FC<{ rect: Rect; start?: number; accent?: string; children?: ReactNode }> = ({ rect, start = 0, accent = colors.green, children }) => {
  const frame = useCurrentFrame()
  const perimeter = 2 * (rect.w + rect.h)
  const line = `3px solid ${accent}`
  const corner = (pos: CSSProperties) => <div style={{ position: 'absolute', width: BRACKET, height: BRACKET, ...pos }} />
  const pass = sweep(frame, start + 24, 40)
  return (
    <div style={{ position: 'absolute', left: rect.x, top: rect.y, width: rect.w, height: rect.h, transformOrigin: 'center', ...crtOpen(frame, start) }}>
      <div style={{ position: 'absolute', inset: 0, background: colors.bgPanel }} />
      <svg width={rect.w} height={rect.h} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
        <rect
          x={0.5}
          y={0.5}
          width={rect.w - 1}
          height={rect.h - 1}
          fill="none"
          stroke={accent}
          strokeOpacity={0.55}
          strokeWidth={1}
          strokeDasharray={perimeter}
          strokeDashoffset={borderTrace(frame, start + 4, 24, perimeter)}
        />
      </svg>
      {pass > 0 && pass < 1 ? (
        <div style={{ position: 'absolute', top: 0, bottom: 0, left: pass * rect.w, width: 3, background: accent, opacity: 0.35 * Math.sin(pass * Math.PI) }} />
      ) : null}
      {corner({ left: -2, top: -2, borderLeft: line, borderTop: line })}
      {corner({ right: -2, top: -2, borderRight: line, borderTop: line })}
      {corner({ left: -2, bottom: -2, borderLeft: line, borderBottom: line })}
      {corner({ right: -2, bottom: -2, borderRight: line, borderBottom: line })}
      <div style={{ position: 'absolute', inset: 0 }}>{children}</div>
    </div>
  )
}
