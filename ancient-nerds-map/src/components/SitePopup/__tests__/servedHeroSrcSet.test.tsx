/**
 * @vitest-environment jsdom
 *
 * The popup hero carries the srcset only while it shows the hero the page was served
 * with (review 2026-10-20): after a lightbox set-hero, an admin edit or a switch to
 * another source, the 800 px copy would be the old hero's and phones would show the
 * replaced picture.
 */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SiteData } from '../../../data/sites'
import SitePopup from '../SitePopup'
import { servedHeroSrcSet } from '../servedHeroSrcSet'

// The popup reads only isOffline; the provider would start the offline-cache polling.
vi.mock('../../../contexts/OfflineContext', () => ({ useOffline: () => ({ isOffline: false }) }))

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const HERO = '/data/images/wiki/d953e9b3/hero.webp'
const SRCSET = `/data/images/wiki-800/d953e9b3/hero.webp 800w, ${HERO} 1600w`

const site: SiteData = {
  id: 'd953e9b3-0000-4000-8000-000000000000',
  title: 'Göbekli Tepe',
  location: 'Turkey',
  category: 'Temple',
  period: '10000 BC',
  description: 'A Neolithic hilltop sanctuary.',
  image: HERO,
  imageSrcSet: SRCSET,
  sourceId: 'ancient_nerds',
  coordinates: [38.92, 37.22],
}

describe('servedHeroSrcSet', () => {
  it('gives the served hero its srcset', () => {
    expect(servedHeroSrcSet(site, HERO)).toBe(SRCSET)
  })

  it('gives a hero set in the lightbox none', () => {
    expect(servedHeroSrcSet(site, `${HERO}?v=1760954400`)).toBeUndefined()
  })

  it('gives another record\'s picture none', () => {
    expect(servedHeroSrcSet(site, '/data/images/wiki/d953e9b3/Temple_gate.webp')).toBeUndefined()
    expect(servedHeroSrcSet(undefined, HERO)).toBeUndefined()
  })
})

const roots: Root[] = []

/** The popup's hero <img> on first render: its mount effects fetch images, links and
 *  sources, kept pending here, so it shows what the page shows before any answers. */
async function heroImg(shown: SiteData): Promise<HTMLImageElement> {
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
  // jsdom has no ResizeObserver; the gallery tabs observe their strip for the scroll arrows.
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  roots.push(root)
  await act(async () => root.render(<SitePopup site={shown} onClose={() => {}} isStandalone fullPage />))
  const img = [...document.querySelectorAll('img')].find(el => el.getAttribute('src') === HERO)
  expect(img).toBeDefined()
  return img!
}

afterEach(async () => {
  for (const root of roots.splice(0)) await act(async () => root.unmount())
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

describe('SitePopup hero', () => {
  it('shows the served hero with its srcset', async () => {
    expect((await heroImg(site)).getAttribute('srcset')).toBe(SRCSET)
  })

  it('shows a hero without a srcset as the single file', async () => {
    expect((await heroImg({ ...site, imageSrcSet: undefined })).hasAttribute('srcset')).toBe(false)
  })
})
