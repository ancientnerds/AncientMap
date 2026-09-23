/**
 * labels.json is part of the globe's start (globe_ready waits for the labels).
 * A failed answer must fail the load with the URL and status - Globe reports
 * it as the start error 'labels' - instead of parsing an error page and
 * leaving the loading screen up for ever.
 */

import * as THREE from 'three'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { loadGeoLabels, type GeoLabelContext } from '../geoLabelSystem'

afterEach(() => vi.unstubAllGlobals())

describe('loadGeoLabels', () => {
  it('rejects on an HTTP error with the URL and status, and marks nothing loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>502</html>', { status: 502 })))
    const setLabelsLoaded = vi.fn()
    const ctx = {
      sceneRef: { current: { scene: new THREE.Scene() } },
      labelsLoadedRef: { current: false },
      setLabelsLoaded,
    } as unknown as GeoLabelContext
    await expect(loadGeoLabels(ctx)).rejects.toThrow('/data/labels.json: HTTP 502')
    expect(ctx.labelsLoadedRef.current).toBe(false)
    expect(setLabelsLoaded).not.toHaveBeenCalled()
  })
})
