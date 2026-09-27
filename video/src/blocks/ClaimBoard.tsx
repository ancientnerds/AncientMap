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
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { claimStatusAt } from '../state'
import { colors, statusColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { Icon } from './icons'
import { Stamp } from './Stamp'
import type { BlockProps, Claim } from './types'

export type ClaimBoardProps = { claims: Claim[]; title?: string }

const TITLE_H = 60
const STATUS_W = 380
const MAX_ROW_H = 190

/** Row height, label size and the first row's top: rows as tall as the stage allows, the block centred in it. */
export function boardLayout(count: number, areaTop: number, areaBottom: number): { rowH: number; labelSize: number; top: number } {
  const rowH = Math.min(MAX_ROW_H, Math.floor((areaBottom - areaTop) / count))
  const labelSize = rowH >= 160 ? 46 : rowH >= 120 ? 38 : 30
  return { rowH, labelSize, top: areaTop + Math.floor((areaBottom - areaTop - rowH * count) / 2) }
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
  const { rowH, labelSize, top: rowsTop } = boardLayout(p.claims.length, stage.y + TITLE_H + 30, stage.y + stage.h)
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
          <div key={c.id} style={{ position: 'absolute', left: stage.x, top, width: stage.w, height: rowH - 14, ...bootIn(frame, appear, 14) }}>
            <div style={{ position: 'absolute', inset: 0, background: colors.bgPanel, border: `2px solid ${colors.amber}`, opacity: glow }} />
            <div style={{ position: 'absolute', left: 0, top: 0, width: 10, height: rowH - 14, background: color }} />
            <div style={{ position: 'absolute', left: 34, top: (rowH - 14 - 64) / 2 }}>
              <Icon name={c.icon} color={color} size={64} />
            </div>
            <LayoutBox id={`${sceneId}:claim:${c.id}`} kind="text" style={{ position: 'absolute', left: 120, top: 6, width: stage.w - 120 - STATUS_W, height: rowH - 26, overflow: 'hidden', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{ ...body(labelSize, colors.white), lineHeight: 1.2 }}>{c.label}</div>
              {c.by ? <div style={hud(22, colors.crt400)}>{c.by}</div> : null}
            </LayoutBox>
            {since !== null ? (
              <Stamp id={`${sceneId}:stamp:${c.id}`} text={status} color={color} start={since - sceneFrom} size={32} style={{ left: stage.w - STATUS_W + 40, top: (rowH - 14 - 62) / 2 }} />
            ) : (
              <LayoutBox id={`${sceneId}:status:${c.id}`} kind="text" style={{ position: 'absolute', left: stage.w - STATUS_W + 40, top: (rowH - 14 - 34) / 2, ...hud(28, color) }}>
                {status}
              </LayoutBox>
            )}
          </div>
        )
      })}
    </AbsoluteFill>
  )
}
