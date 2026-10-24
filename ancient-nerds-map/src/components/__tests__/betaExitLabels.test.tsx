/**
 * The beta exit (owner decision D62, wording B, 2026-10-24): both BETA badges are gone (the
 * landing footer and the globe's logo), the popup gallery keeps its warning icon with
 * "Images matched automatically – some may not show this site", the connector status modal
 * describes coverage without calling the system a beta, and the dead `.beta-badge` CSS is
 * removed (knip and vulture do not see CSS).
 *
 * @vitest-environment jsdom
 */

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { act, type ComponentProps, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SiteData } from '../../data/sites'
import ConnectorStatusModal from '../ConnectorStatusModal'
import FilterPanel from '../FilterPanel'
import SitePopup from '../SitePopup'

vi.mock('../../contexts/OfflineContext', () => ({
  useOffline: () => ({ isOffline: false, cachedSourceIds: new Set<string>() }),
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: null }) }))

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const APP_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const read = (path: string) => readFileSync(join(APP_DIR, path), 'utf8')

const GALLERY_WARNING = 'Images matched automatically – some may not show this site'
const CONNECTOR_DESCRIPTION =
  'Content is aggregated from museums, libraries, and archives worldwide. ' +
  'Coverage and accuracy vary by source, and some connectors may be temporarily unavailable.'

const roots: Root[] = []

async function render(element: ReactElement): Promise<void> {
  // The components' mount effects fetch (images, links, connector status); kept pending,
  // so the test sees what the page shows before any answer.
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
  // jsdom has no ResizeObserver; the gallery tabs observe their strip for the scroll arrows.
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  roots.push(root)
  await act(async () => root.render(element))
}

afterEach(async () => {
  for (const root of roots.splice(0)) await act(async () => root.unmount())
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

const noBetaText = () => expect(document.body.textContent ?? '').not.toMatch(/\bbeta\b/i)

describe('beta exit (D62)', () => {
  it('the globe logo carries no BETA badge', async () => {
    const noop = () => {}
    const props: ComponentProps<typeof FilterPanel> = {
      categories: [], selectedCategories: [], availableCategories: [],
      countries: [], selectedCountries: [], availableCountries: [], countryColors: {},
      sources: [], selectedSources: ['ancient_nerds'],
      searchQuery: '', searchAllSources: false,
      applyFiltersToSearch: true, onApplyFiltersToSearchChange: noop,
      searchWithinProximity: false, onSearchWithinProximityChange: noop,
      searchResults: [], isSearching: false, searchError: null,
      filterMode: 'age', ageRange: [-5000, 1500],
      onCategoryChange: noop, onCountryChange: noop, onSourceChange: noop, onSearchChange: noop,
      onSearchAllSourcesChange: noop, onSearchResultSelect: noop, onRandomSite: noop,
      onFilterModeChange: noop, onAgeRangeChange: noop,
      totalSites: 1, filteredCount: 1,
      proximityCenter: null, proximityRadius: 100, isSettingProximityOnGlobe: false,
      onProximityCenterChange: noop, onProximityRadiusChange: noop, onSetProximityOnGlobeChange: noop,
      proximityResults: [], proximityHoverCoords: null,
      searchWithinEmpires: false, onSearchWithinEmpiresChange: noop, hasVisibleEmpires: false,
    }
    await render(<FilterPanel {...props} />)
    const logo = document.querySelector('.logo-wrapper')!
    expect(logo.querySelector('.logo-main')).not.toBeNull()
    expect(logo.querySelector('.beta-badge')).toBeNull()
    expect(document.querySelector('.beta-badge')).toBeNull()
    noBetaText()
  })

  it('the popup gallery keeps its warning icon with the new wording', async () => {
    const site: SiteData = {
      id: 'd953e9b3-0000-4000-8000-000000000000',
      title: 'Göbekli Tepe',
      location: 'Turkey',
      category: 'Temple',
      period: '10000 BC',
      description: 'A Neolithic hilltop sanctuary.',
      sourceId: 'ancient_nerds',
      coordinates: [38.92, 37.22],
    }
    await render(<SitePopup site={site} onClose={() => {}} isStandalone fullPage />)
    const warning = document.querySelector('.gallery-footer .gallery-dev-warning')!
    expect(warning.querySelector('svg')).not.toBeNull()
    expect(warning.querySelector('span')!.textContent).toBe(GALLERY_WARNING)
    noBetaText()
  })

  it('the connector status modal describes coverage without a beta sentence', async () => {
    await render(<ConnectorStatusModal isOpen onClose={() => {}} />)
    const description = document.querySelector('.connector-status-modal-description')!
    expect(description.textContent!.replace(/\s+/g, ' ').trim()).toBe(CONNECTOR_DESCRIPTION)
    noBetaText()
  })

  it('the landing footer carries no BETA badge', () => {
    const html = read('index.html')
    const footer = html.slice(html.indexOf('<footer class="landing-footer">'), html.indexOf('</footer>'))
    expect(footer).toContain('<span class="footer-name">ANCIENT NERDS Research Platform</span>')
    expect(footer).not.toContain('beta-badge')
    expect(html).not.toMatch(/\bbeta\b/i)
  })

  it('no page entry shows a beta label', () => {
    // every MPA entry, inline <style> blocks included (`beta-badge` matches the word too)
    const pages = readdirSync(APP_DIR).filter(name => name.endsWith('.html'))
    expect(pages).toEqual(expect.arrayContaining(['index.html', 'globe.html', 'site.html']))
    for (const page of pages) expect(read(page), page).not.toMatch(/\bbeta\b/i)
  })

  it('no stylesheet keeps the dead .beta-badge rule', () => {
    const sheets = (readdirSync(join(APP_DIR, 'src'), { recursive: true }) as string[])
      .filter(name => name.endsWith('.css'))
    expect(sheets).toContain(join('styles', 'landing.css'))
    for (const sheet of sheets) expect(read(join('src', sheet))).not.toContain('beta-badge')
  })

  it('the longer gallery warning may wrap beside the connector status', () => {
    // A nowrap, non-shrinking warning of 58 characters pushed the connector status out of a
    // phone-wide footer. The layout itself is measured in a real Chrome by
    // tests/frontend/test_gallery_footer_layout.py (local only, it needs Playwright); this
    // pins the rule it measures for CI.
    const css = read(join('src', 'styles', 'index.css'))
    const rules = [...css.matchAll(/(?:^|\n)\.gallery-dev-warning\s*\{([^}]*)\}/g)].map(m => m[1])
    expect(rules.length).toBeGreaterThanOrEqual(1)
    for (const rule of rules) {
      expect(rule).not.toMatch(/white-space:\s*nowrap/)
      expect(rule).not.toMatch(/flex-shrink:\s*0/)
    }
    expect(rules.some(rule => /flex:\s*0 1 auto;/.test(rule) && /max-width:\s*60%;/.test(rule))).toBe(true)
  })
})
