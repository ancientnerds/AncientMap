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
import { GlobeStartError, LIVE_PHASE, failurePhase } from '../../utils/globeStartError'

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
  let live = false

  function Loader() {
    report = useStartErrorBridge(() => live)
    return <p>loading</p>
  }

  beforeEach(() => {
    report = null
    live = false
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
    live = true
    await act(async () => report!('coastlines', new Error('offline')))
    expect(onError).not.toHaveBeenCalled()
    expect(container.innerHTML).toBe('<p>loading</p>')
    expect(track).toHaveBeenCalledExactlyOnceWith('globe_error', { phase: LIVE_PHASE, message: 'coastlines: offline' })
  })

  it('keeps one identity across renders (loader contexts capture it once)', async () => {
    await render(<GlobeErrorBoundary onError={vi.fn()}><Loader /></GlobeErrorBoundary>)
    const first = report
    await act(async () => root!.render(<StrictMode><GlobeErrorBoundary onError={vi.fn()}><Loader /></GlobeErrorBoundary></StrictMode>))
    expect(report).toBe(first)
  })
})

describe('failurePhase', () => {
  it('is live once the globe was ready, whatever threw', () => {
    expect(failurePhase(new GlobeStartError('labels', 'x'), true)).toBe(LIVE_PHASE)
    expect(failurePhase(new Error('panel'), true)).toBe(LIVE_PHASE)
  })

  it('is the start step of a GlobeStartError, else start', () => {
    expect(failurePhase(new GlobeStartError('renderer', 'x'), false)).toBe('renderer')
    expect(failurePhase(new TypeError('x'), false)).toBe('start')
  })

  it('live is the literal the dashboard excludes', () => {
    expect(LIVE_PHASE).toBe('live')
  })
})
