/**
 * MapboxGlobeService.initialize must settle. Before, an 'error' before the
 * first 'load' (style fetch failed, 401/403, offline) was only logged and the
 * promise stayed pending forever, so the load state could never become
 * `failed` and the background queue behind it never ran on.
 *
 * mapbox-gl fires style-level errors from the Style itself (no `sourceId`);
 * errors of a tile or a TileJSON request are forwarded from the source with
 * `sourceId` set (Style#addSource → setEventedParent(this, {sourceId}) in
 * mapbox-gl 3.18). Only the former are fatal before 'load'.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const fake = vi.hoisted(() => {
  type Handler = (e?: unknown) => void
  const maps: FakeMap[] = []
  class FakeMap {
    handlers = new Map<string, Handler[]>()
    options: unknown
    constructor(options: unknown) {
      this.options = options
      maps.push(this)
    }
    on(event: string, handler: Handler) {
      this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler])
      return this
    }
    fire(event: string, payload?: unknown) {
      for (const h of this.handlers.get(event) ?? []) h(payload)
    }
    getLayer() { return undefined }
    getSource() { return undefined }
    remove() {}
  }
  return { maps, FakeMap }
})

vi.mock('mapbox-gl', () => ({ default: { accessToken: '', Map: fake.FakeMap } }))
vi.mock('mapbox-gl/dist/mapbox-gl.css', () => ({}))
vi.mock('../../utils/mapboxTheme', () => ({
  applyDarkTealTheme: vi.fn(),
  setupDarkFog: vi.fn(),
  hexToRgba: vi.fn(),
}))

import { MapboxGlobeService } from '../MapboxGlobeService'

beforeEach(() => {
  fake.maps.length = 0
  vi.stubGlobal('window', { location: { search: '' } })
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function flush() {
  await new Promise(r => setTimeout(r, 0))
}

describe('MapboxGlobeService.initialize', () => {
  it("resolves on 'load' and reports itself initialised", async () => {
    const service = new MapboxGlobeService()
    const init = service.initialize({} as HTMLDivElement, 'dark')
    expect(service.getIsInitialized()).toBe(false)

    fake.maps[0].fire('load')

    await expect(init).resolves.toBeUndefined()
    expect(service.getIsInitialized()).toBe(true)
  })

  it("rejects on a style-level 'error' before 'load'", async () => {
    const service = new MapboxGlobeService()
    const init = service.initialize({} as HTMLDivElement, 'dark')
    const cause = Object.assign(new Error('Unauthorized'), { status: 401 })

    fake.maps[0].fire('error', { type: 'error', error: cause, style: {} })

    await expect(init).rejects.toBe(cause)
    expect(service.getIsInitialized()).toBe(false)
  })

  it("does not reject on a tile or source error (it carries sourceId)", async () => {
    const service = new MapboxGlobeService()
    const init = service.initialize({} as HTMLDivElement, 'dark')
    let settled = false
    init.then(() => { settled = true }, () => { settled = true })

    fake.maps[0].fire('error', { type: 'error', error: new Error('tile 503'), sourceId: 'composite', tile: {} })
    await flush()
    expect(settled).toBe(false)

    fake.maps[0].fire('load')
    await expect(init).resolves.toBeUndefined()
  })

  it("keeps a later 'error' after 'load' non-fatal", async () => {
    const service = new MapboxGlobeService()
    const init = service.initialize({} as HTMLDivElement, 'dark')
    fake.maps[0].fire('load')
    await init

    fake.maps[0].fire('error', { type: 'error', error: new Error('late') })
    expect(service.getIsInitialized()).toBe(true)
  })
})
