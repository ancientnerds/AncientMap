/**
 * An image in one transformed layer together with its markers (PhotoPlate) or
 * pins and distance lines (MapboxTopdown). Ring, pin and line geometry live
 * inside the layer in image pixels, so they move with the image exactly (owner
 * rule); stroke widths are divided by the view scale to stay constant on
 * screen. Labels are drawn in screen space at the transformed position and
 * registered for the overlap lint.
 */
import React from 'react'
import { Img, staticFile, useCurrentFrame } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import type { ImageBox, View } from '../layout/transform'
import { rectToScreen, toScreen } from '../layout/transform'
import { ZONES } from '../layout/zones'
import { bootIn, progress, ringPulse, typeOn } from '../motion'
import { colors } from '../theme/colors'
import { hud } from '../theme/type'

export type LayerMark = { id: string; box: ImageBox; label: string; appear: number; focused: boolean; shape: 'ring' | 'pin' }
export type LayerLine = { id: string; from: { x: number; y: number }; to: { x: number; y: number }; text: string; appear: number }

const LABEL_H = 44
const LABEL_GAP = 14
const LINE_DRAW_FRAMES = 24

export const ImageLayer: React.FC<{
  sceneId: string
  src: string
  width: number
  height: number
  view: View
  marks: readonly LayerMark[]
  lines?: readonly LayerLine[]
}> = ({ sceneId, src, width, height, view, marks, lines = [] }) => {
  const frame = useCurrentFrame()
  const stroke = 3 / view.scale
  const shown = marks.filter((m) => frame >= m.appear)
  return (
    <>
      <div style={{ position: 'absolute', left: 0, top: 0, width, height, transformOrigin: '0 0', transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})` }}>
        <Img src={staticFile(src)} style={{ position: 'absolute', left: 0, top: 0, width, height }} />
        <svg width={width} height={height} style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible' }}>
          {lines
            .filter((l) => frame >= l.appear)
            .map((l) => {
              const len = Math.hypot(l.to.x - l.from.x, l.to.y - l.from.y)
              const drawn = progress(frame, l.appear, LINE_DRAW_FRAMES)
              return <line key={l.id} x1={l.from.x} y1={l.from.y} x2={l.to.x} y2={l.to.y} stroke={colors.amber} strokeWidth={stroke} strokeDasharray={`${len * drawn} ${len}`} />
            })}
          {shown.map((m) => {
            const [x, y, w, h] = m.box
            const pulse = ringPulse(frame, m.appear)
            const cx = x + w / 2
            const cy = y + h / 2
            const color = m.focused ? colors.amber : colors.green
            if (m.shape === 'pin') {
              const r = 10 / view.scale
              return (
                <g key={m.id}>
                  <circle cx={cx} cy={cy} r={r * pulse.scale * 2} fill="none" stroke={color} strokeWidth={stroke} opacity={pulse.opacity} />
                  <circle cx={cx} cy={cy} r={r} fill={color} stroke={colors.bg} strokeWidth={stroke * 0.7} />
                </g>
              )
            }
            return (
              <g key={m.id}>
                <rect x={x} y={y} width={w} height={h} fill="none" stroke={color} strokeWidth={stroke} rx={6 / view.scale} />
                <ellipse cx={cx} cy={cy} rx={(w / 2) * pulse.scale * 1.25} ry={(h / 2) * pulse.scale * 1.25} fill="none" stroke={color} strokeWidth={stroke} opacity={pulse.opacity} />
              </g>
            )
          })}
        </svg>
      </div>
      {shown.map((m) => {
        const r = rectToScreen(view, m.box)
        const ringId = `${sceneId}:mark:${m.id}`
        const labelId = `${sceneId}:label:${m.id}`
        const above = r.y - LABEL_GAP - LABEL_H >= ZONES.stage.y
        const top = above ? r.y - LABEL_GAP - LABEL_H : r.y + r.h + LABEL_GAP
        const color = m.focused ? colors.amber : colors.green
        return (
          <React.Fragment key={m.id}>
            <LayoutBox id={ringId} kind="mark" allow={[labelId]} style={{ position: 'absolute', left: r.x, top: r.y, width: r.w, height: r.h }} />
            <div style={{ position: 'absolute', left: r.x + r.w / 2, top, ...bootIn(frame, m.appear + 6, 12, 'translateX(-50%)') }}>
              <LayoutBox
                id={labelId}
                kind="text"
                allow={[ringId]}
                style={{ ...hud(26, colors.bg), background: color, padding: '7px 16px', whiteSpace: 'nowrap', height: LABEL_H, boxSizing: 'border-box' }}
              >
                {typeOn(m.label, frame, m.appear + 6, 1.2)}
              </LayoutBox>
            </div>
          </React.Fragment>
        )
      })}
      {lines
        .filter((l) => frame >= l.appear + LINE_DRAW_FRAMES)
        .map((l) => {
          const a = toScreen(view, l.from.x, l.from.y)
          const b = toScreen(view, l.to.x, l.to.y)
          return (
            <div key={l.id} style={{ position: 'absolute', left: (a.x + b.x) / 2, top: (a.y + b.y) / 2 - LABEL_H - 10, ...bootIn(frame, l.appear + LINE_DRAW_FRAMES, 12, 'translateX(-50%)') }}>
              <LayoutBox id={`${sceneId}:line:${l.id}`} kind="text" style={{ ...hud(26, colors.bg), background: colors.amber, padding: '7px 16px', whiteSpace: 'nowrap', height: LABEL_H, boxSizing: 'border-box' }}>
                {l.text}
              </LayoutBox>
            </div>
          )
        })}
    </>
  )
}
