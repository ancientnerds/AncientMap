/**
 * QuoteCard: a verbatim passage from the case file's evidence, for texts and
 * traditions (type D) and for sources whose page cannot be captured (paywall or
 * login). The quote, set in the site's serif, types on at its highlight
 * <evidence id> cue (default frame 12); the source line names work, locator and tier.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { domainOf } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, typeOn } from '../motion'
import { colors } from '../theme/colors'
import { body, hud, serif } from '../theme/type'
import { Panel } from './Panel'
import type { BlockProps, Evidence } from './types'

export type QuoteCardProps = { evidence: Evidence; attribution?: string }

const PAD = 64
const SOURCE_H = 96

export function checkQuoteCard(p: QuoteCardProps): string[] {
  return p.evidence.source.quote.trim() ? [] : [`evidence ${p.evidence.id} has no verbatim quote to show`]
}

export const QuoteCard: React.FC<BlockProps<QuoteCardProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const e = p.evidence
  const panel = { x: stage.x + 100, y: stage.y + 10, w: stage.w - 200, h: stage.h - 20 }
  const at = firstCue(cues, 'highlight', e.id) ?? 12
  const quote = e.source.quote
  const typed = typeOn(quote, frame, at, 2)
  const work = p.attribution ? `${p.attribution}, ${e.source.title}` : e.source.title
  const meta = [e.source.locator, domainOf(e.source.url), `tier ${e.source.tier}`].filter(Boolean).join('  //  ')
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Panel rect={panel}>
        <LayoutBox
          id={`${sceneId}:quote`}
          kind="text"
          style={{ position: 'absolute', left: PAD, top: PAD, width: panel.w - 2 * PAD, height: panel.h - 2 * PAD - SOURCE_H - 20, overflow: 'hidden', ...serif(52), display: 'flex', alignItems: 'center' }}
        >
          <div>{`“${typed}${typed.length === quote.length ? '”' : ''}`}</div>
        </LayoutBox>
        {/* The two lines never clip themselves: the box clips, and the lint measures the box, so a line that does not fit is an overflow, never a silently cut work title. */}
        <LayoutBox id={`${sceneId}:source`} kind="text" style={{ position: 'absolute', left: PAD, top: panel.h - PAD - SOURCE_H, width: panel.w - 2 * PAD, height: SOURCE_H, overflow: 'hidden', ...bootIn(frame, at + 10) }}>
          <div style={{ ...body(30, colors.white), whiteSpace: 'nowrap' }}>{work}</div>
          <div style={{ ...hud(20, colors.crt400), whiteSpace: 'nowrap' }}>{meta}</div>
        </LayoutBox>
      </Panel>
    </AbsoluteFill>
  )
}
