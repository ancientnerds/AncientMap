/**
 * An admin save changes a site, so every service-worker cache that can hold
 * that site's /api/sites/ answer must be emptied, or the next visit serves the
 * old data (NetworkFirst's timeout/offline path). The caches are listed once,
 * next to the rules that fill them (src/pwa/runtimeCaching.ts).
 *
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SiteData } from '../../../../data/sites'
import { API_SITES_CACHE_NAMES } from '../../../../pwa/runtimeCaching'
import { useAdminMode } from '../useAdminMode'

// React only flushes effects inside act() when this flag is set.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const SITE = { id: 'site-1', title: 'Giza', coordinates: [31.13, 29.98] } as unknown as SiteData

type Hook = ReturnType<typeof useAdminMode>

describe('useAdminMode', () => {
  let container: HTMLDivElement
  let root: Root
  let hook: Hook | null
  const opened: string[] = []
  const deleted: string[] = []

  function Probe() {
    hook = useAdminMode({ site: SITE, authToken: 'token' })
    return null
  }

  beforeEach(() => {
    opened.length = 0
    deleted.length = 0
    hook = null
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })))
    vi.stubGlobal('caches', {
      open: vi.fn(async (name: string) => {
        opened.push(name)
        return {
          keys: async () => [new Request(`https://ancientnerds.com/${name}/entry`)],
          delete: async (request: Request) => {
            deleted.push(request.url)
            return true
          },
        }
      }),
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.unstubAllGlobals()
  })

  it('empties every api/sites service-worker cache after a successful save', async () => {
    act(() => root.render(<Probe />))
    act(() => hook!.enterAdminMode())
    await act(async () => {
      await hook!.handleSave()
    })

    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/sites/site-1'), expect.objectContaining({ method: 'PUT' }))
    expect([...opened].sort()).toEqual([...API_SITES_CACHE_NAMES].sort())
    expect(deleted.sort()).toEqual(API_SITES_CACHE_NAMES.map(name => `https://ancientnerds.com/${name}/entry`).sort())
    expect(hook!.saveError).toBeNull()
  })
})
