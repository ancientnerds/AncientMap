/**
 * Diagram (type C, science and space): NERV wireframe primitives in a width x
 * height user space, scaled uniformly into the stage: circle, line, arrow,
 * curve (polyline through points), orbit (a body on an ellipse, one revolution
 * per `period` seconds) and label. Elements trace in on their show <id> cues,
 * staggered otherwise. Schematic: the basis line says what it simplifies. A
 * scene too short for the staggered elements is refused (checkDiagram): the
 * last element would never be drawn.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { firstCue } from '../cues'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps, CheckContext } from './types'

export type DiagramElement = {
  id: string
  type: 'circle' | 'line' | 'arrow' | 'curve' | 'orbit' | 'label'
  tone: Tone
  label?: string
  cx?: number
  cy?: number
  r?: number
  rx?: number
  ry?: number
  period?: number
  x1?: number
  y1?: number
  x2?: number
  y2?: number
  dashed?: boolean
  points?: [number, number][]
  x?: number
  y?: number
  text?: string
}
export type DiagramProps = { title: string; width: number; height: number; basis?: string; elements: DiagramElement[] }

const BASIS_H = 56
/** Frame the first element appears without a show cue, and the stagger of the next ones. */
const FIRST_ELEMENT = 10
const ELEMENT_STAGGER = 8
/** A shape traces in over TRACE_FRAMES; its label starts LABEL_DELAY frames after it appears and takes LABEL_FADE. */
const TRACE_FRAMES = 20
const LABEL_DELAY = 8
const LABEL_FADE = 10

const REQUIRED: Record<DiagramElement['type'], (keyof DiagramElement)[]> = {
  circle: ['cx', 'cy', 'r'],
  line: ['x1', 'y1', 'x2', 'y2'],
  arrow: ['x1', 'y1', 'x2', 'y2'],
  curve: ['points'],
  orbit: ['cx', 'cy', 'rx', 'ry', 'period'],
  label: ['x', 'y', 'text'],
}

export function checkDiagram(p: DiagramProps, ctx: CheckContext): string[] {
  const errors: string[] = []
  for (const e of p.elements) {
    for (const key of REQUIRED[e.type]) if (e[key] === undefined) errors.push(`element ${e.id} (${e.type}) needs "${key}"`)
  }
  const settled = settledAt(p.elements, () => null)
  if (ctx.durationInFrames <= settled) {
    errors.push(`a Diagram scene needs at least ${settled + 1} frames (its elements trace in one after the other until frame ${settled}), got ${ctx.durationInFrames}`)
  }
  return errors
}

/** First frame of each element: its show cue, else staggered from FIRST_ELEMENT. */
function elementStarts(elements: readonly DiagramElement[], cueFrame: (id: string) => number | null): number[] {
  return elements.map((e, i) => cueFrame(e.id) ?? FIRST_ELEMENT + i * ELEMENT_STAGGER)
}

/**
 * The first frame on which every shape has traced in and every label is in (a
 * label element has no trace, only its text), for elements appearing as
 * elementStarts places them. An orbit's body keeps moving; its ellipse settles.
 * checkDiagram passes no cues: it sees the default schedule only.
 */
export function settledAt(elements: readonly DiagramElement[], cueFrame: (id: string) => number | null): number {
  const starts = elementStarts(elements, cueFrame)
  const label = LABEL_DELAY + LABEL_FADE
  return elements.reduce((done, e, i) => Math.max(done, starts[i] + (e.type === 'label' ? label : Math.max(TRACE_FRAMES, label))), 0)
}

/** Uniform scale and offset placing the user space in the drawing area, centred. */
export function fitDiagram(width: number, height: number, area: Rect): { s: number; ox: number; oy: number } {
  const s = Math.min(area.w / width, area.h / height)
  return { s, ox: area.x + (area.w - width * s) / 2, oy: area.y + (area.h - height * s) / 2 }
}

export const Diagram: React.FC<BlockProps<DiagramProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const area = { x: stage.x, y: stage.y + 80, w: stage.w, h: stage.h - 80 - BASIS_H - 20 }
  const { s, ox, oy } = fitDiagram(p.width, p.height, area)
  const X = (v: number) => ox + v * s
  const Y = (v: number) => oy + v * s
  const labels: React.ReactNode[] = []
  const starts = elementStarts(p.elements, (id) => firstCue(cues, 'show', id))
  const shapes = p.elements.map((e, i) => {
    const appear = starts[i]
    if (frame < appear) return null
    const k = progress(frame, appear, TRACE_FRAMES)
    const color = toneColor[e.tone]
    const common = { stroke: color, strokeWidth: 3, fill: 'none', strokeDasharray: e.dashed ? '10 8' : undefined }
    let anchor: { x: number; y: number } | null = null
    let shape: React.ReactNode = null
    switch (e.type) {
      case 'circle':
        shape = <circle cx={X(e.cx as number)} cy={Y(e.cy as number)} r={(e.r as number) * s * k} {...common} />
        anchor = { x: X(e.cx as number) + (e.r as number) * s + 12, y: Y(e.cy as number) - 14 }
        break
      case 'line':
      case 'arrow': {
        const x1 = X(e.x1 as number)
        const y1 = Y(e.y1 as number)
        const x2 = x1 + (X(e.x2 as number) - x1) * k
        const y2 = y1 + (Y(e.y2 as number) - y1) * k
        const ang = Math.atan2(y2 - y1, x2 - x1)
        shape = (
          <g>
            <line x1={x1} y1={y1} x2={x2} y2={y2} {...common} />
            {e.type === 'arrow' && k > 0.9 ? (
              <path d={`M${x2} ${y2} L${x2 - 18 * Math.cos(ang - 0.4)} ${y2 - 18 * Math.sin(ang - 0.4)} M${x2} ${y2} L${x2 - 18 * Math.cos(ang + 0.4)} ${y2 - 18 * Math.sin(ang + 0.4)}`} {...common} />
            ) : null}
          </g>
        )
        anchor = { x: (x1 + X(e.x2 as number)) / 2 + 12, y: (y1 + Y(e.y2 as number)) / 2 - 34 }
        break
      }
      case 'curve': {
        const pts = (e.points as [number, number][]).map(([x, y]) => `${X(x)},${Y(y)}`)
        shape = <polyline points={pts.slice(0, Math.max(2, Math.ceil(pts.length * k))).join(' ')} {...common} />
        const [lx, ly] = (e.points as [number, number][])[(e.points as [number, number][]).length - 1]
        anchor = { x: X(lx) + 12, y: Y(ly) - 16 }
        break
      }
      case 'orbit': {
        const cx = X(e.cx as number)
        const cy = Y(e.cy as number)
        const rx = (e.rx as number) * s
        const ry = (e.ry as number) * s
        const phase = (2 * Math.PI * (frame - appear)) / ((e.period as number) * fps)
        shape = (
          <g>
            <ellipse cx={cx} cy={cy} rx={rx} ry={ry} {...common} strokeOpacity={0.5 * k} />
            <circle cx={cx + rx * Math.cos(phase)} cy={cy + ry * Math.sin(phase)} r={10} fill={color} />
          </g>
        )
        anchor = { x: cx + rx + 12, y: cy - 16 }
        break
      }
      case 'label':
        anchor = { x: X(e.x as number), y: Y(e.y as number) }
        break
    }
    const text = e.type === 'label' ? e.text : e.label
    if (text && anchor) {
      labels.push(
        <LayoutBox key={e.id} id={`${sceneId}:el:${e.id}`} kind="text" style={{ position: 'absolute', left: anchor.x, top: anchor.y, whiteSpace: 'nowrap', ...hud(26, color), ...bootIn(frame, appear + LABEL_DELAY, LABEL_FADE) }}>
          {text}
        </LayoutBox>,
      )
    }
    return <React.Fragment key={e.id}>{shape}</React.Fragment>
  })
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {shapes}
      </svg>
      {labels}
      {p.basis ? (
        <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
          {`Schematic. Basis: ${p.basis}`}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
