import { afterEach, describe, expect, it, vi } from 'vitest'

import { _resetForTests, MAX_VALUE_CHARS } from '../index'
import { trackBackgroundFailure } from '../globeBackground'

const g = globalThis as unknown as { window?: unknown }

afterEach(() => {
  _resetForTests()
  delete g.window
  vi.restoreAllMocks()
})

describe('trackBackgroundFailure', () => {
  it('logs the failure with its task and sends globe_error with a bg: phase', () => {
    const spy = vi.fn()
    g.window = { umami: { track: spy } }
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const err = new Error('basemap /data/basemaps/satellite_low.webp: HTTP 404')
    trackBackgroundFailure('satellite', err)
    expect(log).toHaveBeenCalledWith('[globe bg] satellite', err)
    expect(spy).toHaveBeenCalledWith('globe_error', {
      phase: 'bg:satellite',
      message: 'basemap /data/basemaps/satellite_low.webp: HTTP 404',
    })
  })

  it('clips the message and accepts non-Error rejections', () => {
    const spy = vi.fn()
    g.window = { umami: { track: spy } }
    vi.spyOn(console, 'error').mockImplementation(() => {})
    trackBackgroundFailure('basemap', 'x'.repeat(300))
    const props = spy.mock.calls[0][1] as { phase: string; message: string }
    expect(props.phase).toBe('bg:basemap')
    expect(props.message).toHaveLength(MAX_VALUE_CHARS)
  })
})
