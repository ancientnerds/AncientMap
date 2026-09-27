/**
 * Timeline (type D transmission, site phases): a horizontal year axis across
 * the stage. Events enter on their show <id> cues (staggered otherwise) with
 * labels alternating above and below the axis so neighbours keep apart (the
 * lint pass checks it). Negative years are BCE; year 0 does not exist.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { formatYear, yearTicks } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps } from './types'

export type TimelineEvent = { id: string; year: number; label: string; tone: Tone }
export type TimelineProps = { title: string; from: number; to: number; events: TimelineEvent[]; basis?: string }

const BASIS_H = 56
/** Events in the outer 15 % of the axis carry edge-aligned labels, so the label stays on screen. */
const EDGE = 0.15

/** Horizontal placement of an event label at axis fraction f: centred, or aligned to the near edge. */
export function labelAnchor(f: number): { textAlign: 'left' | 'center' | 'right'; transform: string; dx: number } {
  if (f < EDGE) return { textAlign: 'left', transform: '', dx: -16 }
  if (f > 1 - EDGE) return { textAlign: 'right', transform: 'translateX(-100%)', dx: 16 }
  return { textAlign: 'center', transform: 'translateX(-50%)', dx: 0 }
}

export function checkTimeline(p: TimelineProps): string[] {
  const errors = p.to <= p.from ? [`timeline range ${p.from}..${p.to} is empty`] : []
  for (const e of p.events) {
    if (e.year < p.from || e.year > p.to) errors.push(`event ${e.id} (${e.year}) lies outside ${p.from}..${p.to}`)
    if (e.year === 0) errors.push(`event ${e.id}: year 0 does not exist`)
  }
  return errors
}

export const Timeline: React.FC<BlockProps<TimelineProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const axis = { x: stage.x + 60, y: stage.y + Math.round((stage.h - BASIS_H) / 2) + 40, w: stage.w - 120 }
  const xOf = (year: number) => axis.x + ((year - p.from) / (p.to - p.from)) * axis.w
  const events = [...p.events].sort((a, b) => a.year - b.year)
  const drawn = progress(frame, 4, 30)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <div style={{ position: 'absolute', left: axis.x, top: axis.y, width: axis.w * drawn, height: 4, background: colors.green }} />
      {yearTicks(p.from, p.to).map((y) => (
        <div key={y} style={{ position: 'absolute', left: xOf(y), top: axis.y + 14, transform: 'translateX(-50%)', ...hud(18, colors.crt400), whiteSpace: 'nowrap', opacity: drawn }}>
          {formatYear(y)}
        </div>
      ))}
      {events.map((e, i) => {
        const appear = firstCue(cues, 'show', e.id) ?? 30 + i * 14
        if (frame < appear) return null
        const x = xOf(e.year)
        const anchor = labelAnchor((e.year - p.from) / (p.to - p.from))
        const above = i % 2 === 0
        const color = toneColor[e.tone]
        return (
          <React.Fragment key={e.id}>
            <div style={{ position: 'absolute', left: x - 11, top: axis.y - 9, width: 22, height: 22, borderRadius: 11, background: color, ...bootIn(frame, appear, 8) }} />
            <div style={{ position: 'absolute', left: x - 1, top: above ? axis.y - 80 : axis.y + 50, width: 2, height: 36, background: color, opacity: 0.7 }} />
            <LayoutBox
              id={`${sceneId}:event:${e.id}`}
              kind="text"
              style={{ position: 'absolute', left: x + anchor.dx, top: above ? axis.y - 170 : axis.y + 94, textAlign: anchor.textAlign, whiteSpace: 'nowrap', ...bootIn(frame, appear + 4, 12, anchor.transform) }}
            >
              <div style={hud(26, color)}>{formatYear(e.year)}</div>
              <div style={body(30, colors.white)}>{e.label}</div>
            </LayoutBox>
          </React.Fragment>
        )
      })}
      {p.basis ? (
        <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
          {`Dates: ${p.basis}`}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
