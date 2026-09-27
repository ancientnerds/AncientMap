/**
 * ClaimBoard: the claims under test, in rows that fill the stage. Its state is
 * episode-wide (state.ts): a claim appears at its introduce cue, whichever scene
 * carried it (claims without any introduce cue enter staggered at the scene
 * start); a status cue recolours it and slams the new status as a stamp. A
 * board shown later in the episode shows everything cued before it. The local
 * cue highlight <claim id> outlines the row.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { useEpisode } from '../context'
import { firstCue } from '../cues'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { claimStatusAt } from '../state'
import { colors, statusColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { Icon } from './icons'
import { Stamp } from './Stamp'
import type { BlockProps, Claim } from './types'

export type ClaimBoardProps = { claims: Claim[]; title?: string }

export const TITLE_H = 60
const MAX_ROW_H = 190
/** Space under each row panel. */
const ROW_GAP = 14
/** The label box ends this far left of the stage's right edge. */
const LABEL_END = 420
/**
 * The stamp and the status text start this far left of the stage's right edge: 60 px after the
 * label, room for the 54 px a SUPPORTED stamp reaches left of its box when it slams in at 1.35x
 * tilted -6 deg, and far enough in that it reaches only to frame x 1811 (both stages run from
 * x 96, 1728 wide), inside the safe area's 1824.
 */
const STATUS_X = 360

/**
 * Row height, label size, stamp size and the first row's top: rows as tall as the stage allows,
 * the block centred in it. The stamp shrinks with the row so that the widest status, slamming in
 * at 1.35x and tilted, keeps its bounding box within its own row's height: the stamps of
 * neighbouring rows never meet, even when they slam together (test/blocks-cards.test.ts checks
 * every board on both stages).
 */
export function boardLayout(count: number, stage: Rect): { rowH: number; labelSize: number; stampSize: number; top: number } {
  const areaTop = stage.y + TITLE_H + 30
  const areaBottom = stage.y + stage.h
  const rowH = Math.min(MAX_ROW_H, Math.floor((areaBottom - areaTop) / count))
  const labelSize = rowH >= 160 ? 46 : rowH >= 120 ? 38 : 30
  const stampSize = rowH >= 140 ? 32 : rowH >= 110 ? 28 : rowH >= 95 ? 22 : rowH >= 85 ? 19 : 14
  return { rowH, labelSize, stampSize, top: areaTop + Math.floor((areaBottom - areaTop - rowH * count) / 2) }
}

export type RowFrame = { h: number; label: Rect; statusX: number }

/** A row's panel height, its label box and the left edge of its status column, relative to the row. */
export function rowFrame(stageW: number, rowH: number): RowFrame {
  return { h: rowH - ROW_GAP, label: { x: 120, y: 6, w: stageW - 120 - LABEL_END, h: rowH - 26 }, statusX: stageW - STATUS_X }
}

/** Scene frame a claim appears on the board, or null when it is introduced only after this scene. */
export function claimAppear(introducedAbs: number | undefined, index: number, sceneFrom: number, sceneEnd: number): number | null {
  if (introducedAbs === undefined) return 8 + index * 10
  if (introducedAbs >= sceneEnd) return null
  return Math.max(0, introducedAbs - sceneFrom)
}

export const ClaimBoard: React.FC<BlockProps<ClaimBoardProps>> = ({ props: p, cues, durationInFrames, sceneId, sceneFrom, stage }) => {
  const frame = useCurrentFrame()
  const { state } = useEpisode()
  const title = p.title ?? 'The claims'
  const { rowH, labelSize, stampSize, top: rowsTop } = boardLayout(p.claims.length, stage)
  const row = rowFrame(stage.w, rowH)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: TITLE_H, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {title}
      </LayoutBox>
      {p.claims.map((c, i) => {
        const appear = claimAppear(state.introduced.get(c.id), i, sceneFrom, sceneFrom + durationInFrames)
        if (appear === null || frame < appear) return null
        const { status, since } = claimStatusAt(state, c.id, c.status, sceneFrom + frame)
        const color = statusColor[status]
        const top = rowsTop + i * rowH
        const hl = firstCue(cues, 'highlight', c.id)
        const glow = hl === null ? 0 : progress(frame, hl, 10)
        return (
          <div key={c.id} style={{ position: 'absolute', left: stage.x, top, width: stage.w, height: row.h, ...bootIn(frame, appear, 14) }}>
            <div style={{ position: 'absolute', inset: 0, background: colors.bgPanel, border: `2px solid ${colors.amber}`, opacity: glow }} />
            <div style={{ position: 'absolute', left: 0, top: 0, width: 10, height: row.h, background: color }} />
            <div style={{ position: 'absolute', left: 34, top: (row.h - 64) / 2 }}>
              <Icon name={c.icon} color={color} size={64} />
            </div>
            <LayoutBox id={`${sceneId}:claim:${c.id}`} kind="text" style={{ position: 'absolute', left: row.label.x, top: row.label.y, width: row.label.w, height: row.label.h, overflow: 'hidden', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{ ...body(labelSize, colors.white), lineHeight: 1.2 }}>{c.label}</div>
              {c.by ? <div style={hud(22, colors.crt400)}>{c.by}</div> : null}
            </LayoutBox>
            {/* the stamp or the status text, centred on the panel's height whatever its size */}
            <div style={{ position: 'absolute', left: row.statusX, top: 0, height: row.h, display: 'flex', alignItems: 'center' }}>
              {since !== null ? (
                <Stamp id={`${sceneId}:stamp:${c.id}`} text={status} color={color} start={since - sceneFrom} size={stampSize} style={{ position: 'relative' }} />
              ) : (
                <LayoutBox id={`${sceneId}:status:${c.id}`} kind="text" style={hud(28, color)}>
                  {status}
                </LayoutBox>
              )}
            </div>
          </div>
        )
      })}
    </AbsoluteFill>
  )
}
