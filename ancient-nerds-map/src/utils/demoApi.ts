/**
 * Demo API for Puppeteer-driven video recording.
 * Only active when `?demo=1` is in the URL.
 *
 * Usage:
 *   1. App.tsx calls registerAppDemoApi() with top-level setters
 *   2. Globe.tsx calls registerGlobeDemoApi() with rendering-level refs
 *   3. Puppeteer uses window.__DEMO.* to orchestrate scenes
 */

import type { FilterMode } from '../App'
import type { SiteData } from '../data/sites'

export interface DemoAPI {
  // Camera
  flyTo(lng: number, lat: number): Promise<void>
  setZoom(distance: number): void
  smoothZoom(from: number, to: number, durationMs: number): void
  setAutoRotate(enabled: boolean): void
  setFlyToDuration(ms: number): void

  // Filters
  setFilterMode(mode: FilterMode): void
  setAgeRange(min: number, max: number): void

  // Sources
  setSelectedSources(sourceIds: string[]): void
  loadSources(sourceIds: string[]): void

  // Visual layers
  setVectorLayer(layer: string, visible: boolean): void
  setSatellite(enabled: boolean): void
  setGeoLabels(visible: boolean): void

  // Empires
  showEmpire(id: string): Promise<void>
  hideAllEmpires(): void

  // Paleoshoreline
  setPaleoshoreline(visible: boolean, seaLevel?: number): void

  // Site interaction (tooltips & popups)
  selectSite(name: string): Promise<void>
  deselectSite(): void
  openSitePopup(name: string): Promise<void>
  closeAllPopups(): void
  setDemoTooltips(visible: boolean): void
  setDemoPopups(visible: boolean): void

  // Mapbox street-level
  enterMapbox(): Promise<void>
  exitMapbox(): void
  mapboxJumpTo(lng: number, lat: number, zoom: number, bearing?: number, pitch?: number): void

  // UI control
  hideAllUI(): void
  showUI(): void

  // Status
  isReady(): boolean
  waitUntilReady(): Promise<void>
}

declare global {
  interface Window {
    __DEMO?: Partial<DemoAPI>
  }
}

/** Returns true if ?demo=1 is in the URL */
export function isDemoMode(): boolean {
  return new URLSearchParams(window.location.search).has('demo')
}

/** App.tsx registers top-level state setters */
export interface AppDemoSetters {
  setFilterMode: (mode: FilterMode) => void
  setAgeRange: (range: [number, number]) => void
  setFlyToCoords: (coords: [number, number] | null) => void
  setDemoMode: (on: boolean) => void
  setSelectedSources: (sources: string[]) => void
  handleLoadSources: (sourceIds: string[]) => void
  openSitePopup: (site: SiteData) => void
  closeAllPopups: () => void
  sitesRef: React.MutableRefObject<SiteData[]>
}

export function registerAppDemoApi(setters: AppDemoSetters): void {
  if (!isDemoMode()) return

  const api: Partial<DemoAPI> = {
    setFilterMode: (mode) => setters.setFilterMode(mode),
    setAgeRange: (min, max) => setters.setAgeRange([min, max]),
    flyTo: (lng, lat) => {
      return new Promise<void>((resolve) => {
        setters.setFlyToCoords([lng, lat])
        // Allow 700ms for the fly-to animation (600ms + buffer)
        setTimeout(() => {
          setters.setFlyToCoords(null)
          resolve()
        }, 700)
      })
    },
    hideAllUI: () => setters.setDemoMode(true),
    showUI: () => setters.setDemoMode(false),
    setSelectedSources: (ids) => setters.setSelectedSources(ids),
    loadSources: (ids) => setters.handleLoadSources(ids),
    openSitePopup: (name) => {
      const site = setters.sitesRef.current.find(s =>
        s.title.toLowerCase().includes(name.toLowerCase())
      )
      if (!site) {
        console.warn(`[DemoAPI] Site not found: "${name}"`)
        return Promise.resolve()
      }
      setters.openSitePopup(site)
      return Promise.resolve()
    },
    closeAllPopups: () => setters.closeAllPopups(),
    setDemoTooltips: (visible) => {
      document.body.classList.toggle('demo-show-tooltips', visible)
    },
    setDemoPopups: (visible) => {
      document.body.classList.toggle('demo-show-popups', visible)
    },
  }

  window.__DEMO = { ...window.__DEMO, ...api }
}

/** Globe.tsx registers rendering-level methods */
export interface GlobeDemoRefs {
  isAutoRotatingRef: React.MutableRefObject<boolean>
  manualRotationRef: React.MutableRefObject<boolean>
  sceneRef: React.MutableRefObject<{ camera: { position: { setLength(d: number): void } }; controls: { update(): void } } | null>
  warpCompleteForLabelsRef: React.MutableRefObject<boolean>
  dotsAnimationCompleteRef: React.MutableRefObject<boolean>
  flyToDurationRef: React.MutableRefObject<number>
  setTileLayers: (updater: (prev: any) => any) => void
  setVectorLayers: (updater: (prev: any) => any) => void
  setGeoLabelsVisible: (visible: boolean) => void
  toggleEmpire: (id: string) => void
  getVisibleEmpires: () => Set<string>
  setPaleoshorelineVisible: (visible: boolean) => void
  setSeaLevelWithSlider: (level: number) => void
  // Site tooltip control
  validSitesRef: React.MutableRefObject<SiteData[]>
  setFrozenSite: (site: SiteData | null) => void
  setIsFrozen: (frozen: boolean) => void
  setTooltipPos: (pos: { x: number; y: number }) => void
  calculateTooltipPos: (site: SiteData) => { x: number; y: number }
  // Mapbox control
  enterMapboxMode: () => void
  exitMapboxMode: () => void
  mapboxServiceRef: React.MutableRefObject<any>
}

export function registerGlobeDemoApi(refs: GlobeDemoRefs): void {
  if (!isDemoMode()) return

  const api: Partial<DemoAPI> = {
    setAutoRotate: (enabled) => {
      refs.isAutoRotatingRef.current = enabled
      refs.manualRotationRef.current = enabled
    },
    setZoom: (distance) => {
      if (!refs.sceneRef.current) return
      const { camera, controls } = refs.sceneRef.current
      camera.position.setLength(distance)
      controls.update()
    },
    smoothZoom: (from, to, durationMs) => {
      // Time-based animation — works with both real and synthetic time.
      // Uses performance.now() so recording's synthetic clock drives it
      // at exactly the right pace regardless of actual FPS.
      const startTime = performance.now()
      const step = () => {
        const elapsed = performance.now() - startTime
        const t = Math.min(elapsed / durationMs, 1)
        const eased = t * t * (3 - 2 * t) // smoothstep
        const d = from + (to - from) * eased
        if (refs.sceneRef.current) {
          refs.sceneRef.current.camera.position.setLength(d)
          refs.sceneRef.current.controls.update()
        }
        if (t < 1) requestAnimationFrame(step)
      }
      step()
    },
    setFlyToDuration: (ms) => {
      refs.flyToDurationRef.current = ms
    },
    setSatellite: (on) => {
      refs.setTileLayers(prev => ({ ...prev, satellite: on }))
    },
    setVectorLayer: (key, visible) => {
      refs.setVectorLayers(prev => ({ ...prev, [key]: visible }))
    },
    setGeoLabels: (visible) => {
      refs.setGeoLabelsVisible(visible)
    },
    showEmpire: (id) => {
      return new Promise<void>((resolve) => {
        // Only toggle if not already visible (toggleEmpire handles loading + rendering)
        if (!refs.getVisibleEmpires().has(id)) {
          refs.toggleEmpire(id)
        }
        // Allow time for GeoJSON to load and render
        setTimeout(resolve, 2000)
      })
    },
    hideAllEmpires: () => {
      // Toggle off each visible empire so it properly unloads 3D geometry
      const visible = refs.getVisibleEmpires()
      visible.forEach(id => refs.toggleEmpire(id))
    },
    setPaleoshoreline: (visible, seaLevel) => {
      refs.setPaleoshorelineVisible(visible)
      if (seaLevel !== undefined) {
        refs.setSeaLevelWithSlider(seaLevel)
      }
    },
    selectSite: (name) => {
      const site = refs.validSitesRef.current.find(s =>
        s.title.toLowerCase().includes(name.toLowerCase())
      )
      if (!site) {
        console.warn(`[DemoAPI] Site not found: "${name}"`)
        return Promise.resolve()
      }
      // Set frozen tooltip state
      refs.setFrozenSite(site)
      refs.setIsFrozen(true)
      // Calculate and set tooltip position
      const pos = refs.calculateTooltipPos(site)
      refs.setTooltipPos(pos)
      return Promise.resolve()
    },
    deselectSite: () => {
      refs.setFrozenSite(null)
      refs.setIsFrozen(false)
    },
    enterMapbox: () => {
      return new Promise<void>((resolve) => {
        const mapbox = refs.mapboxServiceRef.current
        // Wait for Mapbox to be initialized (it loads asynchronously)
        const waitForInit = () => {
          if (mapbox?.getIsInitialized()) {
            refs.enterMapboxMode()
            // Wait for the 300ms CSS transition + React state update
            setTimeout(resolve, 500)
          } else {
            setTimeout(waitForInit, 100)
          }
        }
        waitForInit()
      })
    },
    exitMapbox: () => {
      refs.exitMapboxMode()
    },
    mapboxJumpTo: (lng, lat, zoom, bearing, pitch) => {
      const mapbox = refs.mapboxServiceRef.current
      if (!mapbox?.getIsInitialized()) {
        console.warn('[DemoAPI] Mapbox not initialized')
        return
      }
      // jumpTo is instant (no animation) — works with synthetic time
      const map = mapbox.getMap()
      if (map) {
        map.jumpTo({ center: [lng, lat], zoom, bearing: bearing ?? 0, pitch: pitch ?? 0 })
      }
    },
    isReady: () => {
      return refs.warpCompleteForLabelsRef.current && refs.dotsAnimationCompleteRef.current
    },
    waitUntilReady: () => {
      return new Promise<void>((resolve) => {
        const check = () => {
          if (refs.warpCompleteForLabelsRef.current && refs.dotsAnimationCompleteRef.current) {
            resolve()
          } else {
            setTimeout(check, 100)
          }
        }
        check()
      })
    },
  }

  window.__DEMO = { ...window.__DEMO, ...api }
}
