/**
 * The auto-switch reads the Mapbox load state as React state, so reaching
 * `ready` while the camera is parked at the switch distance switches at once
 * (before, readiness sat in a ref outside the effect deps and never re-ran it).
 */

import { describe, expect, it, vi } from 'vitest'

import { type AutoSwitchEffectDeps, createAutoSwitchEffect } from '../mapboxEffects'
import type { MapboxLoadState } from '../../../../services/mapboxLoader'

function deps(mapboxState: MapboxLoadState, zoom: number, showMapbox: boolean, offline = false) {
  const d: AutoSwitchEffectDeps = {
    zoom,
    showMapbox,
    mapboxState,
    setShowMapbox: vi.fn(),
    justEnteredMapbox: { current: false },
    contextIsOffline: offline,
    hasMapboxTilesCached: false,
    setShowMapboxOfflineWarning: vi.fn(),
  }
  return d
}

describe('createAutoSwitchEffect', () => {
  it('does not switch at 66 while Mapbox is still loading', () => {
    const d = deps('loading', 66, false)
    createAutoSwitchEffect(d)
    expect(d.setShowMapbox).not.toHaveBeenCalled()
    expect(d.justEnteredMapbox.current).toBe(false)
  })

  it('does not switch when Mapbox failed', () => {
    const d = deps('failed', 66, false)
    createAutoSwitchEffect(d)
    expect(d.setShowMapbox).not.toHaveBeenCalled()
  })

  it('switches to Mapbox at 66 once ready', () => {
    const d = deps('ready', 66, false)
    createAutoSwitchEffect(d)
    expect(d.justEnteredMapbox.current).toBe(true)
    expect(d.setShowMapbox).toHaveBeenCalledExactlyOnceWith(true)
    expect(d.setShowMapboxOfflineWarning).not.toHaveBeenCalled()
  })

  it('switches back below 66 and hides the offline warning', () => {
    const d = deps('ready', 65, true)
    createAutoSwitchEffect(d)
    expect(d.setShowMapbox).toHaveBeenCalledExactlyOnceWith(false)
    expect(d.setShowMapboxOfflineWarning).toHaveBeenCalledExactlyOnceWith(false)
  })

  it('shows the offline warning when entering Mapbox offline without the cached satellite texture', () => {
    const d = deps('ready', 66, false, true)
    createAutoSwitchEffect(d)
    expect(d.setShowMapbox).toHaveBeenCalledExactlyOnceWith(true)
    expect(d.setShowMapboxOfflineWarning).toHaveBeenCalledExactlyOnceWith(true)
  })
})
