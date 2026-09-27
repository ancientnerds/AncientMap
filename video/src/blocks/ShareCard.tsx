/**
 * ShareCard: the end card, the one place the link appears in the picture
 * (owner rule: platform moments are never adverts; the link is on the end
 * card and in the description only). checkBlocks (index.ts) refuses it on any
 * scene but the last.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, typeOn } from '../motion'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { Panel } from './Panel'
import type { BlockProps } from './types'

export type ShareCardProps = { headline: string; url: string; lines: string[] }

export const ShareCard: React.FC<BlockProps<ShareCardProps>> = ({ props: p, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const panel = { x: stage.x + 200, y: stage.y + 60, w: stage.w - 400, h: stage.h - 120 }
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Panel rect={panel}>
        <LayoutBox id={`${sceneId}:headline`} kind="text" style={{ position: 'absolute', left: 64, top: 60, width: panel.w - 128, height: 130, overflow: 'hidden', ...heading(54), ...bootIn(frame, 8) }}>
          {p.headline}
        </LayoutBox>
        <LayoutBox id={`${sceneId}:url`} kind="text" style={{ position: 'absolute', left: 64, top: 220, width: panel.w - 128, height: 64, overflow: 'hidden', whiteSpace: 'nowrap', ...hud(44, colors.green), letterSpacing: '0.02em', textTransform: 'none' }}>
          {typeOn(p.url, frame, 18, 1.5)}
        </LayoutBox>
        {p.lines.map((line, i) => (
          <LayoutBox key={line} id={`${sceneId}:line${i}`} kind="text" style={{ position: 'absolute', left: 64, top: 320 + i * 50, width: panel.w - 128, height: 44, overflow: 'hidden', whiteSpace: 'nowrap', ...body(30, colors.crt300), ...bootIn(frame, 40 + i * 8) }}>
            {line}
          </LayoutBox>
        ))}
      </Panel>
    </AbsoluteFill>
  )
}
