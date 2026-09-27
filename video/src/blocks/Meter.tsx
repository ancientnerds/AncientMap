/**
 * Meter: the probability meter between two hypotheses, large across the stage.
 * It starts at `start`; every meter cue of the episode, whichever scene carried
 * it, rolls the split to its value (state.ts), so a Meter shown later picks up
 * where the last one stopped. Under the numbers the house probability words.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { useEpisode } from '../context'
import { verbal } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn } from '../motion'
import { meterAt } from '../state'
import { colors } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { MeterValue } from '../timeline'
import type { BlockProps } from './types'

export type MeterProps = { hypotheses: [string, string]; start: MeterValue; title?: string; note?: string }

const LABEL_H = 96
const PCT_H = 150
const WORDS_H = 40
const BAR_H = 64
const NOTE_H = 84

/** Top of the labels row: the whole stack (labels, numbers, words, bar, note) centred below the title. */
export function meterTop(stageY: number, stageH: number, withNote: boolean): number {
  const stack = LABEL_H + 10 + PCT_H + WORDS_H + 30 + BAR_H + (withNote ? 40 + NOTE_H : 0)
  const areaTop = stageY + 90
  return areaTop + Math.max(0, Math.floor((stageY + stageH - areaTop - stack) / 2))
}

export function checkMeter(p: MeterProps): string[] {
  return p.start[0] + p.start[1] === 100 ? [] : [`meter start ${JSON.stringify(p.start)} must sum to 100`]
}

export const Meter: React.FC<BlockProps<MeterProps>> = ({ props: p, sceneId, sceneFrom, stage }) => {
  const frame = useCurrentFrame()
  const { state } = useEpisode()
  const { a } = meterAt(state, p.start, sceneFrom + frame)
  const b = 100 - a
  const colW = Math.floor(stage.w / 2) - 40
  const labelsY = meterTop(stage.y, stage.h, Boolean(p.note))
  const pctY = labelsY + LABEL_H + 10
  const wordsY = pctY + PCT_H
  const barY = wordsY + WORDS_H + 30
  const noteY = barY + BAR_H + 40
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title ?? 'The balance of evidence'}
      </LayoutBox>
      {[0, 1].map((side) => {
        const value = side === 0 ? a : b
        const color = side === 0 ? colors.green : colors.amber
        const left = side === 0 ? stage.x : stage.x + stage.w - colW
        const align = side === 0 ? 'left' : 'right'
        return (
          <React.Fragment key={side}>
            <LayoutBox id={`${sceneId}:hyp${side}`} kind="text" style={{ position: 'absolute', left, top: labelsY, width: colW, height: LABEL_H, overflow: 'hidden', textAlign: align, ...body(36, colors.text), lineHeight: 1.25, ...bootIn(frame, 6 + side * 6) }}>
              {p.hypotheses[side]}
            </LayoutBox>
            <LayoutBox id={`${sceneId}:pct${side}`} kind="text" style={{ position: 'absolute', left, top: pctY, width: colW, height: PCT_H, overflow: 'hidden', textAlign: align, ...heading(110, color), letterSpacing: '0.02em', ...bootIn(frame, 10 + side * 6) }}>
              {`${Math.round(value)}%`}
            </LayoutBox>
            <LayoutBox id={`${sceneId}:words${side}`} kind="text" style={{ position: 'absolute', left, top: wordsY, width: colW, height: WORDS_H, overflow: 'hidden', textAlign: align, ...hud(26, colors.crt300), ...bootIn(frame, 14 + side * 6) }}>
              {verbal(value)}
            </LayoutBox>
          </React.Fragment>
        )
      })}
      <div style={{ position: 'absolute', left: stage.x, top: barY, width: stage.w, height: BAR_H, border: `1px solid ${colors.greenDim}`, ...bootIn(frame, 8) }}>
        <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${a}%`, background: colors.green }} />
        <div style={{ position: 'absolute', right: 0, top: 0, height: '100%', width: `${b}%`, background: colors.amber, opacity: 0.85 }} />
        <div style={{ position: 'absolute', left: `${a}%`, top: -12, width: 4, height: BAR_H + 24, marginLeft: -2, background: colors.white }} />
      </div>
      {p.note ? (
        <LayoutBox id={`${sceneId}:note`} kind="text" style={{ position: 'absolute', left: stage.x, top: noteY, width: stage.w, height: NOTE_H, overflow: 'hidden', textAlign: 'center', ...body(30, colors.white), ...bootIn(frame, 20) }}>
          {p.note}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
