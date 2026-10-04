/**
 * ScaleDrawing: a to-scale side view of 2-5 objects on one ground line, all at
 * the same metres per pixel, with their dimensions labelled and the basis always
 * on screen ("block 20.5 m long, DAI 2014; person 1.75 m"): comparisons state
 * their basis, and lengths are never drawn on oblique photos (owner rules).
 * Objects grow in on their show <id> cues, staggered otherwise.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { formatNumber } from '../format'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps } from './types'

export type ScaleShape = 'block' | 'person' | 'column' | 'bus' | 'pyramid' | 'rect'
export type ScaleObject = { id: string; label: string; shape: ScaleShape; width: number; height: number; x: number }
export type ScaleDrawingProps = { title: string; unit: 'cm' | 'm' | 'km'; basis: string; objects: ScaleObject[] }

const LABEL_ROOM = 90
const BASIS_H = 56
const PALETTE = [colors.green, colors.amber, colors.cyan, colors.crt300, colors.orange]

/** Pixels per unit so the widest extent and the tallest object both fit the drawing area. */
export function fitScale(objects: readonly ScaleObject[], w: number, h: number): number {
  const extent = Math.max(...objects.map((o) => o.x + o.width))
  const tallest = Math.max(...objects.map((o) => o.height))
  return Math.min(w / extent, h / tallest)
}

export function drawArea(stage: Rect): Rect {
  const top = stage.y + 60 + LABEL_ROOM
  return { x: stage.x + 60, y: top, w: stage.w - 120, h: stage.y + stage.h - BASIS_H - 20 - top }
}

/** The ground line: the drawing (tallest object on it) centred vertically in the area. */
export function groundLine(objects: readonly ScaleObject[], s: number, area: Rect): number {
  const tallest = Math.max(...objects.map((o) => o.height)) * s
  return area.y + Math.round((area.h + tallest) / 2)
}

/** The dimension label: the height of upright shapes, width x height of the others. */
export function dimensionLabel(o: ScaleObject, unit: string): string {
  const upright = o.shape === 'person' || o.shape === 'column' || o.shape === 'pyramid'
  return upright ? `${formatNumber(o.height, 2)} ${unit}` : `${formatNumber(o.width, 2)} × ${formatNumber(o.height, 2)} ${unit}`
}

export function checkScaleDrawing(p: ScaleDrawingProps): string[] {
  return p.objects.filter((o) => o.width <= 0 || o.height <= 0).map((o) => `object ${o.id} needs a positive width and height`)
}

/** The on-screen basis line (owner rule: comparisons state their basis). */
export function basisLine(p: ScaleDrawingProps): string {
  return `To scale. Basis: ${p.basis}`
}

function shapePath(o: ScaleObject, x: number, ground: number, w: number, h: number): React.ReactNode {
  const top = ground - h
  switch (o.shape) {
    case 'person': {
      const head = Math.min(w, h * 0.13)
      return (
        <g>
          <circle cx={x + w / 2} cy={top + head / 2} r={head / 2} />
          <path d={`M${x + w / 2} ${top + head} V${ground - h * 0.45} M${x} ${top + h * 0.32} H${x + w} M${x + w / 2} ${ground - h * 0.45} L${x + w * 0.1} ${ground} M${x + w / 2} ${ground - h * 0.45} L${x + w * 0.9} ${ground}`} />
        </g>
      )
    }
    case 'column':
      return <path d={`M${x} ${ground} V${top + h * 0.06} H${x + w} V${ground} M${x - w * 0.15} ${top} H${x + w * 1.15} V${top + h * 0.06} H${x - w * 0.15} Z`} />
    case 'pyramid':
      return <path d={`M${x} ${ground} L${x + w / 2} ${top} L${x + w} ${ground} Z`} />
    case 'bus':
      return (
        <g>
          <rect x={x} y={top} width={w} height={h * 0.82} rx={h * 0.08} />
          <circle cx={x + w * 0.2} cy={ground - h * 0.1} r={h * 0.1} />
          <circle cx={x + w * 0.8} cy={ground - h * 0.1} r={h * 0.1} />
        </g>
      )
    case 'block':
    case 'rect':
      return <rect x={x} y={top} width={w} height={h} />
  }
}

export const ScaleDrawing: React.FC<BlockProps<ScaleDrawingProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const area = drawArea(stage)
  const s = fitScale(p.objects, area.w, area.h)
  const ground = groundLine(p.objects, s, area)
  const appear = p.objects.map((o, i) => firstCue(cues, 'show', o.id) ?? 10 + i * 18)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <line x1={area.x} y1={ground} x2={area.x + area.w} y2={ground} stroke={colors.greenDim} strokeWidth={3} />
        {p.objects.map((o, i) => {
          const grow = progress(frame, appear[i], 22)
          if (grow <= 0) return null
          const color = PALETTE[i % PALETTE.length]
          return (
            <g key={o.id} fill={`${color}33`} stroke={color} strokeWidth={3}>
              {shapePath(o, area.x + o.x * s, ground, o.width * s, o.height * s * grow)}
            </g>
          )
        })}
      </svg>
      {p.objects.map((o, i) => {
        if (frame < appear[i] + 16) return null
        const top = Math.max(stage.y + 70, ground - o.height * s - LABEL_ROOM + 6)
        return (
          <LayoutBox
            key={o.id}
            id={`${sceneId}:obj:${o.id}`}
            kind="text"
            style={{ position: 'absolute', left: area.x + (o.x + o.width / 2) * s, top, textAlign: 'center', whiteSpace: 'nowrap', ...bootIn(frame, appear[i] + 16, 12, 'translateX(-50%)') }}
          >
            <div style={hud(24, colors.crt300)}>{o.label}</div>
            <div style={hud(32, colors.white)}>{dimensionLabel(o, p.unit)}</div>
          </LayoutBox>
        )
      })}
      <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
        {basisLine(p)}
      </LayoutBox>
    </AbsoluteFill>
  )
}
