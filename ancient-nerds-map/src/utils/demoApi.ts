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

export interface CameraState {
  distance: number
  lat: number
  lng: number
  animating: boolean
}

export interface DemoAPI {
  // Camera
  flyTo(lng: number, lat: number): Promise<void>
  setZoom(distance: number): void
  smoothZoom(from: number, to: number, durationMs: number): void
  setAutoRotate(enabled: boolean): void
  setFlyToDuration(ms: number): void
  /** Instant camera placement: surface point under the camera + distance from the globe centre. */
  setCameraPose(lng: number, lat: number, distance: number): void

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
  /** Mapbox DEM terrain for recordings (null disables). Demo-only; the live globe never calls it. */
  setTerrain(exaggeration: number | null): void
  /** Sweep the Mapbox bearing from→to around a fixed centre; synthetic-time safe like smoothZoom. */
  mapboxOrbit(lng: number, lat: number, zoom: number, pitch: number, bearingFrom: number, bearingTo: number, durationMs: number): void
  /** Resolves once Mapbox reports `idle` (all tiles loaded) or after `timeoutMs`. */
  mapboxWaitIdle(timeoutMs?: number): Promise<void>
  /** Swap the Mapbox style by URL (e.g. satellite-streets for labels); resolves on style.load. */
  setMapboxStyleUrl(url: string): Promise<void>
  /** Drive the Mapbox camera through keyframes (`at` = 0..1 of durationMs), smoothstep per segment. */
  mapboxPath(keyframes: MapboxKeyframe[], durationMs: number): void
  /** Jump straight to the pose the path would have at fraction `t` (warm-up sampling). */
  mapboxJumpToPathPose(keyframes: MapboxKeyframe[], t: number): void
  /** Replace the app's dark fog (it blackens satellite imagery at globe zooms) with any Mapbox fog spec. */
  setMapboxFog(spec: Record<string, unknown>): void
  /** Hide every style layer whose id matches `pattern` (regex source). Returns how many were hidden. */
  hideMapboxLayers(pattern: string): number | Promise<number>
  /** raster-fade-duration for every raster layer; 0 so tiles are opaque on the first captured frame. */
  setMapboxRasterFade(ms: number): void
  /** True when every tile (imagery + DEM) for the current view is loaded; the recorder polls this per frame. */
  mapboxTilesLoaded(): boolean
  /**
   * Tint one country (ISO 3166-1 alpha-2) on the globe from Mapbox's country
   * boundaries, below the labels; fully visible from space, faded out by z7.5
   * so a view inside the country is not tinted. Recording-only.
   */
  setMapboxCountryHighlight(iso2: string, color: string): void

  // UI control
  hideAllUI(): void
  showUI(): void

  // Status
  /** Camera distance from the globe centre and the surface point under it (scene debugging). */
  getCameraState(): CameraState | Promise<CameraState>
  isReady(): boolean
  waitUntilReady(): Promise<void>
}

export interface MapboxKeyframe {
  at: number
  lng: number
  lat: number
  zoom: number
  pitch: number
  bearing: number
  /**
   * Terrain exaggeration to apply from this keyframe on (`null` = off). Zooming
   * out over terrain while the centre moves from mountains to sea puts the
   * camera below the surface; paths switch terrain off once they are high.
   */
  terrain?: number | null
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
  sceneRef: React.MutableRefObject<{ camera: { position: { setLength(d: number): void; length(): number; set(x: number, y: number, z: number): void; x: number; y: number; z: number }; lookAt(x: number, y: number, z: number): void }; controls: { update(): void } } | null>
  cameraAnimationRef: React.MutableRefObject<number | null>
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

type Vec3 = [number, number, number]

/** Camera pose along a keyframe path at fraction `t` (0..1), smoothstep per segment. */
function pathPose(keyframes: MapboxKeyframe[], t: number): Omit<MapboxKeyframe, 'at'> {
  let i = 1
  while (i < keyframes.length - 1 && keyframes[i].at <= t) i++
  const a = keyframes[i - 1]
  const b = keyframes[i]
  const span = Math.max(b.at - a.at, 1e-6)
  const u = Math.max(0, Math.min(1, (t - a.at) / span))
  const e = u * u * (3 - 2 * u)
  const lerp = (x: number, y: number) => x + (y - x) * e
  // Terrain state = the latest keyframe at or before t that declares one.
  let terrain: number | null | undefined
  for (const k of keyframes) {
    if (k.at <= t && k.terrain !== undefined) terrain = k.terrain
  }
  return { lng: lerp(a.lng, b.lng), lat: lerp(a.lat, b.lat), zoom: lerp(a.zoom, b.zoom), pitch: lerp(a.pitch, b.pitch), bearing: lerp(a.bearing, b.bearing), terrain }
}

/** Unit direction for a surface point — the same mapping useFlyToAnimation uses. */
function directionFor(lng: number, lat: number): Vec3 {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return [-Math.sin(phi) * Math.cos(theta), Math.cos(phi), Math.sin(phi) * Math.sin(theta)]
}

export function registerGlobeDemoApi(refs: GlobeDemoRefs): void {
  if (!isDemoMode()) return

  // A pending app fly-to would keep overwriting the camera each frame.
  const cancelFlyTo = () => {
    if (refs.cameraAnimationRef.current !== null) {
      cancelAnimationFrame(refs.cameraAnimationRef.current)
      refs.cameraAnimationRef.current = null
    }
    refs.isAutoRotatingRef.current = false
  }

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
    setCameraPose: (lng, lat, distance) => {
      const scene = refs.sceneRef.current
      if (!scene) return
      cancelFlyTo()
      const d = directionFor(lng, lat)
      scene.camera.position.set(d[0] * distance, d[1] * distance, d[2] * distance)
      scene.camera.lookAt(0, 0, 0)
      scene.controls.update()
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
        // Wait for Mapbox to be initialized. The service itself is created
        // lazily (mapboxLoader), so read the ref on every poll.
        const waitForInit = () => {
          if (refs.mapboxServiceRef.current?.getIsInitialized()) {
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
    setTerrain: (exaggeration) => {
      const mapbox = refs.mapboxServiceRef.current
      if (!mapbox?.getIsInitialized()) {
        console.warn('[DemoAPI] Mapbox not initialized')
        return
      }
      mapbox.setTerrain(exaggeration)
    },
    mapboxOrbit: (lng, lat, zoom, pitch, bearingFrom, bearingTo, durationMs) => {
      const map = refs.mapboxServiceRef.current?.getMap()
      if (!map) {
        console.warn('[DemoAPI] Mapbox not initialized')
        return
      }
      const startTime = performance.now()
      const step = () => {
        const t = Math.min((performance.now() - startTime) / durationMs, 1)
        const eased = t * t * (3 - 2 * t) // smoothstep
        map.jumpTo({ center: [lng, lat], zoom, pitch, bearing: bearingFrom + (bearingTo - bearingFrom) * eased })
        if (t < 1) requestAnimationFrame(step)
      }
      step()
    },
    setMapboxStyleUrl: (url) => {
      return new Promise<void>((resolve) => {
        const mapbox = refs.mapboxServiceRef.current
        const map = mapbox?.getMap()
        if (!mapbox?.getIsInitialized() || !map) {
          console.warn('[DemoAPI] Mapbox not initialized')
          resolve()
          return
        }
        map.once('style.load', () => resolve())
        mapbox.setStyleUrl(url)
      })
    },
    mapboxPath: (keyframes, durationMs) => {
      const map = refs.mapboxServiceRef.current?.getMap()
      if (!map || keyframes.length < 2) {
        console.warn('[DemoAPI] mapboxPath needs Mapbox and ≥2 keyframes')
        return
      }
      const startTime = performance.now()
      let terrainApplied: number | null | undefined
      const step = () => {
        const t = Math.min((performance.now() - startTime) / durationMs, 1)
        const pose = pathPose(keyframes, t)
        if (pose.terrain !== undefined && pose.terrain !== terrainApplied) {
          refs.mapboxServiceRef.current?.setTerrain(pose.terrain)
          terrainApplied = pose.terrain
        }
        map.jumpTo({ center: [pose.lng, pose.lat], zoom: pose.zoom, pitch: pose.pitch, bearing: pose.bearing })
        if (t < 1) requestAnimationFrame(step)
      }
      step()
    },
    mapboxJumpToPathPose: (keyframes, t) => {
      const map = refs.mapboxServiceRef.current?.getMap()
      if (!map || keyframes.length < 2) return
      const pose = pathPose(keyframes, t)
      if (pose.terrain !== undefined) refs.mapboxServiceRef.current?.setTerrain(pose.terrain)
      map.jumpTo({ center: [pose.lng, pose.lat], zoom: pose.zoom, pitch: pose.pitch, bearing: pose.bearing })
    },
    setMapboxFog: (spec) => {
      const map = refs.mapboxServiceRef.current?.getMap()
      if (!map) {
        console.warn('[DemoAPI] Mapbox not initialized')
        return
      }
      map.setFog(spec as Parameters<typeof map.setFog>[0])
    },
    hideMapboxLayers: (pattern) => {
      const map = refs.mapboxServiceRef.current?.getMap()
      if (!map) {
        console.warn('[DemoAPI] Mapbox not initialized')
        return 0
      }
      const re = new RegExp(pattern)
      const hit = (map.getStyle()?.layers ?? []).filter((l: { id: string }) => re.test(l.id))
      hit.forEach((l: { id: string }) => map.setLayoutProperty(l.id, 'visibility', 'none'))
      return hit.length
    },
    setMapboxCountryHighlight: (iso2, color) => {
      const map = refs.mapboxServiceRef.current?.getMap()
      if (!map) {
        console.warn('[DemoAPI] Mapbox not initialized')
        return
      }
      const SOURCE = 'country-highlight'
      if (!map.getSource(SOURCE)) {
        map.addSource(SOURCE, { type: 'vector', url: 'mapbox://mapbox.country-boundaries-v1' })
      }
      // one polygon per country in the "US"/all worldview, as Mapbox documents it
      const filter = [
        'all',
        ['==', ['get', 'iso_3166_1'], iso2],
        ['match', ['get', 'worldview'], ['all', 'US'], true, false],
      ]
      const fade = (peak: number) => ['interpolate', ['linear'], ['zoom'], 5.5, peak, 7.5, 0]
      const before = (map.getStyle()?.layers ?? []).find((l: { type: string }) => l.type === 'symbol')?.id
      for (const id of [`${SOURCE}-fill`, `${SOURCE}-line`]) {
        if (map.getLayer(id)) map.removeLayer(id)
      }
      map.addLayer(
        {
          id: `${SOURCE}-fill`,
          type: 'fill',
          source: SOURCE,
          'source-layer': 'country_boundaries',
          filter,
          paint: { 'fill-color': color, 'fill-opacity': fade(0.28) },
        },
        before,
      )
      map.addLayer(
        {
          id: `${SOURCE}-line`,
          type: 'line',
          source: SOURCE,
          'source-layer': 'country_boundaries',
          filter,
          paint: {
            'line-color': color,
            'line-width': ['interpolate', ['linear'], ['zoom'], 2, 1.5, 6, 2.5],
            'line-opacity': fade(0.9),
          },
        },
        before,
      )
    },
    setMapboxRasterFade: (ms) => {
      const map = refs.mapboxServiceRef.current?.getMap()
      if (!map) {
        console.warn('[DemoAPI] Mapbox not initialized')
        return
      }
      ;(map.getStyle()?.layers ?? [])
        .filter((l: { id: string; type: string }) => l.type === 'raster')
        .forEach((l: { id: string }) => map.setPaintProperty(l.id, 'raster-fade-duration', ms))
    },
    mapboxTilesLoaded: () => {
      const map = refs.mapboxServiceRef.current?.getMap()
      return map ? map.areTilesLoaded() : true
    },
    mapboxWaitIdle: (timeoutMs = 15000) => {
      return new Promise<void>((resolve) => {
        const map = refs.mapboxServiceRef.current?.getMap()
        if (!map) { resolve(); return }
        const timer = setTimeout(resolve, timeoutMs)
        map.once('idle', () => { clearTimeout(timer); resolve() })
      })
    },
    getCameraState: () => {
      const scene = refs.sceneRef.current
      if (!scene) return { distance: 0, lat: 0, lng: 0, animating: false }
      const { x, y, z } = scene.camera.position
      const distance = scene.camera.position.length()
      const lat = Math.asin(y / distance) * (180 / Math.PI)
      // Inverse of useFlyToAnimation's lat/lng → direction mapping.
      const lng = Math.atan2(z, -x) * (180 / Math.PI) - 180
      return { distance, lat, lng: lng < -180 ? lng + 360 : lng, animating: refs.cameraAnimationRef.current !== null }
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
