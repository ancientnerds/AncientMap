/**
 * @vitest-environment jsdom
 *
 * The full-screen notices of /globe.html. The phone gate must stay exactly as
 * it was (spec §3: text and layout unchanged) while its controls now report
 * globe_gate; the unsupported and error screens reuse its layout and links.
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

/** The gate as App.tsx rendered it before globe-load (commit 7df5e24), verbatim. */
function LegacyGate({ onGlobe }: { onGlobe: () => void }) {
  return (
      <div className="mobile-overlay">
        <div className="mobile-overlay-content">
          <img src={BRAND_ASSETS.logo} alt="" className="mobile-logo-icon" />
          <div className="mobile-logo-main">{BRAND_NAME}</div>
          <div className="mobile-logo-sub">{BRAND_SUBTITLE}</div>
          <div className="mobile-message">
            The 3D globe is optimized for desktop browsers.
          </div>
          <div className="mobile-hint">
            Explore our mobile-friendly pages below, or continue to the globe.
          </div>
          <div className="mobile-actions">
            <div className="mobile-actions-row">
              <a className="mobile-action-btn" href="/news.html">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1m2 13a2 2 0 0 1-2-2V7m2 13a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-2" /></svg>
                Stories
              </a>
              <a className="mobile-action-btn" href="/radar.html">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83" /></svg>
                Radar
              </a>
            </div>
            <div className="mobile-actions-row">
              <a className="mobile-action-btn" href="/articles.html">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
                Journal
              </a>
              <a className="mobile-action-btn" href="/lyra.html">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
                Lyra
              </a>
            </div>
            <div className="mobile-actions-row">
              <a className="mobile-action-btn" href="/db.html">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2C6.48 2 2 3.79 2 6v12c0 2.21 4.48 4 10 4s10-1.79 10-4V6c0-2.21-4.48-4-10-4zM2 12c0 2.21 4.48 4 10 4s10-1.79 10-4" /></svg>
                Database
              </a>
              <button
                className="mobile-action-btn mobile-action-globe"
                onClick={onGlobe}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="M2 12h20" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></svg>
                3D Globe
              </button>
            </div>
          </div>
        </div>
      </div>
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
  it('renders exactly the DOM of the gate it replaced', async () => {
    const before = await mount(<LegacyGate onGlobe={() => {}} />)
    const after = await mount(<PhoneGate onChoice={() => {}} />)
    expect(after.innerHTML).toBe(before.innerHTML)
    expect(after.innerHTML.length).toBeGreaterThan(1000)
  })

  it('each of the six controls reports its choice as globe_gate', async () => {
    const latches: GateChoice[] = []
    const container = await mount(
      <PhoneGate onChoice={choice => { latches.push(choice); reportGateChoice(choice, createGlobeEndingLatch()) }} />,
    )
    const controls = [...container.querySelectorAll<HTMLElement>('.mobile-action-btn')]
    expect(controls.map(c => c.textContent)).toEqual(['Stories', 'Radar', 'Journal', 'Lyra', 'Database', '3D Globe'])
    for (const control of controls) control.click()
    expect(latches).toEqual(['stories', 'radar', 'journal', 'lyra', 'db', 'globe'])
    expect(vi.mocked(track).mock.calls).toEqual(
      ['stories', 'radar', 'journal', 'lyra', 'db', 'globe'].map(choice => ['globe_gate', { choice }]),
    )
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
    expect(links).toEqual(['/news.html', '/radar.html', '/articles.html', '/lyra.html', '/db.html'])
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
    expect(links).toEqual(['/news.html', '/radar.html', '/articles.html', '/lyra.html', '/db.html'])
    const button = container.querySelector<HTMLButtonElement>('button')!
    expect(button.textContent).toBe('Reload the globe')
    button.click()
    expect(reload).toHaveBeenCalledOnce()
    vi.unstubAllGlobals()
  })
})
