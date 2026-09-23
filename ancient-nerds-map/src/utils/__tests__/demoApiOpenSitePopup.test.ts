/**
 * The demo API opens popups straight from App's bulk site list. The globe
 * starts without the sites' detail fields, so it has to wait for them (like
 * App's own bulk-data popup path) instead of opening a popup without its
 * description; the popup never fills in later (useAdminMode syncs on id only).
 *
 * @vitest-environment jsdom
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SiteData } from '../../data/sites'

const { withSiteDetails } = vi.hoisted(() => ({ withSiteDetails: vi.fn() }))
vi.mock('../../data/sites', () => ({ withSiteDetails }))

import { registerAppDemoApi, type AppDemoSetters } from '../demoApi'

const ALPHA: SiteData = {
  id: 'a',
  title: 'Alpha Temple',
  location: 'Greece',
  category: 'Temple',
  period: 'Iron Age',
  periodStart: -500,
  description: '',
  sourceId: 'ancient_nerds',
  coordinates: [20, 10],
}

function setters(openSitePopup: (site: SiteData) => void): AppDemoSetters {
  const noop = () => {}
  return {
    setFilterMode: noop,
    setAgeRange: noop,
    setFlyToCoords: noop,
    setDemoMode: noop,
    setSelectedSources: noop,
    handleLoadSources: noop,
    openSitePopup,
    closeAllPopups: noop,
    sitesRef: { current: [ALPHA] },
  }
}

beforeEach(() => {
  window.history.replaceState({}, '', '/globe.html?demo=1')
  withSiteDetails.mockReset()
})

afterEach(() => {
  delete (window as { __DEMO?: unknown }).__DEMO
})

describe('__DEMO.openSitePopup', () => {
  it('opens the site once its detail fields are in', async () => {
    const detailed = { ...ALPHA, description: 'On a hill' }
    let release: (site: SiteData) => void = () => {}
    withSiteDetails.mockReturnValue(new Promise<SiteData>(resolve => { release = resolve }))
    const open = vi.fn()
    registerAppDemoApi(setters(open))

    const opening = window.__DEMO!.openSitePopup!('alpha')
    await Promise.resolve()
    expect(withSiteDetails).toHaveBeenCalledWith(ALPHA)
    expect(open).not.toHaveBeenCalled()

    release(detailed)
    await opening
    expect(open).toHaveBeenCalledWith(detailed)
  })

  it('rejects when the details failed to load, without opening', async () => {
    withSiteDetails.mockRejectedValue(new Error('Failed to load site details: HTTP 503'))
    const open = vi.fn()
    registerAppDemoApi(setters(open))

    await expect(window.__DEMO!.openSitePopup!('alpha')).rejects.toThrow('HTTP 503')
    expect(open).not.toHaveBeenCalled()
  })
})
