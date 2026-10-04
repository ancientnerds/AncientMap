/**
 * Timeline (type D transmission, site phases): a horizontal year axis across
 * the stage. Events enter on their show <id> cues (staggered otherwise) with
 * labels alternating above and below the axis so neighbours keep apart (the
 * lint pass checks it). Negative years are BCE; year 0 does not exist. A scene
 * too short for the staggered events is refused (checkTimeline): the last event
 * would never be drawn.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { formatYear, yearTicks } from '../format'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, progress } from '../motion'
import { type Tone, colors, toneColor } from '../theme/colors'
import { body, heading, hud } from '../theme/type'
import type { BlockProps, CheckContext } from './types'

export type TimelineEvent = { id: string; year: number; label: string; tone: Tone }
export type TimelineProps = { title: string; from: number; to: number; events: TimelineEvent[]; basis?: string }

const BASIS_H = 56
/** Events in the outer 15 % of the axis carry edge-aligned labels, so the label stays on screen. */
const EDGE = 0.15
/** The axis draws from frame AXIS_START over AXIS_FRAMES frames. */
const AXIS_START = 4
const AXIS_FRAMES = 30
/** Frame the first event (by year) appears without a show cue, and the stagger of the next ones. */
const FIRST_EVENT = 30
const EVENT_STAGGER = 14
/** An event's dot boots in over DOT_FADE frames; its label starts LABEL_DELAY frames later and takes LABEL_FADE. */
const DOT_FADE = 8
const LABEL_DELAY = 4
const LABEL_FADE = 12

/** The events in axis order: the default stagger and the above/below alternation follow it. */
const byYear = (events: readonly TimelineEvent[]): TimelineEvent[] => [...events].sort((a, b) => a.year - b.year)

/** First frame of each event of `sorted` (axis order): its show cue, else staggered from FIRST_EVENT. */
function eventStarts(sorted: readonly TimelineEvent[], cueFrame: (id: string) => number | null): number[] {
  return sorted.map((e, i) => cueFrame(e.id) ?? FIRST_EVENT + i * EVENT_STAGGER)
}

/**
 * The first frame on which the axis is drawn and every event's dot and label are
 * in, for events appearing on their show cues (`cueFrame`) or staggered in axis
 * order. checkTimeline passes no cues: it sees the default schedule only.
 */
export function settledAt(events: readonly TimelineEvent[], cueFrame: (id: string) => number | null): number {
  const starts = eventStarts(byYear(events), cueFrame)
  return starts.reduce((done, s) => Math.max(done, s + Math.max(DOT_FADE, LABEL_DELAY + LABEL_FADE)), AXIS_START + AXIS_FRAMES)
}

/** Horizontal placement of an event label at axis fraction f: centred, or aligned to the near edge. */
export function labelAnchor(f: number): { textAlign: 'left' | 'center' | 'right'; transform: string; dx: number } {
  if (f < EDGE) return { textAlign: 'left', transform: '', dx: -16 }
  if (f > 1 - EDGE) return { textAlign: 'right', transform: 'translateX(-100%)', dx: 16 }
  return { textAlign: 'center', transform: 'translateX(-50%)', dx: 0 }
}

export function checkTimeline(p: TimelineProps, ctx: CheckContext): string[] {
  const errors = p.to <= p.from ? [`timeline range ${p.from}..${p.to} is empty`] : []
  for (const e of p.events) {
    if (e.year < p.from || e.year > p.to) errors.push(`event ${e.id} (${e.year}) lies outside ${p.from}..${p.to}`)
    if (e.year === 0) errors.push(`event ${e.id}: year 0 does not exist`)
  }
  const settled = settledAt(p.events, () => null)
  if (ctx.durationInFrames <= settled) {
    errors.push(`a Timeline scene needs at least ${settled + 1} frames (its events enter one after the other until frame ${settled}), got ${ctx.durationInFrames}`)
  }
  return errors
}

export const Timeline: React.FC<BlockProps<TimelineProps>> = ({ props: p, cues, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const axis = { x: stage.x + 60, y: stage.y + Math.round((stage.h - BASIS_H) / 2) + 40, w: stage.w - 120 }
  const xOf = (year: number) => axis.x + ((year - p.from) / (p.to - p.from)) * axis.w
  const events = byYear(p.events)
  const starts = eventStarts(events, (id) => firstCue(cues, 'show', id))
  const drawn = progress(frame, AXIS_START, AXIS_FRAMES)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <LayoutBox id={`${sceneId}:title`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y, width: stage.w, height: 60, overflow: 'hidden', ...heading(48), ...bootIn(frame, 0) }}>
        {p.title}
      </LayoutBox>
      <div style={{ position: 'absolute', left: axis.x, top: axis.y, width: axis.w * drawn, height: 4, background: colors.green }} />
      {yearTicks(p.from, p.to).map((y) => (
        <div key={y} style={{ position: 'absolute', left: xOf(y), top: axis.y + 14, transform: 'translateX(-50%)', ...hud(18, colors.crt400), whiteSpace: 'nowrap', opacity: drawn }}>
          {formatYear(y)}
        </div>
      ))}
      {events.map((e, i) => {
        const appear = starts[i]
        if (frame < appear) return null
        const x = xOf(e.year)
        const anchor = labelAnchor((e.year - p.from) / (p.to - p.from))
        const above = i % 2 === 0
        const color = toneColor[e.tone]
        return (
          <React.Fragment key={e.id}>
            <div style={{ position: 'absolute', left: x - 11, top: axis.y - 9, width: 22, height: 22, borderRadius: 11, background: color, ...bootIn(frame, appear, DOT_FADE) }} />
            <div style={{ position: 'absolute', left: x - 1, top: above ? axis.y - 80 : axis.y + 50, width: 2, height: 36, background: color, opacity: 0.7 }} />
            <LayoutBox
              id={`${sceneId}:event:${e.id}`}
              kind="text"
              style={{ position: 'absolute', left: x + anchor.dx, top: above ? axis.y - 170 : axis.y + 94, textAlign: anchor.textAlign, whiteSpace: 'nowrap', ...bootIn(frame, appear + LABEL_DELAY, LABEL_FADE, anchor.transform) }}
            >
              <div style={hud(26, color)}>{formatYear(e.year)}</div>
              <div style={body(30, colors.white)}>{e.label}</div>
            </LayoutBox>
          </React.Fragment>
        )
      })}
      {p.basis ? (
        <LayoutBox id={`${sceneId}:basis`} kind="text" style={{ position: 'absolute', left: stage.x, top: stage.y + stage.h - BASIS_H, width: stage.w, height: BASIS_H, overflow: 'hidden', ...body(24, colors.crt400) }}>
          {`Dates: ${p.basis}`}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
