/**
 * ListCard: a short numbered list across the stage, e.g. "what would change our
 * mind" or the verdict's reasons. Items boot in on their show <id> cues,
 * staggered otherwise; an optional note closes the card.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn } from '../motion'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { Panel } from './Panel'
import type { BlockProps } from './types'

export type ListItem = { id: string; text: string }
export type ListCardProps = { title: string; items: ListItem[]; note?: string }

const PAD = 56
const NOTE_H = 70

export const ListCard: React.FC<BlockProps<ListCardProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const panel = { x: stage.x + 60, y: stage.y + 10, w: stage.w - 120, h: stage.h - 20 }
  const listTop = PAD + 80
  const listBottom = panel.h - PAD - (p.note ? NOTE_H + 16 : 0)
  const rowH = Math.min(130, Math.floor((listBottom - listTop) / p.items.length))
  const itemSize = rowH >= 110 ? 40 : 32
  const first = listTop + Math.floor((listBottom - listTop - rowH * p.items.length) / 2)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Panel rect={panel}>
        <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: PAD, top: PAD, width: panel.w - 2 * PAD, height: 60, overflow: 'hidden', ...heading(44), ...bootIn(frame, 4) }}>
          {p.title}
        </LayoutBox>
        {p.items.map((item, i) => {
          const appear = firstCue(cues, 'show', item.id) ?? 14 + i * 14
          if (frame < appear) return null
          return (
            <div key={item.id} style={{ position: 'absolute', left: PAD, top: first + i * rowH, width: panel.w - 2 * PAD, height: rowH - 12, ...bootIn(frame, appear, 14) }}>
              <div style={{ position: 'absolute', left: 0, top: 4, ...hud(40, colors.green) }}>{String(i + 1).padStart(2, '0')}</div>
              <LayoutBox id={`${sceneId}:item:${item.id}`} kind="text" style={{ position: 'absolute', left: 110, top: 0, width: panel.w - 2 * PAD - 110, height: rowH - 12, overflow: 'hidden', ...body(itemSize, colors.white), lineHeight: 1.25 }}>
                {item.text}
              </LayoutBox>
            </div>
          )
        })}
        {p.note ? (
          <LayoutBox id={`${sceneId}:note`} kind="text" style={{ position: 'absolute', left: PAD, top: panel.h - PAD - NOTE_H, width: panel.w - 2 * PAD, height: NOTE_H, overflow: 'hidden', ...body(26, colors.crt300), ...bootIn(frame, 30) }}>
            {p.note}
          </LayoutBox>
        ) : null}
      </Panel>
    </AbsoluteFill>
  )
}
