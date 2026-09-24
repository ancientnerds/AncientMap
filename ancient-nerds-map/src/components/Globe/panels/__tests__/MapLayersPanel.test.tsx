/**
 * The satellite toggle waits for its texture: while it is switched on but not
 * on the GPU yet, the row shows the existing loading indicator (the same span
 * the vector layers use), and the checkbox shows what the visitor asked for.
 *
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../../utils/cardApi', () => ({ reportAchievementEvent: vi.fn() }))

import { MapLayersPanel } from '../MapLayersPanel'
import { reportAchievementEvent } from '../../../../utils/cardApi'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null
let container: HTMLDivElement

async function renderPanel(satellite: boolean, satellitePending: boolean, onTileLayerToggle = vi.fn()) {
  if (!root) {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  }
  await act(async () => {
    root!.render(
      <MapLayersPanel
        minimized={false}
        onToggleMinimize={() => {}}
        tileLayers={{ satellite, streets: false }}
        satellitePending={satellitePending}
        onTileLayerToggle={onTileLayerToggle}
        vectorLayers={{ coastlines: true, countryBorders: true, rivers: false, lakes: false, coralReefs: false, glaciers: false, plateBoundaries: false }}
        onVectorLayerToggle={() => {}}
        isLoadingLayers={{}}
        layersLoaded={{ coastlines: true, countryBorders: true }}
        geoLabelsVisible={false}
        onGeoLabelsToggle={() => {}}
        labelTypesExpanded={false}
        onLabelTypesExpandToggle={() => {}}
        labelTypesVisible={{}}
        onLabelTypeToggle={() => {}}
        showMapbox={false}
        isOffline={false}
        cachedLayerIds={new Set()}
      />,
    )
  })
}

function satelliteRow(): HTMLLabelElement {
  const label = [...container.querySelectorAll('.base-maps-section label.layer-toggle')]
    .find(el => el.querySelector('.layer-label')?.textContent === 'Satellite')
  if (!label) throw new Error('no Satellite row')
  return label as HTMLLabelElement
}

afterEach(async () => {
  await act(async () => { root?.unmount() })
  root = null
  container?.remove()
})

describe('MapLayersPanel vector rows offline', () => {
  async function renderOffline(onVectorLayerToggle = vi.fn()) {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root!.render(
        <MapLayersPanel
          minimized={false}
          onToggleMinimize={() => {}}
          tileLayers={{ satellite: false, streets: false }}
          satellitePending={false}
          onTileLayerToggle={() => {}}
          // Coastlines switched off by the visitor; rivers never loaded
          vectorLayers={{ coastlines: false, countryBorders: true, rivers: false, lakes: false, coralReefs: false, glaciers: false, plateBoundaries: false }}
          onVectorLayerToggle={onVectorLayerToggle}
          isLoadingLayers={{}}
          layersLoaded={{ coastlines: true, countryBorders: true }}
          geoLabelsVisible={false}
          onGeoLabelsToggle={() => {}}
          labelTypesExpanded={false}
          onLabelTypesExpandToggle={() => {}}
          labelTypesVisible={{}}
          onLabelTypeToggle={() => {}}
          showMapbox={false}
          isOffline={true}
          // A sources-only download: no layer download is complete
          cachedLayerIds={new Set()}
        />,
      )
    })
  }

  function vectorRow(label: string): HTMLLabelElement {
    const row = [...container.querySelectorAll('label.layer-toggle')]
      .find(el => el.querySelector('.layer-label')?.textContent === label)
    if (!row) throw new Error(`no ${label} row`)
    return row as HTMLLabelElement
  }

  it('lets a layer that is loaded be switched back on: the toggle fetches nothing', async () => {
    const toggle = vi.fn()
    await renderOffline(toggle)
    const row = vectorRow('Coastlines')
    expect(row.querySelector('input')!.disabled).toBe(false)
    expect(row.className).not.toContain('offline-unavailable')
    await act(async () => { row.querySelector('input')!.click() })
    expect(toggle).toHaveBeenCalledWith('coastlines')
  })

  it('still blocks a layer that would have to be fetched', async () => {
    await renderOffline()
    const row = vectorRow('Rivers')
    expect(row.querySelector('input')!.disabled).toBe(true)
    expect(row.title).toContain('Not available offline')
  })
})

describe('MapLayersPanel satellite row', () => {
  it('shows the loading indicator while the satellite is pending', async () => {
    await renderPanel(true, true)
    const row = satelliteRow()
    const indicator = row.querySelector('.loading-indicator')
    expect(indicator?.textContent).toBe('...')
    expect(indicator?.previousElementSibling?.className).toBe('layer-label')
    expect(row.querySelector('input')!.checked).toBe(true)
  })

  it('shows no indicator once the satellite is ready, or while it is off', async () => {
    await renderPanel(true, false)
    expect(satelliteRow().querySelector('.loading-indicator')).toBe(null)
    await renderPanel(false, false)
    expect(satelliteRow().querySelector('.loading-indicator')).toBe(null)
  })

  it('keeps the toggle and the achievement as they were', async () => {
    const toggle = vi.fn()
    await renderPanel(false, false, toggle)
    await act(async () => { satelliteRow().querySelector('input')!.click() })
    expect(toggle).toHaveBeenCalledWith('satellite')
    expect(reportAchievementEvent).toHaveBeenCalledWith('satellite_enabled')
  })
})
