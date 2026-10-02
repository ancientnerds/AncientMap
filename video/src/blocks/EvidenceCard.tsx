/**
 * EvidenceCard: one sourced evidence item of the case file: what it is, the
 * statement, the verbatim quote from the source (types on at its highlight
 * <evidence id> cue, else at frame 24), the source line (domain, tier,
 * locator, paper anchor) and a VERIFIED stamp (stamp <evidence id> cue, else
 * 70 % into the scene; only verified evidence reaches a script). A status cue
 * for the evidence's claim in this scene slams the claim's new status on the card.
 */
import React from 'react'
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from 'remotion'

import { firstCue, latestCue } from '../cues'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, typeOn } from '../motion'
import { type ClaimStatus, colors, statusColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import { COMPOSED, lineProblem, sourceLine } from './composed'
import { Panel } from './Panel'
import { Stamp } from './Stamp'
import type { BlockProps, Evidence, Media } from './types'

export type EvidenceCardProps = { evidence: Evidence; image?: Media }

const PAD = 48
const GAP = 18
const HEAD_H = 36
const SOURCE_H = 80
const IMAGE_W = 500
const STAMP_COLUMN = 360

/** The source line is one 18 px caps line: it must fit in total, whatever the host and the locator. */
export function checkEvidenceCard(p: EvidenceCardProps): string[] {
  const limits = COMPOSED['EvidenceCard.sourceLine']
  return lineProblem(`evidence ${p.evidence.id}: the source line`, sourceLine(p.evidence), p.image ? limits.image : limits.plain, 'the card', p.image ? 'beside an image' : 'with no image')
}

/** Vertical layout of the card's text inside a panel of height h: statement 45 %, quote 55 % of the free space. */
export function cardLayout(h: number): { statement: Rect; quote: Rect; source: Rect } {
  const free = h - 2 * PAD - HEAD_H - SOURCE_H - 3 * GAP
  const statementH = Math.floor(free * 0.45)
  const quoteH = free - statementH
  const statementY = PAD + HEAD_H + GAP
  const quoteY = statementY + statementH + GAP
  return {
    statement: { x: PAD, y: statementY, w: 0, h: statementH },
    quote: { x: PAD, y: quoteY, w: 0, h: quoteH },
    source: { x: PAD, y: h - PAD - SOURCE_H, w: 0, h: SOURCE_H },
  }
}

export const EvidenceCard: React.FC<BlockProps<EvidenceCardProps>> = ({ props: p, cues, durationInFrames, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const e = p.evidence
  const panel = { x: stage.x + 60, y: stage.y + 10, w: stage.w - 120, h: stage.h - 20 }
  const layout = cardLayout(panel.h)
  // The right column holds the image (if any) and the stamps; the text keeps clear of it.
  const textW = panel.w - 2 * PAD - (p.image ? IMAGE_W + PAD : STAMP_COLUMN)
  const quoteAt = firstCue(cues, 'highlight', e.id) ?? 24
  const stampAt = firstCue(cues, 'stamp', e.id) ?? Math.round(durationInFrames * 0.7)
  const status = latestCue(cues, 'status', e.claim_id, frame)
  const quote = e.source.quote
  const typed = typeOn(quote, frame, quoteAt, 2)
  const source = sourceLine(e)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Panel rect={panel}>
        <LayoutBox id={`${sceneId}:head`} kind="text" style={{ position: 'absolute', left: PAD, top: PAD, width: textW, height: HEAD_H, overflow: 'hidden', whiteSpace: 'nowrap', ...hud(24), ...bootIn(frame, 6) }}>
          {`Evidence // ${e.kind}`}
        </LayoutBox>
        <LayoutBox
          id={`${sceneId}:statement`}
          kind="text"
          style={{ position: 'absolute', left: PAD, top: layout.statement.y, width: textW, height: layout.statement.h, overflow: 'hidden', ...heading(40), textTransform: 'none', letterSpacing: '0.02em', ...bootIn(frame, 10) }}
        >
          {e.statement}
        </LayoutBox>
        {quote ? (
          <LayoutBox
            id={`${sceneId}:quote`}
            kind="text"
            style={{ position: 'absolute', left: PAD, top: layout.quote.y, width: textW, height: layout.quote.h, overflow: 'hidden', ...body(32, colors.crt300), borderLeft: `4px solid ${colors.green}`, paddingLeft: 22, boxSizing: 'border-box' }}
          >
            {`“${typed}${typed.length === quote.length ? '”' : ''}`}
          </LayoutBox>
        ) : null}
        {/* The two lines never clip themselves: the box clips, and the lint measures the box, so a line that does not fit is an overflow, never a silently cut title. */}
        <LayoutBox id={`${sceneId}:source`} kind="text" style={{ position: 'absolute', left: PAD, top: layout.source.y, width: textW, height: SOURCE_H, overflow: 'hidden', ...bootIn(frame, 16) }}>
          <div style={{ ...body(24, colors.text), whiteSpace: 'nowrap' }}>{e.source.title}</div>
          <div style={{ ...hud(18, colors.crt400), whiteSpace: 'nowrap' }}>{source}</div>
        </LayoutBox>
        {p.image ? (
          <div style={{ position: 'absolute', left: panel.w - PAD - IMAGE_W, top: PAD, width: IMAGE_W, height: panel.h - 2 * PAD - 110, overflow: 'hidden', border: `1px solid ${colors.greenDim}`, ...bootIn(frame, 12) }}>
            <Img src={staticFile(p.image.src)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
        ) : null}
      </Panel>
      <Stamp id={`${sceneId}:verified`} text="Verified" color={colors.okGreen} start={stampAt} size={30} style={{ left: panel.x + panel.w - 330, top: panel.y + panel.h - 100 }} />
      {status ? (
        <Stamp
          id={`${sceneId}:status`}
          text={String(status.value)}
          color={statusColor[status.value as ClaimStatus]}
          start={status.frame}
          size={30}
          style={{ left: panel.x + panel.w - 330, top: panel.y + panel.h - 230 }}
        />
      ) : null}
    </AbsoluteFill>
  )
}
