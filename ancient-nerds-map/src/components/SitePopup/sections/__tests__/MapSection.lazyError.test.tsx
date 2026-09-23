/**
 * EmpireMinimap is a lazy chunk (it pulls mapbox-gl, 463 kB gzip, which must
 * stay out of the globe and site entries). When that chunk fails to load,
 * React.lazy throws during render. SitePopup sits under no error boundary in
 * App, so without one around the minimap the failure would unmount the whole
 * globe app. The section must show the boundary's notice instead and keep
 * rendering the rest of the popup.
 *
 * @vitest-environment jsdom
 */

import { act, createRef } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const trackMock = vi.hoisted(() => vi.fn())

vi.mock('../../../EmpireMinimap', () => {
  throw new Error('Failed to fetch dynamically imported module')
})
vi.mock('../../../../analytics', () => ({ track: trackMock }))

import { MapSection } from '../MapSection'

// React only flushes effects inside act() when this flag is set.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null
let container: HTMLDivElement | null = null

// React's dev build rethrows a caught render error inside a synthetic event
// before the boundary takes it; jsdom would print it to stderr.
const swallowReportedError = (e: ErrorEvent) => e.preventDefault()

beforeEach(() => {
  // React logs every error a boundary catches.
  vi.spyOn(console, 'error').mockImplementation(() => {})
  window.addEventListener('error', swallowReportedError)
  trackMock.mockClear()
})

afterEach(() => {
  act(() => root?.unmount())
  root = null
  container?.remove()
  container = null
  window.removeEventListener('error', swallowReportedError)
  vi.restoreAllMocks()
})

describe('MapSection in empire mode when the EmpireMinimap chunk fails', () => {
  it("renders the boundary's notice instead of throwing out of the popup", async () => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)

    await act(async () => {
      root!.render(
        <MapSection
          lat={0}
          lng={0}
          isWaterLocation={false}
          isEmpireMode
          empire={{ id: 'roman', name: 'Roman Empire', region: 'Europe', color: 0xff0000, peakYear: 117 }}
          empireYear={117}
          googleMapsLoaded={false}
          googleMapsError={false}
          showStreetView={false}
          isMapFullscreen={false}
          shareSuccess={false}
          onGoogleMapsLoad={() => {}}
          onGoogleMapsError={() => {}}
          onStreetViewToggle={() => {}}
          onFullscreenToggle={() => {}}
          onShareGoogleMaps={() => {}}
          mapSectionRef={createRef<HTMLDivElement>()}
        />,
      )
    })
    // Let the rejected lazy import settle and React retry the render.
    for (let i = 0; i < 20 && !trackMock.mock.calls.length && container.querySelector('.empire-minimap-section'); i++) {
      await act(async () => { await new Promise(r => setTimeout(r, 10)) })
    }

    const section = container.querySelector('.empire-minimap-section')
    expect(section).not.toBeNull()
    expect(section!.textContent).toContain('Failed to load. Please refresh the page.')
    expect(trackMock).toHaveBeenCalledWith('js_error', expect.objectContaining({ source: 'boundary' }))
  })
})
