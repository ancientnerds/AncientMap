import { describe, expect, it } from 'vitest'

import { cameraAt, coverScale, focusCamera, fractionBox, kenBurnsCamera, rectToScreen, toScreen, viewFor } from '../src/layout/transform'

describe('cover fit and camera view', () => {
  it('cover-fits a 4:3 image into 16:9 by width', () => {
    expect(coverScale(1600, 1200, 1920, 1080)).toBeCloseTo(1.2)
  })
  it('centres the camera point on screen when the image allows it', () => {
    const v = viewFor(4000, 3000, 1920, 1080, { cx: 2000, cy: 1500, zoom: 2 })
    const c = toScreen(v, 2000, 1500)
    expect(c.x).toBeCloseTo(960)
    expect(c.y).toBeCloseTo(540)
  })
  it('clamps at the image edge so no background ever shows', () => {
    const v = viewFor(1600, 1200, 1920, 1080, { cx: 0, cy: 0, zoom: 1 })
    expect(v.tx).toBe(0)
    expect(v.ty).toBe(0)
    const far = viewFor(1600, 1200, 1920, 1080, { cx: 1600, cy: 1200, zoom: 1 })
    expect(far.tx).toBeCloseTo(1920 - 1600 * far.scale)
    expect(far.ty).toBeCloseTo(1080 - 1200 * far.scale)
  })
})

describe('markers move with the image', () => {
  it('turns case-file fraction boxes into image pixels', () => {
    expect(fractionBox([0.1, 0.5, 0.1, 0.3], 1600, 1200)).toEqual([160, 600, 160, 360])
  })
  it('maps a marker box through the same view as the image pixels it covers', () => {
    const box = [1000, 700, 120, 240] as const
    for (const cam of [{ cx: 800, cy: 600, zoom: 1 }, { cx: 1060, cy: 820, zoom: 3 }]) {
      const v = viewFor(1600, 1200, 1920, 1080, cam)
      const r = rectToScreen(v, box)
      const tl = toScreen(v, box[0], box[1])
      const br = toScreen(v, box[0] + box[2], box[1] + box[3])
      expect(r.x).toBeCloseTo(tl.x)
      expect(r.y).toBeCloseTo(tl.y)
      expect(r.x + r.w).toBeCloseTo(br.x)
      expect(r.y + r.h).toBeCloseTo(br.y)
    }
  })
  it('keeps the focused marker centred and large', () => {
    const box = [1000, 700, 120, 240] as const
    const r = rectToScreen(viewFor(1600, 1200, 1920, 1080, focusCamera(1600, 1200, 1920, 1080, box)), box)
    expect(r.x + r.w / 2).toBeCloseTo(960, 0)
    expect(r.y + r.h / 2).toBeCloseTo(540, 0)
    expect(r.h / 1080).toBeCloseTo(0.45, 2)
  })
})

describe('camera paths', () => {
  it('holds the ends and eases between keys, zoom in log space', () => {
    const keys = [
      { at: 0, cx: 0, cy: 0, zoom: 1 },
      { at: 1, cx: 100, cy: 50, zoom: 4 },
    ]
    expect(cameraAt(keys, -1)).toEqual({ cx: 0, cy: 0, zoom: 1 })
    expect(cameraAt(keys, 2)).toEqual({ cx: 100, cy: 50, zoom: 4 })
    const mid = cameraAt(keys, 0.5)
    expect(mid.cx).toBeCloseTo(50)
    expect(mid.zoom).toBeCloseTo(2)
    expect(() => cameraAt([], 0.5)).toThrow(/no keyframes/)
  })
  it('pushes in, pulls out or holds still on the image centre', () => {
    expect(kenBurnsCamera(1000, 800, 'in')).toEqual([
      { at: 0, cx: 500, cy: 400, zoom: 1 },
      { at: 1, cx: 500, cy: 400, zoom: 1.08 },
    ])
    expect(kenBurnsCamera(1000, 800, 'out')[0].zoom).toBe(1.08)
    expect(kenBurnsCamera(1000, 800, 'none')).toEqual([{ at: 0, cx: 500, cy: 400, zoom: 1 }])
  })
})
