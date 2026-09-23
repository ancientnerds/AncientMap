/**
 * The capability check before the globe mounts: a throw-away canvas must give
 * a WebGL 2 context with the renderer's own attributes (three r182 asks for
 * nothing else) and a texture limit the smallest basemap fits into. The probe
 * context is released at once; browsers cap live WebGL contexts.
 */

import { describe, expect, it, vi } from 'vitest'

import { RENDERER_ATTRIBUTES } from '../../config/globeConstants'
import { MIN_BASEMAP_TEXTURE_SIZE } from '../deviceTier'
import { checkGlobeSupport } from '../globeSupport'

const MAX_TEXTURE_SIZE = 0x0d33

function fakeCanvas(opts: { gl: boolean; maxTexture?: number; creationError?: string }) {
  const loseContext = vi.fn()
  const listeners: Record<string, (e: Event) => void> = {}
  const getContext = vi.fn((kind: string) => {
    if (kind !== 'webgl2') throw new Error(`asked for ${kind}`)
    if (!opts.gl) {
      if (opts.creationError !== undefined) {
        listeners.webglcontextcreationerror?.({ statusMessage: opts.creationError } as unknown as Event)
      }
      return null
    }
    return {
      MAX_TEXTURE_SIZE,
      getParameter: (p: number) => (p === MAX_TEXTURE_SIZE ? opts.maxTexture : undefined),
      getExtension: (name: string) => (name === 'WEBGL_lose_context' ? { loseContext } : null),
    }
  })
  const canvas = {
    getContext,
    addEventListener: (type: string, fn: (e: Event) => void) => { listeners[type] = fn },
    removeEventListener: (type: string) => { delete listeners[type] },
  } as unknown as HTMLCanvasElement
  return { canvas, getContext, loseContext }
}

describe('checkGlobeSupport', () => {
  it('asks for webgl2 with the renderer attributes', () => {
    const { canvas, getContext } = fakeCanvas({ gl: true, maxTexture: 16384 })
    checkGlobeSupport(canvas)
    expect(getContext).toHaveBeenCalledExactlyOnceWith('webgl2', RENDERER_ATTRIBUTES)
  })

  it('reports no_webgl2 when there is no WebGL 2 context', () => {
    const { canvas } = fakeCanvas({ gl: false })
    expect(checkGlobeSupport(canvas)).toEqual({ ok: false, reason: 'no_webgl2', detail: undefined })
  })

  it('passes the browser status message on as the detail', () => {
    const { canvas } = fakeCanvas({ gl: false, creationError: 'Web page caused context loss and was blocked' })
    expect(checkGlobeSupport(canvas)).toEqual({
      ok: false,
      reason: 'no_webgl2',
      detail: 'Web page caused context loss and was blocked',
    })
  })

  it('reports max_texture_size below the smallest basemap and releases the context', () => {
    const { canvas, loseContext } = fakeCanvas({ gl: true, maxTexture: 2048 })
    expect(checkGlobeSupport(canvas)).toEqual({ ok: false, reason: 'max_texture_size', detail: '2048' })
    expect(loseContext).toHaveBeenCalledOnce()
  })

  it('passes at exactly the smallest basemap and releases the probe context', () => {
    const { canvas, loseContext } = fakeCanvas({ gl: true, maxTexture: MIN_BASEMAP_TEXTURE_SIZE })
    expect(checkGlobeSupport(canvas)).toEqual({ ok: true })
    expect(loseContext).toHaveBeenCalledOnce()
  })
})
