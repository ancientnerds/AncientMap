/**
 * A #ev-NN deep link from a video description re-scrolls to its paragraph
 * once the images above it have settled (loaded or failed), and nothing
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

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

async function mount(): Promise<void> {
  root = createRoot(document.getElementById('mount')!)
  await act(async () => {
    root!.render(<Probe />)
    await flush()
  })
}

beforeEach(() => {
  scrolled = []
  Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
    scrolled.push(this.id)
  })
  document.body.innerHTML =
    '<div class="theo-page"><img id="hero" src="/h.jpg">' +
    '<div class="theo-paper-body"><p id="ev-07" class="theo-evidence">x</p></div></div>' +
    '<div id="mount"></div>'
  setComplete(document.getElementById('hero') as HTMLImageElement, true)
})

afterEach(() => {
  act(() => root?.unmount())
  root = null
  window.location.hash = ''
  document.body.innerHTML = ''
})

it('scrolls to the evidence paragraph once the images above it have loaded', async () => {
  window.location.hash = '#ev-07'
  const hero = document.getElementById('hero') as HTMLImageElement
  setComplete(hero, false)
  await mount()
  expect(scrolled).toEqual([])
  await act(async () => {
    hero.dispatchEvent(new Event('load'))
    await flush()
  })
  expect(scrolled).toEqual(['ev-07'])
})

it('an image that fails to load does not hold the scroll back', async () => {
  window.location.hash = '#ev-07'
  const hero = document.getElementById('hero') as HTMLImageElement
  setComplete(hero, false)
  await mount()
  await act(async () => {
    hero.dispatchEvent(new Event('error'))
    await flush()
  })
  expect(scrolled).toEqual(['ev-07'])
})

it('does not wait for a lazy image, which never loads off-screen', async () => {
  window.location.hash = '#ev-07'
  const hero = document.getElementById('hero') as HTMLImageElement
  hero.setAttribute('loading', 'lazy')
  setComplete(hero, false)
  await mount()
  expect(scrolled).toEqual(['ev-07'])
})

it('ignores a hash that is not an evidence or corrections anchor', async () => {
  window.location.hash = '#the-quarry'
  await mount()
  expect(scrolled).toEqual([])
})
