/**
 * @vitest-environment jsdom
 *
 * The globe's error boundary and the bridge that brings asynchronous start
 * failures to it. Without them a failed start unmounts the whole page (the
 * black screen with only the footer, spec §1.3); a boundary alone sees render
 * and effect errors only, never a rejected fetch or a shader error in rAF.
 */

import { StrictMode, act, useEffect } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// boot.ts (errorProps) boots the page analytics on import and needs the real helpers
vi.mock('../../analytics', async importOriginal => ({
  ...(await importOriginal<typeof import('../../analytics')>()),
  track: vi.fn(),
}))

import { track } from '../../analytics'
import GlobeErrorBoundary, { useStartErrorBridge, type ReportStartError } from '../GlobeErrorBoundary'
import { GlobeStartError, LIVE_PHASE, boundaryFailure } from '../../utils/globeStartError'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null
let container: HTMLDivElement

async function render(node: React.ReactNode): Promise<void> {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(<StrictMode>{node}</StrictMode>)
  })
}

// React's development build replays a caught error as a window error event;
// jsdom prints those unless a listener cancels them
const quiet = (e: ErrorEvent) => e.preventDefault()

beforeEach(() => {
  vi.mocked(track).mockClear()
  // React logs every caught error; the expected ones would bury real output
  vi.spyOn(console, 'error').mockImplementation(() => {})
  window.addEventListener('error', quiet)
})

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
  container.remove()
  window.removeEventListener('error', quiet)
  vi.restoreAllMocks()
})

function ThrowInRender(): never {
  throw new Error('render broke')
}

function ThrowInEffect() {
  useEffect(() => {
    throw new GlobeStartError('renderer', new Error('Error creating WebGL context.'))
  }, [])
  return <p>scene</p>
}

describe('GlobeErrorBoundary', () => {
  it('catches a render throw, hands it over and renders nothing', async () => {
    const onError = vi.fn()
    await render(<GlobeErrorBoundary onError={onError}><ThrowInRender /></GlobeErrorBoundary>)
    expect(onError).toHaveBeenCalled()
    expect((onError.mock.calls[0][0] as Error).message).toBe('render broke')
    expect(container.innerHTML).toBe('')
  })

  it('catches a throw in an effect (the WebGLRenderer constructor runs in one)', async () => {
    const onError = vi.fn()
    await render(<GlobeErrorBoundary onError={onError}><ThrowInEffect /></GlobeErrorBoundary>)
    const err = onError.mock.calls[0][0]
    expect(err).toBeInstanceOf(GlobeStartError)
    expect((err as GlobeStartError).phase).toBe('renderer')
    expect(container.innerHTML).toBe('')
  })

  it('renders its children while nothing failed', async () => {
    await render(<GlobeErrorBoundary onError={vi.fn()}><p>globe</p></GlobeErrorBoundary>)
    expect(container.innerHTML).toBe('<p>globe</p>')
  })
})

describe('useStartErrorBridge', () => {
  let report: ReportStartError | null = null
  // App's globe_ready (page-wide, never reset) and this Globe instance's layers
  let appReady = false
  const layersUp = { current: false }

  function Loader() {
    report = useStartErrorBridge(() => appReady, layersUp)
    return <p>loading</p>
  }

  beforeEach(() => {
    report = null
    appReady = false
    layersUp.current = false
  })

  it('brings an asynchronous failure to the boundary, with its phase; the first one wins', async () => {
    const onError = vi.fn()
    await render(<GlobeErrorBoundary onError={onError}><Loader /></GlobeErrorBoundary>)
    expect(onError).not.toHaveBeenCalled()
    const cause = new Error('/data/labels.json: HTTP 404')
    await act(async () => {
      await Promise.reject(cause).catch((err: unknown) => {
        report!('labels', err)
        report!('basemap', new Error('later'))
      })
    })
    expect(onError).toHaveBeenCalledOnce()
    const err = onError.mock.calls[0][0] as GlobeStartError
    expect(err).toBeInstanceOf(GlobeStartError)
    expect(err.phase).toBe('labels')
    expect(err.message).toBe('/data/labels.json: HTTP 404')
    expect(err.cause).toBe(cause)
    expect(container.innerHTML).toBe('')
    expect(track).not.toHaveBeenCalled() // App reports what the boundary hands over
  })

  it('once the globe is ready it tracks the failure as live and tears nothing down', async () => {
    const onError = vi.fn()
    await render(<GlobeErrorBoundary onError={onError}><Loader /></GlobeErrorBoundary>)
    appReady = true
    layersUp.current = true
    await act(async () => report!('coastlines', new Error('offline')))
    expect(onError).not.toHaveBeenCalled()
    expect(container.innerHTML).toBe('<p>loading</p>')
    expect(track).toHaveBeenCalledExactlyOnceWith('globe_error', { phase: LIVE_PHASE, message: 'coastlines: offline' })
  })

  it('between the layers and the sites a failure is still a start failure', async () => {
    const onError = vi.fn()
    await render(<GlobeErrorBoundary onError={onError}><Loader /></GlobeErrorBoundary>)
    layersUp.current = true
    await act(async () => report!('labels', new Error('HTTP 503')))
    expect(onError).toHaveBeenCalledOnce()
    expect(track).not.toHaveBeenCalled()
  })

  it('a remounted Globe (resized through the phone gate) reports its start failures to the boundary', async () => {
    // App's globe_ready fired for the first Globe and stays true; this instance's layers are not up
    const onError = vi.fn()
    appReady = true
    await render(<GlobeErrorBoundary onError={onError}><Loader /></GlobeErrorBoundary>)
    await act(async () => report!('basemap', new Error('HTTP 502')))
    expect(onError).toHaveBeenCalledOnce()
    expect((onError.mock.calls[0][0] as GlobeStartError).phase).toBe('basemap')
    expect(container.innerHTML).toBe('')
    expect(track).not.toHaveBeenCalled()
  })

  it('keeps one identity across renders (loader contexts capture it once)', async () => {
    await render(<GlobeErrorBoundary onError={vi.fn()}><Loader /></GlobeErrorBoundary>)
    const first = report
    await act(async () => root!.render(<StrictMode><GlobeErrorBoundary onError={vi.fn()}><Loader /></GlobeErrorBoundary></StrictMode>))
    expect(report).toBe(first)
  })
})

describe('boundaryFailure', () => {
  it('is live once the globe was ready, whatever threw', () => {
    expect(boundaryFailure(new GlobeStartError('labels', 'x'), true).phase).toBe(LIVE_PHASE)
    expect(boundaryFailure(new Error('panel'), true).phase).toBe(LIVE_PHASE)
  })

  it('is the start step of a GlobeStartError with its cause, else start with the error', () => {
    const cause = new Error('HTTP 502')
    expect(boundaryFailure(new GlobeStartError('renderer', cause), false)).toEqual({ phase: 'renderer', error: cause })
    const other = new TypeError('x')
    expect(boundaryFailure(other, false)).toEqual({ phase: 'start', error: other })
    expect(boundaryFailure(other, true)).toEqual({ phase: LIVE_PHASE, error: other })
  })

  it("keeps a remounted Globe's step in a live failure's message, as the bridge's own live path does", () => {
    // App's globe_ready fired for the first Globe; the one mounted after the phone gate fails its basemap
    const { phase, error } = boundaryFailure(new GlobeStartError('basemap', new Error('HTTP 502')), true)
    expect(phase).toBe(LIVE_PHASE)
    expect((error as Error).message).toBe('basemap: HTTP 502')
  })

  it('live is the literal the dashboard excludes', () => {
    expect(LIVE_PHASE).toBe('live')
  })
})
