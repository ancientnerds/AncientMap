/**
 * A 2D canvas stand-in for label tests in the node environment. `measureText`
 * depends on everything the real one does for a label - the font (weight,
 * style, size), the letter spacing and every character - with fractional
 * widths, so a size that rounds or measures the wrong text shows up.
 */

import { vi } from 'vitest'

export interface FakeLabelCanvas {
  width: number
  height: number
  context: FakeLabelContext
  getContext: (kind: string) => FakeLabelContext
}

export class FakeLabelContext {
  font = '10px sans-serif'
  letterSpacing = '0px'
  textBaseline = 'alphabetic'
  textAlign = 'start'
  imageSmoothingEnabled = false
  imageSmoothingQuality = 'low'
  shadowColor = ''
  shadowBlur = 0
  shadowOffsetX = 0
  shadowOffsetY = 0
  strokeStyle = ''
  fillStyle = ''
  lineWidth = 1
  lineJoin = 'miter'
  lineCap = 'butt'
  /** Every text drawn: [method, text, font, letterSpacing]. */
  readonly drawn: Array<[string, string, string, string]> = []

  measureText(text: string): { width: number } {
    return { width: fakeTextWidth(this.font, this.letterSpacing, text) }
  }

  strokeText(text: string): void {
    this.drawn.push(['stroke', text, this.font, this.letterSpacing])
  }

  fillText(text: string): void {
    this.drawn.push(['fill', text, this.font, this.letterSpacing])
  }
}

/** Stands for the font files: a test sets `widthFactor` to model a web font that finished loading between two measurements. */
export const fakeGlyphs = { widthFactor: 1 }

/** The fake glyph metrics: size from the font, 600 wider than 400, italic wider still, per-character widths. */
export function fakeTextWidth(font: string, letterSpacing: string, text: string): number {
  const size = Number(/(\d+(?:\.\d+)?)px/.exec(font)?.[1])
  if (!Number.isFinite(size)) throw new Error(`fake canvas: no px size in font "${font}"`)
  const spacing = Number.parseFloat(letterSpacing)
  const weight = /\b600\b/.test(font) ? 1.08 : 1
  const italic = font.startsWith('italic ') ? 1.03 : 1
  let width = 0
  for (const ch of text) width += size * (0.51 + (ch.codePointAt(0)! % 11) * 0.0137) * weight * italic + spacing
  return width * fakeGlyphs.widthFactor
}

/** Stubs `document.createElement('canvas')`; returns every canvas handed out. */
export function stubLabelCanvas(): FakeLabelCanvas[] {
  const canvases: FakeLabelCanvas[] = []
  vi.stubGlobal('document', {
    createElement: (tag: string) => {
      if (tag !== 'canvas') throw new Error(`fake document: createElement('${tag}')`)
      const context = new FakeLabelContext()
      const canvas: FakeLabelCanvas = {
        width: 300,
        height: 150,
        context,
        getContext: (kind: string) => {
          if (kind !== '2d') throw new Error(`fake canvas: getContext('${kind}')`)
          return context
        },
      }
      canvases.push(canvas)
      return canvas
    },
  })
  return canvases
}
