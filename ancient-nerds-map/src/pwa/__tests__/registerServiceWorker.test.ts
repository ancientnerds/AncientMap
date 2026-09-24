/**
 * Service-worker registration for globe.html, run late by the globe's
 * background queue instead of the inline snippet on window 'load' (whose
 * precache of ~6.9 MB competed with the globe's critical load).
 * Same semantics as the snippet (serviceWorkerSnippet.ts SW_INSTALL): only where
 * `serviceWorker` exists, not before 'load', `/sw.js` with scope `/`. A
 * refusal rejects, so the caller (the queue) reports it; nothing is swallowed.
 * Node environment: navigator/document/window are stubbed per test (Node 20
 * has no global navigator).
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

function stubPage(opts: { readyState: DocumentReadyState; register?: ReturnType<typeof vi.fn> | null }) {
  const listeners = new Map<string, Array<() => void>>()
  const navigatorStub = opts.register === null ? {} : { serviceWorker: { register: opts.register } }
  vi.stubGlobal('navigator', navigatorStub)
  vi.stubGlobal('document', { readyState: opts.readyState })
  vi.stubGlobal('window', {
    addEventListener: (type: string, cb: () => void) => {
      listeners.set(type, [...(listeners.get(type) ?? []), cb])
    },
  })
  return {
    fire: (type: string) => {
      for (const cb of listeners.get(type) ?? []) cb()
    },
    listenerCount: (type: string) => listeners.get(type)?.length ?? 0,
  }
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('registerServiceWorker', () => {
  it('touches no browser global when imported (SSR-safe module scope)', async () => {
    vi.stubGlobal('navigator', undefined)
    vi.stubGlobal('document', undefined)
    vi.stubGlobal('window', undefined)
    const mod = await import('../registerServiceWorker')
    expect(typeof mod.registerServiceWorker).toBe('function')
  })

  it('registers /sw.js with scope / once the page has loaded', async () => {
    const register = vi.fn().mockResolvedValue({})
    stubPage({ readyState: 'complete', register })
    const { registerServiceWorker } = await import('../registerServiceWorker')
    await expect(registerServiceWorker()).resolves.toBe(true)
    expect(register).toHaveBeenCalledTimes(1)
    expect(register).toHaveBeenCalledWith('/sw.js', { scope: '/' })
  })

  it('waits for window load before registering', async () => {
    const register = vi.fn().mockResolvedValue({})
    const page = stubPage({ readyState: 'interactive', register })
    const { registerServiceWorker } = await import('../registerServiceWorker')
    const done = registerServiceWorker()
    await flush()
    expect(register).not.toHaveBeenCalled()
    expect(page.listenerCount('load')).toBe(1)
    page.fire('load')
    await done
    expect(register).toHaveBeenCalledWith('/sw.js', { scope: '/' })
  })

  it('does nothing where the browser has no service workers', async () => {
    stubPage({ readyState: 'complete', register: null })
    const { registerServiceWorker } = await import('../registerServiceWorker')
    await expect(registerServiceWorker()).resolves.toBe(false)
  })

  it('rejects with the refusal so the caller reports it', async () => {
    const refusal = new Error('Failed to register a ServiceWorker: The operation is insecure.')
    stubPage({ readyState: 'complete', register: vi.fn().mockRejectedValue(refusal) })
    const { registerServiceWorker } = await import('../registerServiceWorker')
    await expect(registerServiceWorker()).rejects.toBe(refusal)
  })
})

/** A worker that moves through its states when the test says so. */
function fakeWorker(state: ServiceWorkerState) {
  const listeners = new Set<() => void>()
  const worker = {
    state,
    addEventListener: (_type: string, cb: () => void) => { listeners.add(cb) },
    removeEventListener: (_type: string, cb: () => void) => { listeners.delete(cb) },
  }
  return {
    worker,
    listeners,
    move(next: ServiceWorkerState) {
      worker.state = next
      for (const cb of [...listeners]) cb()
    },
  }
}

describe('ensureServiceWorkerActive (before an offline download)', () => {
  it('resolves at once when a worker is active', async () => {
    const register = vi.fn().mockResolvedValue({ active: {}, installing: null, waiting: null })
    stubPage({ readyState: 'complete', register })
    const { ensureServiceWorkerActive } = await import('../registerServiceWorker')
    await expect(ensureServiceWorkerActive()).resolves.toBeUndefined()
    expect(register).toHaveBeenCalledWith('/sw.js', { scope: '/' })
  })

  it('waits until the first worker has installed (its precache) and activated', async () => {
    const w = fakeWorker('installing')
    stubPage({ readyState: 'complete', register: vi.fn().mockResolvedValue({ active: null, installing: w.worker, waiting: null }) })
    const { ensureServiceWorkerActive } = await import('../registerServiceWorker')
    let done = false
    const ensured = ensureServiceWorkerActive().then(() => { done = true })
    await flush()
    w.move('installed')
    w.move('activating')
    await flush()
    expect(done).toBe(false)
    w.move('activated')
    await ensured
    expect(done).toBe(true)
    expect(w.listeners.size).toBe(0)
  })

  it('rejects when the install fails (the worker turns redundant)', async () => {
    const w = fakeWorker('installing')
    stubPage({ readyState: 'complete', register: vi.fn().mockResolvedValue({ active: null, installing: w.worker, waiting: null }) })
    const { ensureServiceWorkerActive } = await import('../registerServiceWorker')
    const ensured = ensureServiceWorkerActive()
    await flush()
    w.move('redundant')
    await expect(ensured).rejects.toThrow('the service worker could not install')
  })

  it('rejects where the browser has no service workers', async () => {
    stubPage({ readyState: 'complete', register: null })
    const { ensureServiceWorkerActive } = await import('../registerServiceWorker')
    await expect(ensureServiceWorkerActive()).rejects.toThrow('this browser has no service workers')
  })

  it('rejects with a refusal', async () => {
    const refusal = new Error('Failed to register a ServiceWorker: The operation is insecure.')
    stubPage({ readyState: 'complete', register: vi.fn().mockRejectedValue(refusal) })
    const { ensureServiceWorkerActive } = await import('../registerServiceWorker')
    await expect(ensureServiceWorkerActive()).rejects.toBe(refusal)
  })
})
