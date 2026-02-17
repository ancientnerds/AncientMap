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

export interface DemoAPI {
  // Camera
  flyTo(lng: number, lat: number): Promise<void>
  setZoom(distance: number): void
  smoothZoom(from: number, to: number, durationMs: number): void
  setAutoRotate(enabled: boolean): void

  // Filters
  setFilterMode(mode: FilterMode): void
  setAgeRange(min: number, max: number): void

  // Visual layers
  setVectorLayer(layer: string, visible: boolean): void
  setSatellite(enabled: boolean): void

  // Empires
  showEmpire(id: string): Promise<void>
  hideAllEmpires(): void

  // Paleoshoreline
  setPaleoshoreline(visible: boolean, seaLevel?: number): void

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
  setTileLayers: (updater: (prev: any) => any) => void
  setVectorLayers: (updater: (prev: any) => any) => void
  toggleEmpire: (id: string) => void
  getVisibleEmpires: () => Set<string>
  setPaleoshorelineVisible: (visible: boolean) => void
  setSeaLevelWithSlider: (level: number) => void
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
    setSatellite: (on) => {
      refs.setTileLayers(prev => ({ ...prev, satellite: on }))
    },
    setVectorLayer: (key, visible) => {
      refs.setVectorLayers(prev => ({ ...prev, [key]: visible }))
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
