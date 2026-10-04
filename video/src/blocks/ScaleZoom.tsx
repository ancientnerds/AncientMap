/**
 * ScaleZoom (type C, owner decision 31): the Powers-of-Ten zoom-out without a
 * log axis, for ratios a UnitGrid cannot hold (beyond 1:400). The two
 * quantities are bars on one linear scale, both starting at the same left
 * edge: first the small one fills most of the bar area (readable), then the
 * camera pulls back linearly (the visible extent grows linearly from the small
 * value to the large one, eased at both ends) until the large one fits, and
 * the small one shrinks to a dot that keeps its label. Every frame is one
 * linear scale, so the two bars always stand in the ratio of their values.
 * The pull-back runs from 25 % of the scene to one second before its end,
 * frame by frame; show <small id> and show <large id> let a quantity appear
 * (default: the small at frame 12, the large when the pull-back starts). The
 * basis is always on screen.
 */
import React from 'react'
import { AbsoluteFill, Easing, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { valueText } from './BarChart'
import type { BlockProps, CheckContext } from './types'

export type ZoomQuantity = { id: string; label: string; value: number }
export type ScaleZoomProps = { title: string; unit: string; basis: string; small: ZoomQuantity; large: ZoomQuantity }

/** The fitted quantity spans this share of the bar area's width. */
export const FILL = 0.8
/** A bar shorter than this is drawn as a dot of this diameter. */
export const DOT = 14
/** The fitted final view holds for one second at 60 fps. */
const HOLD_FRAMES = 60
/** Frames the scene needs: the small quantity, the pull-back and the hold (4 s). */
export const MIN_FRAMES = 240
const BASIS_H = 56
const LABEL_H = 48
const BAR_H = 72
const ROW_H = 170

export function checkScaleZoom(p: ScaleZoomProps, ctx: CheckContext): string[] {
  const errors: string[] = []
  if (p.small.id === p.large.id) errors.push(`small and large need different ids (both ${p.small.id})`)
  if (!(p.small.value > 0)) errors.push(`${p.small.id}: the small value must be greater than 0`)
  if (!(p.large.value > p.small.value)) errors.push(`${p.large.id}: the large value ${p.large.value} must be greater than the small value ${p.small.value}`)
  if (ctx.durationInFrames < MIN_FRAMES) {
    errors.push(`a ScaleZoom scene needs at least ${MIN_FRAMES} frames (the small quantity, the pull-back, a 1 s hold), got ${ctx.durationInFrames}`)
  }
  return errors
}

/** The frames of the pull-back: from 25 % of the scene to one second before its end. */
export function pullWindow(durationInFrames: number): { start: number; end: number } {
  return { start: Math.round(durationInFrames * 0.25), end: durationInFrames - HOLD_FRAMES }
}

/**
 * Pixels per unit at scene frame `frame` for a bar area `width` px wide: the
 * visible extent (the value that spans FILL of the width) runs linearly from
 * the small value to the large one over the pull-back, eased at both ends.
 */
export function zoomScale(p: ScaleZoomProps, width: number, frame: number, durationInFrames: number): number {
  const { start, end } = pullWindow(durationInFrames)
  const u = progress(frame, start, end - start, Easing.inOut(Easing.quad))
  const extent = p.small.value + (p.large.value - p.small.value) * u
  return (FILL * width) / extent
}

/** The on-screen basis line (owner rule: comparisons state their basis). */
export function basisLine(p: ScaleZoomProps): string {
  return `To scale, linear. Basis: ${p.basis}`
}

function barArea(stage: Rect): Rect {
  return { x: stage.x + 20, y: stage.y + 100, w: stage.w - 40, h: 2 * ROW_H }
}

export const ScaleZoom: React.FC<BlockProps<ScaleZoomProps>> = ({ props: p, cues, durationInFrames, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const area = barArea(stage)
  const s = zoomScale(p, area.w, frame, durationInFrames)
  const rows = [
    { q: p.small, appear: firstCue(cues, 'show', p.small.id) ?? 12, color: colors.amber },
    { q: p.large, appear: firstCue(cues, 'show', p.large.id) ?? pullWindow(durationInFrames).start, color: colors.green },
  ]
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <div style={{ position: 'absolute', left: area.x, top: area.y, width: area.w, height: area.h, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: 0, top: 0, width: 2, height: area.h, background: colors.greenDim }} />
        {rows.map(({ q, appear, color }, i) => {
          if (frame < appear) return null
          const length = q.value * s
          const top = i * ROW_H + LABEL_H + 12
          return length >= DOT ? (
            <div key={q.id} style={{ position: 'absolute', left: 0, top, width: length, height: BAR_H, background: color, opacity: progress(frame, appear, 12) }} />
          ) : (
            <div key={q.id} style={{ position: 'absolute', left: 0, top: top + (BAR_H - DOT) / 2, width: DOT, height: DOT, borderRadius: DOT / 2, background: color, boxShadow: `0 0 10px ${color}` }} />
          )
        })}
      </div>
      {rows.map(({ q, appear, color }, i) =>
        frame < appear ? null : (
          <LayoutBox
            key={q.id}
            id={`${sceneId}:q:${q.id}`}
            kind="text"
            style={{ position: 'absolute', left: area.x, top: area.y + i * ROW_H, width: area.w, height: LABEL_H, overflow: 'hidden', whiteSpace: 'nowrap', display: 'flex', alignItems: 'baseline', gap: 24, ...bootIn(frame, appear, 12) }}
          >
            <span style={body(32, colors.white)}>{q.label}</span>
            <span style={hud(30, color)}>{valueText(q.value, p.unit)}</span>
          </LayoutBox>
        ),
      )}
      <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
        {basisLine(p)}
      </LayoutBox>
    </AbsoluteFill>
  )
}
