/**
 * SourceViewer: a captured source page (pipeline/studio/capture/sources.py:
 * 1280 CSS px wide at device scale 2, the quote already highlighted in the page,
 * banners removed) inside a browser frame filling the stage. The page scrolls
 * from the quote low in the window up to 35 % from the top; an outline glows
 * around the highlighted quote from its highlight <evidence id> cue (default
 * 40 % into the scene). The capture's "page" event carries the URL, whose ASCII
 * hostname is all the address bar draws (the page's own <title> in that event is
 * a record only, never drawn: owner decision 32, so a Greek or Chinese source page
 * shows as captured), its "highlight" event the quote's box in image pixels.
 */
import React from 'react'
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from 'remotion'

import { firstCue } from '../cues'
import { domainOf } from '../format'
import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { bootIn, crtOpen, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, hud } from '../theme/type'
import type { BlockProps, Capture, Evidence } from './types'

export type SourceViewerProps = { page: Capture; evidence: Evidence }
export type ScrollKey = { at: number; y: number }

const BAR = 52
const CAPTION_H = 44

export function windowRect(stage: Rect): Rect {
  return { x: stage.x + 40, y: stage.y, w: stage.w - 80, h: stage.h - CAPTION_H - 20 }
}

/** The page's url and the highlight box from the capture events. */
export function pageInfo(page: Capture): { url: string; box: [number, number, number, number] } {
  const meta = page.events.find((e) => e.name === 'page')
  const hl = page.events.find((e) => e.name === 'highlight')
  if (!meta?.url || !hl?.box) throw new Error(`capture ${page.id} lacks its page or highlight event`)
  return { url: meta.url, box: hl.box }
}

export function checkSourceViewer(p: SourceViewerProps): string[] {
  const meta = p.page.events.find((e) => e.name === 'page')
  const hl = p.page.events.find((e) => e.name === 'highlight')
  const errors: string[] = []
  if (!meta?.url) errors.push(`capture ${p.page.id} has no page event with a url`)
  if (!hl?.box) errors.push(`capture ${p.page.id} has no highlight event with a box`)
  else if (hl.box[0] + hl.box[2] > p.page.width || hl.box[1] + hl.box[3] > p.page.height) errors.push(`the highlight of ${p.page.id} lies outside the page image`)
  return errors
}

/** Page scroll (image pixels at the window's top) from the quote low in the window to 35 % from the top. */
export function defaultScroll(pageW: number, pageH: number, quoteY: number, win: Rect): ScrollKey[] {
  const viewport = ((win.h - BAR) * pageW) / win.w
  const maxY = Math.max(0, pageH - viewport)
  const clamp = (y: number) => Math.min(maxY, Math.max(0, y))
  return [
    { at: 0, y: clamp(quoteY - viewport * 0.8) },
    { at: 0.45, y: clamp(quoteY - viewport * 0.35) },
    { at: 1, y: clamp(quoteY - viewport * 0.35) },
  ]
}

export function scrollAt(keys: readonly ScrollKey[], t: number): number {
  if (t <= keys[0].at) return keys[0].y
  for (let i = 1; i < keys.length; i++) {
    if (t <= keys[i].at) {
      const u = (t - keys[i - 1].at) / Math.max(keys[i].at - keys[i - 1].at, 1e-6)
      return keys[i - 1].y + (keys[i].y - keys[i - 1].y) * u * u * (3 - 2 * u)
    }
  }
  return keys[keys.length - 1].y
}

export const SourceViewer: React.FC<BlockProps<SourceViewerProps>> = ({ props: p, cues, durationInFrames, sceneId, stage }) => {
  const frame = useCurrentFrame()
  const win = windowRect(stage)
  const { url, box } = pageInfo(p.page)
  const scale = win.w / p.page.width
  const y = scrollAt(defaultScroll(p.page.width, p.page.height, box[1], win), durationInFrames > 1 ? frame / (durationInFrames - 1) : 0)
  const glowAt = firstCue(cues, 'highlight', p.evidence.id) ?? Math.round(durationInFrames * 0.4)
  const glow = progress(frame, glowAt, 14)
  const [hx, hy, hw, hh] = box
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <div style={{ position: 'absolute', left: win.x, top: win.y, width: win.w, height: win.h, overflow: 'hidden', border: `1px solid ${colors.greenDim}`, background: '#ffffff', transformOrigin: 'center', ...crtOpen(frame, 0) }}>
        <div style={{ position: 'absolute', left: 0, top: 0, width: win.w, height: BAR, background: '#16202a', display: 'flex', alignItems: 'center', paddingLeft: 20, gap: 10 }}>
          {[colors.red, colors.amber, colors.okGreen].map((c) => (
            <div key={c} style={{ width: 12, height: 12, borderRadius: 6, background: c }} />
          ))}
          <LayoutBox id={`${sceneId}:url`} kind="text" style={{ marginLeft: 20, width: win.w - 180, height: 32, overflow: 'hidden', whiteSpace: 'nowrap', ...body(22, colors.crt300), lineHeight: '32px' }}>
            {domainOf(url)}
          </LayoutBox>
        </div>
        <div style={{ position: 'absolute', left: 0, top: BAR, width: win.w, height: win.h - BAR, overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: 0, top: 0, width: p.page.width, height: p.page.height, transformOrigin: '0 0', transform: `scale(${scale}) translateY(${-y}px)` }}>
            <Img src={staticFile(p.page.src)} style={{ position: 'absolute', left: 0, top: 0, width: p.page.width, height: p.page.height }} />
            <div
              style={{
                position: 'absolute',
                left: hx - 14,
                top: hy - 14,
                width: hw + 28,
                height: hh + 28,
                border: `${4 / scale}px solid ${colors.green}`,
                borderRadius: 8 / scale,
                opacity: glow,
                boxShadow: `0 0 ${26 / scale}px ${colors.green}`,
              }}
            />
          </div>
        </div>
      </div>
      <LayoutBox
        id={`${sceneId}:caption`}
        kind="text"
        style={{ position: 'absolute', left: win.x, top: win.y + win.h + 14, width: win.w, height: CAPTION_H, overflow: 'hidden', whiteSpace: 'nowrap', ...hud(22, colors.crt400), lineHeight: `${CAPTION_H}px`, ...bootIn(frame, 10) }}
      >
        {`Source page // tier ${p.evidence.source.tier} // quote highlighted`}
      </LayoutBox>
    </AbsoluteFill>
  )
}
