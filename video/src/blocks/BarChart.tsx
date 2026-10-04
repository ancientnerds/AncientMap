/**
 * BarChart: horizontal bars on a linear axis for frequencies and sizes (type B:
 * how many sites per region, per period). Linear only (owner decision 31: a
 * log axis is not pictorial; ratios beyond a UnitGrid's 1:400 are a ScaleZoom).
 * A value is a number, or [low, high] when sources differ: the bar is solid to
 * low and outlined on to high, labelled "low–high unit" (spec 4.2: a quantity
 * with a range shows the range). Bars grow in on their show <id> cues,
 * staggered otherwise; a single value rolls with its bar; the basis is always
 * on screen. A scene too short for the staggered bars is refused (checkBarChart):
 * the last bar would never appear, or its value would stop short of the true one.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { formatNumber } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { COMPOSED, lineProblem } from './composed'
import type { BlockProps, CheckContext } from './types'

export type BarValue = number | [number, number]
export type Bar = { id: string; label: string; value: BarValue; tone?: Tone }
export type BarChartProps = { title: string; unit: string; basis: string; bars: Bar[] }
/** The linear value axis 0..hi. */
export type BarAxis = { lo: 0; hi: number }

const LABEL_W = 580
const VALUE_W = 360
const BASIS_H = 56
const GROW_FRAMES = 30
/** Frame the first bar starts without a show cue, and the stagger of the next ones. */
const FIRST_BAR = 12
const BAR_STAGGER = 12
/** Frames a bar's label, and a range's value once its bar has grown, take to boot in. */
const TEXT_FADE = 12

const lowOf = (v: BarValue): number => (Array.isArray(v) ? v[0] : v)
const highOf = (v: BarValue): number => (Array.isArray(v) ? v[1] : v)
/**
 * The exact decimals of `x`'s shortest form, exponent form included, with no cap (1.75 -> 2,
 * 1.5e-7 -> 8, 1e21 -> 0), so a value bound to a case-file quantity prints exactly that value;
 * one too long for its box fails the layout lint as `overflow`, never prints as another number.
 */
const decimalsOf = (x: number): number => {
  const [mantissa, exp = '0'] = String(x).split('e')
  return Math.max(0, (mantissa.split('.')[1] ?? '').length - Number(exp))
}

export function checkBarChart(p: BarChartProps, ctx: CheckContext): string[] {
  const errors: string[] = []
  for (const b of p.bars) {
    if (Array.isArray(b.value) && !(b.value[0] < b.value[1])) errors.push(`bar ${b.id}: range [${b.value[0]}, ${b.value[1]}] needs low < high`)
    // the value box holds characters of the digits and the unit together, not of the unit alone
    const range = Array.isArray(b.value)
    errors.push(...lineProblem(`bar ${b.id}:`, valueText(b.value, p.unit), COMPOSED['BarChart.valueText'][range ? 'range' : 'single'], 'the value box', range ? 'for a range' : 'for a single value'))
  }
  if (!p.bars.some((b) => highOf(b.value) > 0)) errors.push('every bar is 0: nothing to compare')
  const settled = settledAt(p.bars, () => null)
  if (ctx.durationInFrames <= settled) {
    errors.push(`a BarChart scene needs at least ${settled + 1} frames (its bars grow in one after the other until frame ${settled}), got ${ctx.durationInFrames}`)
  }
  return errors
}

/** First frame of each bar: its show cue, else staggered from FIRST_BAR. */
function barStarts(bars: readonly Bar[], cueFrame: (id: string) => number | null): number[] {
  return bars.map((b, i) => cueFrame(b.id) ?? FIRST_BAR + i * BAR_STAGGER)
}

/**
 * The first frame on which every bar has grown, every single value has rolled to
 * its value and every range's label (it boots in once its bar has grown) is in,
 * for bars starting as barStarts places them. checkBarChart passes no cues: it
 * sees the default schedule only.
 */
export function settledAt(bars: readonly Bar[], cueFrame: (id: string) => number | null): number {
  const starts = barStarts(bars, cueFrame)
  return bars.reduce((done, b, i) => Math.max(done, starts[i] + GROW_FRAMES + (Array.isArray(b.value) ? TEXT_FADE : 0)), 0)
}

/** The axis of the chart: 0 up to the largest (high) value. */
export function barAxis(p: BarChartProps): BarAxis {
  return { lo: 0, hi: Math.max(...p.bars.map((b) => highOf(b.value))) }
}

/** Where `value` lies along the bar area, 0..1 (linear). */
export function barFraction(axis: BarAxis, value: number): number {
  return value / axis.hi
}

/** "1,250 t", "1.75 m", or "1,000–1,650 t" for a range; every value keeps its own decimals. */
export function valueText(v: BarValue, unit: string): string {
  const n = (x: number) => formatNumber(x, decimalsOf(x))
  return `${Array.isArray(v) ? `${n(v[0])}–${n(v[1])}` : n(v)} ${unit}`
}

/** The on-screen basis line (owner rule: comparisons state their basis). */
export function basisLine(p: BarChartProps): string {
  return `Basis: ${p.basis}`
}

export const BarChart: React.FC<BlockProps<BarChartProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const axis = barAxis(p)
  const areaTop = stage.y + 100
  const areaH = stage.h - 100 - BASIS_H - 30
  const rowH = Math.min(130, Math.floor(areaH / p.bars.length))
  const top = areaTop + Math.floor((areaH - rowH * p.bars.length) / 2)
  const barX = stage.x + LABEL_W
  const barMax = stage.w - LABEL_W - VALUE_W - 40
  const starts = barStarts(p.bars, (id) => firstCue(cues, 'show', id))
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      {p.bars.map((b, i) => {
        const appear = starts[i]
        if (frame < appear) return null
        const grow = progress(frame, appear, GROW_FRAMES)
        const y = top + i * rowH
        const color = toneColor[b.tone ?? 'accent']
        const range = Array.isArray(b.value)
        const solid = barMax * barFraction(axis, lowOf(b.value)) * grow
        const end = barMax * barFraction(axis, highOf(b.value)) * grow
        // A single value rolls with its bar; a range appears once the bar has grown.
        const rolls = !range
        return (
          <React.Fragment key={b.id}>
            <LayoutBox id={`${sceneId}:bar:${b.id}`} kind="text" style={{ position: 'absolute', left: stage.x, top: y, width: LABEL_W - 20, height: rowH - 16, overflow: 'hidden', textAlign: 'right', ...body(28, colors.text), lineHeight: `${rowH - 16}px`, whiteSpace: 'nowrap', ...bootIn(frame, appear, TEXT_FADE) }}>
              {b.label}
            </LayoutBox>
            <div style={{ position: 'absolute', left: barX, top: y + 6, width: solid, height: rowH - 28, background: color }} />
            {range ? <div style={{ position: 'absolute', left: barX + solid, top: y + 6, width: end - solid, height: rowH - 28, boxSizing: 'border-box', border: `3px solid ${color}`, borderLeft: 'none' }} /> : null}
            <LayoutBox
              id={`${sceneId}:value:${b.id}`}
              kind="text"
              style={{ position: 'absolute', left: barX + end + 16, top: y, width: VALUE_W, height: rowH - 16, overflow: 'hidden', whiteSpace: 'nowrap', ...hud(range ? 30 : 34, colors.white), lineHeight: `${rowH - 16}px`, ...(rolls ? {} : bootIn(frame, appear + GROW_FRAMES, TEXT_FADE)) }}
            >
              {rolls ? `${formatNumber(lowOf(b.value) * grow, decimalsOf(lowOf(b.value)))} ${p.unit}` : valueText(b.value, p.unit)}
            </LayoutBox>
          </React.Fragment>
        )
      })}
      <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
        {basisLine(p)}
      </LayoutBox>
    </AbsoluteFill>
  )
}
