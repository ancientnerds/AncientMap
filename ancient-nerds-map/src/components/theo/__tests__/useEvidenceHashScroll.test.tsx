/**
 * A #ev-NN or #corrections deep link re-scrolls to its target once the images
 * above it have settled (loaded or failed). Images below the target do not
 * hold it back, the reader taking over (wheel, touch, pointer, key, an in-page
 * hash change) drops it, a reload or history step skips it, and nothing
 * happens for any other hash.
 *
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { useEvidenceHashScroll } from '../useEvidenceHashScroll'

// React only flushes effects inside act() when this flag is set.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function Probe() {
  useEvidenceHashScroll()
  return null
}

let root: Root | null = null
let scrolled: string[] = []

/** jsdom never fetches images: say explicitly whether each one is still loading. */
function setComplete(img: HTMLImageElement, complete: boolean): void {
  Object.defineProperty(img, 'complete', { configurable: true, value: complete })
}

/** jsdom has no navigation entry: hand the hook the navigation type a browser would. */
function setNavigationType(type: NavigationTimingType): void {
  vi.spyOn(performance, 'getEntriesByType').mockImplementation(entryType =>
    entryType === 'navigation' ? [{ type } as PerformanceNavigationTiming] : [],
  )
}

function image(id: string): HTMLImageElement {
  return document.getElementById(id) as HTMLImageElement
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

async function mount(): Promise<void> {
  root = createRoot(document.getElementById('mount')!)
  await act(async () => {
    root!.render(<Probe />)
    await flush()
  })
}

async function settle(img: HTMLImageElement, outcome: 'load' | 'error'): Promise<void> {
  await act(async () => {
    img.dispatchEvent(new Event(outcome))
    await flush()
  })
}

beforeEach(() => {
  scrolled = []
  Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
    scrolled.push(this.id)
  })
  setNavigationType('navigate')
  // Every id a permissive hash filter could reach is present, so each
  // negative test can fail: #the-quarry, #ev-7 (one digit) and #corrections.
  document.body.innerHTML =
    '<div class="theo-page"><img id="hero" src="/h.jpg">' +
    '<div class="theo-paper-body"><h2 id="the-quarry">The quarry</h2>' +
    '<p id="ev-7" class="theo-evidence">w</p>' +
    '<p id="ev-07" class="theo-evidence">x</p>' +
    '<img id="figure" src="/f.jpg">' +
    '<section id="corrections"><h2>Corrections</h2></section></div></div>' +
    '<div id="mount"></div>'
  setComplete(image('hero'), true)
  setComplete(image('figure'), true)
})

afterEach(() => {
  act(() => root?.unmount())
  root = null
  window.location.hash = ''
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

it('scrolls to the evidence paragraph once the images above it have loaded', async () => {
  window.location.hash = '#ev-07'
  setComplete(image('hero'), false)
  await mount()
  expect(scrolled).toEqual([])
  await settle(image('hero'), 'load')
  expect(scrolled).toEqual(['ev-07'])
})

it('an image that fails to load does not hold the scroll back', async () => {
  window.location.hash = '#ev-07'
  setComplete(image('hero'), false)
  await mount()
  await settle(image('hero'), 'error')
  expect(scrolled).toEqual(['ev-07'])
})

it('does not wait for a lazy image, which never loads off-screen', async () => {
  window.location.hash = '#ev-07'
  image('hero').setAttribute('loading', 'lazy')
  setComplete(image('hero'), false)
  await mount()
  expect(scrolled).toEqual(['ev-07'])
})

it('does not wait for an image below the target, which cannot move it', async () => {
  window.location.hash = '#ev-07'
  setComplete(image('figure'), false)
  await mount()
  expect(scrolled).toEqual(['ev-07'])
})

it('scrolls to the corrections log', async () => {
  window.location.hash = '#corrections'
  setComplete(image('hero'), false)
  setComplete(image('figure'), false)
  await mount()
  expect(scrolled).toEqual([])
  await settle(image('hero'), 'load')
  expect(scrolled).toEqual([])
  await settle(image('figure'), 'load')
  expect(scrolled).toEqual(['corrections'])
})

it('ignores a hash that is not an evidence or corrections anchor', async () => {
  window.location.hash = '#the-quarry'
  await mount()
  expect(scrolled).toEqual([])
})

it('ignores an evidence id with fewer than two digits', async () => {
  window.location.hash = '#ev-7'
  await mount()
  expect(scrolled).toEqual([])
})

it.each(['wheel', 'touchstart', 'pointerdown', 'keydown'])(
  'a %s from the reader before the images settle drops the re-scroll',
  async type => {
    window.location.hash = '#ev-07'
    setComplete(image('hero'), false)
    await mount()
    await act(async () => {
      document.body.dispatchEvent(new Event(type, { bubbles: true }))
      await flush()
    })
    await settle(image('hero'), 'load')
    expect(scrolled).toEqual([])
  },
)

it('an in-page link that changes the hash before the images settle drops the re-scroll', async () => {
  window.location.hash = '#ev-07'
  setComplete(image('hero'), false)
  await mount()
  await act(async () => {
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await flush()
  })
  await settle(image('hero'), 'load')
  expect(scrolled).toEqual([])
})

it.each(['reload', 'back_forward'] as const)(
  'a %s navigation keeps the scroll position the browser restored',
  async type => {
    setNavigationType(type)
    window.location.hash = '#ev-07'
    await mount()
    expect(scrolled).toEqual([])
  },
)

it('removes its window and image listeners when unmounted before the images settle', async () => {
  window.location.hash = '#ev-07'
  setComplete(image('hero'), false)
  const added = vi.spyOn(window, 'addEventListener')
  const removed = vi.spyOn(window, 'removeEventListener')
  const imageRemoved = vi.spyOn(image('hero'), 'removeEventListener')
  await mount()
  act(() => root!.unmount())
  root = null
  const addedTypes = added.mock.calls.map(([type]) => type).sort()
  const removedTypes = removed.mock.calls.map(([type]) => type).sort()
  expect(addedTypes).toEqual(['hashchange', 'keydown', 'pointerdown', 'touchstart', 'wheel'])
  expect(removedTypes).toEqual(addedTypes)
  expect(imageRemoved.mock.calls.map(([type]) => type).sort()).toEqual(['error', 'load'])
  await settle(image('hero'), 'load')
  expect(scrolled).toEqual([])
})
