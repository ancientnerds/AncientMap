/**
 * @vitest-environment jsdom
 *
 * The full-screen notices of /globe.html. The phone gate keeps its text and
 * layout (spec §3) and lists the pages that work on a phone - Sites, Research
 * and Search joined on 2026-09-24 (owner request); its controls report
 * globe_gate, and the unsupported and error screens reuse its layout and links.
 * The probe (scripts/globe_probe/probe.py) finds the unsupported screen by the
 * text "show the 3D globe".
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../analytics', () => ({ track: vi.fn() }))

import { track } from '../../analytics'
import { createGlobeEndingLatch, installGlobeAbandon, reportGateChoice, type GateChoice } from '../../analytics/globeAbandon'
import { BRAND_NAME, BRAND_SUBTITLE, BRAND_ASSETS } from '../../constants/brand'
import GlobeErrorScreen from '../GlobeErrorScreen'
import GlobeUnsupported from '../GlobeUnsupported'
import PhoneGate from '../PhoneGate'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

/** The pages that work without the globe, in the order every notice lists them. */
const PAGES = [
  ['Stories', '/news.html', 'stories'],
  ['Sites', '/sites/', 'sites'],
  ['Research', '/research/', 'research'],
  ['Search', '/search.html', 'search'],
  ['Radar', '/radar.html', 'radar'],
  ['Journal', '/articles.html', 'journal'],
  ['Lyra', '/lyra.html', 'lyra'],
  ['Database', '/db.html', 'db'],
] as const
const HREFS = PAGES.map(([, href]) => href)

/** The label of every control, row by row. */
function rows(container: HTMLElement): string[][] {
  return [...container.querySelectorAll('.mobile-actions-row')].map(row =>
    [...row.children].map(c => c.textContent ?? ''),
  )
}

const roots: Root[] = []

async function mount(node: React.ReactNode): Promise<HTMLDivElement> {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  roots.push(root)
  await act(async () => root.render(node))
  return container
}

// jsdom cannot navigate; the gate's links are real <a href> elements
const noNavigation = (e: Event) => e.preventDefault()

beforeEach(() => {
  vi.mocked(track).mockClear()
  document.addEventListener('click', noNavigation)
})

afterEach(async () => {
  for (const root of roots.splice(0)) await act(async () => root.unmount())
  document.body.innerHTML = ''
  document.removeEventListener('click', noNavigation)
})

describe('PhoneGate', () => {
  it('keeps the gate text and lists the pages two per row, the globe button last', async () => {
    const container = await mount(<PhoneGate onChoice={() => {}} />)
    const text = container.textContent ?? ''
    expect(container.querySelector('.mobile-logo-main')!.textContent).toBe(BRAND_NAME)
    expect(container.querySelector('.mobile-logo-sub')!.textContent).toBe(BRAND_SUBTITLE)
    expect(container.querySelector<HTMLImageElement>('.mobile-logo-icon')!.getAttribute('src')).toBe(BRAND_ASSETS.logo)
    expect(text).toContain('The 3D globe is optimized for desktop browsers.')
    expect(text).toContain('Explore our mobile-friendly pages below, or continue to the globe.')
    expect(rows(container)).toEqual([
      ['Stories', 'Sites'], ['Research', 'Search'], ['Radar', 'Journal'], ['Lyra', 'Database'], ['3D Globe'],
    ])
    expect([...container.querySelectorAll('a')].map(a => a.getAttribute('href'))).toEqual(HREFS)
  })

  it('each of the nine controls reports its choice as globe_gate', async () => {
    const latches: GateChoice[] = []
    const container = await mount(
      <PhoneGate onChoice={choice => { latches.push(choice); reportGateChoice(choice, createGlobeEndingLatch()) }} />,
    )
    const controls = [...container.querySelectorAll<HTMLElement>('.mobile-action-btn')]
    expect(controls.map(c => c.textContent)).toEqual([...PAGES.map(([label]) => label), '3D Globe'])
    for (const control of controls) control.click()
    const choices = [...PAGES.map(([, , choice]) => choice), 'globe']
    expect(latches).toEqual(choices)
    expect(vi.mocked(track).mock.calls).toEqual(choices.map(choice => ['globe_gate', { choice }]))
  })

  it('one ending per load: a gate link, then the page leaving, sends only the link', async () => {
    const latch = createGlobeEndingLatch()
    const uninstall = installGlobeAbandon({ latch, getPhase: () => 'gate', now: () => 1200 })
    const container = await mount(<PhoneGate onChoice={choice => reportGateChoice(choice, latch)} />)
    container.querySelector<HTMLElement>('a[href="/articles.html"]')!.click()
    window.dispatchEvent(new Event('pagehide'))
    uninstall()
    expect(vi.mocked(track).mock.calls).toEqual([['globe_gate', { choice: 'journal' }]])
  })

  it('the globe button is no ending: leaving later still reports the abandon', async () => {
    const latch = createGlobeEndingLatch()
    const uninstall = installGlobeAbandon({ latch, getPhase: () => 'sites', now: () => 5000 })
    const container = await mount(<PhoneGate onChoice={choice => reportGateChoice(choice, latch)} />)
    container.querySelector<HTMLElement>('.mobile-action-globe')!.click()
    window.dispatchEvent(new Event('pagehide'))
    uninstall()
    expect(vi.mocked(track).mock.calls).toEqual([
      ['globe_gate', { choice: 'globe' }],
      ['globe_abandon', { ms: 5000, phase: 'sites' }],
    ])
  })
})

describe('GlobeUnsupported', () => {
  it('names the missing WebGL 2, the fix and the pages without the globe', async () => {
    const container = await mount(<GlobeUnsupported reason="no_webgl2" detail={undefined} />)
    const text = container.textContent ?? ''
    expect(text).toContain("Your browser can't show the 3D globe")
    expect(text).toContain('show the 3D globe') // what the probe looks for
    expect(text).toContain('WebGL 2 is not available.')
    expect(text).toContain('Turning on hardware acceleration in your browser settings often fixes this.')
    const links = [...container.querySelectorAll('a')].map(a => a.getAttribute('href'))
    expect(links).toEqual(HREFS)
    expect(rows(container)).toEqual([['Stories', 'Sites'], ['Research', 'Search'], ['Radar', 'Journal'], ['Lyra', 'Database']])
    expect(container.querySelector('.mobile-overlay')).not.toBeNull()
  })

  it('names the texture limit of the graphics card', async () => {
    const container = await mount(<GlobeUnsupported reason="max_texture_size" detail="2048" />)
    expect(container.textContent).toContain('Your graphics card supports textures up to 2048 px; the globe needs 4096.')
  })
})

describe('GlobeErrorScreen', () => {
  it('shows the phase and message, a reload and the pages without the globe', async () => {
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    const container = await mount(<GlobeErrorScreen phase="labels" message="/data/labels.json: HTTP 404" />)
    const text = container.textContent ?? ''
    expect(text).toContain('The 3D globe could not start')
    expect(text).toContain('Something went wrong while loading (labels): /data/labels.json: HTTP 404')
    const links = [...container.querySelectorAll('a')].map(a => a.getAttribute('href'))
    expect(links).toEqual(HREFS)
    expect(rows(container).at(-1)).toEqual(['Reload the globe'])
    const button = container.querySelector<HTMLButtonElement>('button')!
    expect(button.textContent).toBe('Reload the globe')
    button.click()
    expect(reload).toHaveBeenCalledOnce()
    vi.unstubAllGlobals()
  })

  it('says the globe stopped, not that it could not start, for a failure after it was up', async () => {
    const container = await mount(<GlobeErrorScreen phase="live" message="Cannot read properties of null" />)
    const text = container.textContent ?? ''
    expect(text).toContain('The 3D globe stopped')
    expect(text).toContain('Something went wrong while it was running: Cannot read properties of null')
    expect(text).not.toContain('could not start')
    expect(container.querySelector('button')!.textContent).toBe('Reload the globe')
  })
})
