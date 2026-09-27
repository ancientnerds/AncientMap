/**
 * UnitGrid: counts as unit squares ("one block = 80 city buses"), at most 400
 * cells, as large as the stage allows (ratios beyond 1:400 are a ScaleZoom,
 * linear too: owner decision 31). Groups light up one after the
 * other (a group starts on its show <id> cue, otherwise when the previous one
 * has filled) while their numbers roll; the basis is always on screen.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, digitRoll } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps } from './types'

export type UnitGroup = { id: string; count: number; label: string; tone: Tone }
export type UnitGridProps = { title: string; basis: string; unitLabel: string; columns?: number; groups: UnitGroup[] }

const MAX_CELLS = 400
/** Cells lit per frame while a group fills. */
const FILL_RATE = 2
const LEGEND_W = 480
const BASIS_H = 56

export function checkUnitGrid(p: UnitGridProps): string[] {
  const total = p.groups.reduce((n, g) => n + g.count, 0)
  return total > MAX_CELLS ? [`${total} cells; the grid holds at most ${MAX_CELLS}`] : []
}

/** The on-screen basis line (owner rule: comparisons state their basis). */
export function basisLine(p: UnitGridProps): string {
  return `1 square = ${p.unitLabel}. Basis: ${p.basis}`
}

/** First frame of each group: its show cue, else when the previous group has filled. */
export function groupStarts(groups: readonly UnitGroup[], cueFrame: (id: string) => number | null, first = 12): number[] {
  const starts: number[] = []
  groups.forEach((g, i) => {
    const prevEnd = i === 0 ? first : starts[i - 1] + Math.ceil(groups[i - 1].count / FILL_RATE) + 6
    starts.push(cueFrame(g.id) ?? prevEnd)
  })
  return starts
}

/** Grid geometry: columns (given, or the count that makes the cells largest) and the cell size. */
export function gridLayout(total: number, area: Rect, columns?: number): { columns: number; rows: number; cell: number } {
  const candidates = columns !== undefined ? [columns] : Array.from({ length: Math.min(total, 40) }, (_, i) => i + 1)
  let best = { columns: 1, rows: total, cell: 0 }
  for (const c of candidates) {
    const rows = Math.ceil(total / c)
    const cell = Math.min(area.w / c, area.h / rows)
    if (cell > best.cell) best = { columns: c, rows, cell }
  }
  return best
}

export const UnitGrid: React.FC<BlockProps<UnitGridProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const starts = groupStarts(p.groups, (id) => firstCue(cues, 'show', id))
  const total = p.groups.reduce((n, g) => n + g.count, 0)
  const area = { x: stage.x, y: stage.y + 90, w: stage.w - LEGEND_W - 60, h: stage.h - 90 - BASIS_H - 30 }
  const { columns, cell } = gridLayout(total, area, p.columns)
  const gap = Math.max(2, cell * 0.14)
  const cells: React.ReactNode[] = []
  let index = 0
  p.groups.forEach((g, gi) => {
    const lit = Math.max(0, Math.min(g.count, Math.floor((frame - starts[gi]) * FILL_RATE)))
    for (let k = 0; k < g.count; k++, index++) {
      const on = k < lit
      cells.push(
        <div
          key={index}
          style={{
            position: 'absolute',
            left: (index % columns) * cell,
            top: Math.floor(index / columns) * cell,
            width: cell - gap,
            height: cell - gap,
            background: on ? toneColor[g.tone] : 'transparent',
            border: `1px solid ${on ? toneColor[g.tone] : colors.greenDim}`,
          }}
        />,
      )
    }
  })
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <div style={{ position: 'absolute', left: area.x, top: area.y, width: area.w, height: area.h }}>{cells}</div>
      <div style={{ position: 'absolute', left: stage.x + stage.w - LEGEND_W, top: area.y, width: LEGEND_W }}>
        {p.groups.map((g, gi) => {
          if (frame < starts[gi]) return null
          return (
            <LayoutBox key={g.id} id={`${sceneId}:group:${g.id}`} kind="text" style={{ marginBottom: 32, ...bootIn(frame, starts[gi], 12) }}>
              <div style={{ ...hud(72, toneColor[g.tone]), letterSpacing: '0.02em' }}>{digitRoll(0, g.count, frame, starts[gi], Math.ceil(g.count / FILL_RATE))}</div>
              <div style={body(30, colors.text)}>{g.label}</div>
            </LayoutBox>
          )
        })}
      </div>
      <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
        {basisLine(p)}
      </LayoutBox>
    </AbsoluteFill>
  )
}
