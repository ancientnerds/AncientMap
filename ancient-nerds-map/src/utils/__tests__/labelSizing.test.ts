/**
 * Label sizing apart from drawing (U13). A geo label's mesh is created at load
 * with the size its texture will have, and the texture is drawn when the label
 * is first shown. `measureLabel` must therefore give exactly the canvas size
 * `createLabelTexture` produces - for every style, with letter spacing and
 * uppercase - and must not draw or create a canvas per label.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ATLAS_FONT_FAMILY, LABEL_STYLES } from '../../config/globeConstants'
import { clearLabelTextureCache, createLabelTexture, measureLabel } from '../LabelRenderer'
import { fakeTextWidth, stubLabelCanvas } from './labelTestCanvas'

/** Every style key as (type, national) the way labels.json and the layers name them. */
const STYLE_INPUTS: Array<[string, string, boolean | undefined]> = Object.keys(LABEL_STYLES).map(key =>
  key === 'capitalNat' ? [key, 'capital', true] : [key, key, undefined],
)

const NAMES = ['Germany', 'Atlantic Ocean', 'Mérida', 'Kaliningrad', 'Sierra Nevada', 'São Tomé', 'Ōsaka', 'Rub al Khali']

/** The size today's drawing code gives, written out independently. */
function expectedSize(text: string, type: string, national: boolean | undefined) {
  const style = LABEL_STYLES[type === 'capital' && national ? 'capitalNat' : type]
  const fontSize = style.fontSize * 3
  const font = `${style.italic ? 'italic ' : ''}${style.bold ? '600 ' : '400 '}${fontSize}px ${ATLAS_FONT_FAMILY}`
  const multiplier = type === 'continent' || type === 'ocean' ? 3 : type === 'sea' || type === 'country' ? 2 : 1
  const spacing = Math.round(2 + (style.fontSize - 18) * 14 / 46) * multiplier
  const width = fakeTextWidth(font, `${spacing}px`, style.uppercase ? text.toUpperCase() : text)
  const padding = fontSize * 0.6
  return { width: Math.ceil(width + padding * 2), height: Math.ceil(fontSize * 1.4 + padding * 2) }
}

describe('measureLabel', () => {
  beforeEach(() => clearLabelTextureCache())
  afterEach(() => {
    clearLabelTextureCache()
    vi.unstubAllGlobals()
  })

  it.each(STYLE_INPUTS)('gives the size createLabelTexture draws for the %s style', (_key, type, national) => {
    stubLabelCanvas()
    for (const name of NAMES) {
      const measured = measureLabel(name, type, national)
      const { width, height, texture } = createLabelTexture(name, type, national)
      expect(measured).toEqual({ width, height })
      expect(measured).toEqual(expectedSize(name, type, national))
      expect([texture.image.width, texture.image.height]).toEqual([width, height])
    }
  })

  it('measures on one shared canvas and draws nothing', () => {
    const canvases = stubLabelCanvas()
    for (const [, type, national] of STYLE_INPUTS) {
      for (const name of NAMES) measureLabel(name, type, national)
    }
    expect(canvases).toHaveLength(1)
    expect(canvases[0].context.drawn).toEqual([])
  })

  it('draws the texture with the font, spacing and case it measured', () => {
    const canvases = stubLabelCanvas()
    createLabelTexture('Atlantic Ocean', 'ocean')
    const drawing = canvases.find(c => c.context.drawn.length > 0)!
    const fills = drawing.context.drawn.filter(([method]) => method === 'fill')
    expect(fills).toEqual([['fill', 'ATLANTIC OCEAN', `italic 400 174px ${ATLAS_FONT_FAMILY}`, '42px']])
  })
})
