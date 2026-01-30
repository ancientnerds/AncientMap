// =============================================================================
// MAPBOX GLOBE SERVICE - Direct Mapbox GL JS integration with globe projection
// =============================================================================

import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MAPBOX, rotateMapboxToken, getMapboxToken } from '../config/mapboxConstants'
import { applyDarkTealTheme as applyTealTheme, setupDarkFog } from '../utils/mapboxTheme'

export type MapboxTileType = 'dark' | 'satellite'
export type ColorMode = 'category' | 'age' | 'source' | 'country'

export interface MapboxSiteData {
  id: string
  longitude: number
  latitude: number
  color: string
}

// Legacy alias
export type MapboxMarkerData = MapboxSiteData

/**
 * Service that manages a Mapbox GL JS map instance with globe projection.
 * Handles all Mapbox-related state and logic to keep Globe.tsx minimal.
 */
export class MapboxGlobeService {
  private map: mapboxgl.Map | null = null
  private container: HTMLDivElement | null = null
  private currentStyle: MapboxTileType = 'dark'
  private isInitialized = false
  private isInteractive = false
  private isPrimaryMode = false
  private currentSites: MapboxSiteData[] = []
  private pendingSitesAfterStyleLoad: MapboxSiteData[] | null = null
  private currentDotSize: number = 6  // Default dot size (matches Three.js default)

  // Store current selection and measurements for restoration after style change
  private currentSelectedSites: Array<{ id: string; lng: number; lat: number }> = []
  private currentMeasurements: Array<{
    id: string
    start: [number, number]
    end: [number, number]
    color: string
    label?: string
    startSnapped?: boolean
    endSnapped?: boolean
  }> = []
  private currentSinglePoints: Array<{
    coords: [number, number]
    color: string
    snapped: boolean
  }> = []

  private wheelHandler: ((e: WheelEvent) => void) | null = null

  // Callbacks
  private siteClickCallback: ((siteId: string) => void) | null = null
  private zoomChangeCallback: ((zoomPercent: number) => void) | null = null
  private wheelZoomCallback: ((delta: number, cursorLatLng?: { lat: number; lng: number }) => void) | null = null  // Unified wheel zoom with cursor position
  private siteHoverCallback: ((siteId: string | null, x: number, y: number) => void) | null = null  // Unified hover for tooltips
  private mapClickCallback: ((lng: number, lat: number, screenX: number, screenY: number) => void) | null = null  // Unified click for measure/proximity
  private mouseMoveCallback: ((x: number, y: number) => void) | null = null  // Global mouse move for freeze timing
  private mouseLeaveCallback: (() => void) | null = null  // Called when mouse leaves map
  private cameraMoveCallback: (() => void) | null = null  // Called during camera pan/rotate/zoom for tooltip position updates

  // Cursor state - base cursor to return to when not hovering sites
  private baseCursor: 'grab' | 'crosshair' | 'default' = 'grab'

  // Style URLs for different tile types
  private static readonly STYLES: Record<MapboxTileType, string> = {
    dark: 'mapbox://styles/mapbox/dark-v11',
    satellite: 'mapbox://styles/mapbox/satellite-v9'
  }

  // Zoom range for Mapbox (full range for street-level zoom)
  // Note: geoMath.ts has separate constants for mode-switch entry point
  private static readonly ZOOM_MIN = 0.7   // Mapbox zoom at 0% (matches geoMath entry point)
  private static readonly ZOOM_MAX = 18    // Mapbox zoom at 100% (street level)

  /**
   * Initialize the Mapbox map in the given container
   */
  async initialize(container: HTMLDivElement, initialStyle: MapboxTileType = 'dark'): Promise<void> {
    if (this.isInitialized) {
      console.warn('[MapboxGlobe] Already initialized')
      return
    }

    mapboxgl.accessToken = MAPBOX.ACCESS_TOKEN
    this.container = container
    this.currentStyle = initialStyle

    this.map = new mapboxgl.Map({
      container: container,
      style: MapboxGlobeService.STYLES[initialStyle],
      projection: 'globe',
      zoom: 1.5,
      center: [0, 20],
      interactive: false, // Start non-interactive, enable when needed
      antialias: true,
      fadeDuration: 0,
      maxTileCacheSize: 200,
      trackResize: true,
      minZoom: MapboxGlobeService.ZOOM_MIN,  // Match entry point zoom
    })

    await new Promise<void>((resolve, _reject) => {
      this.map!.on('load', () => {
        console.log('[MapboxGlobe] Map loaded')
        this.setupFog()
        this.applyDarkTealTheme()
        this.setupEventListeners()
        this.isInitialized = true
        resolve()
      })

      this.map!.on('error', (e: mapboxgl.ErrorEvent & { error?: { status?: number } }) => {
        // Check for 401 unauthorized - token expired
        if (e.error?.status === 401) {
          console.warn('[MapboxGlobe] Token expired (401), rotating to next token...')
          if (rotateMapboxToken()) {
            // Update the token and reload style
            mapboxgl.accessToken = getMapboxToken()
            this.map?.setStyle(MapboxGlobeService.STYLES[this.currentStyle])
          } else {
            console.error('[MapboxGlobe] All tokens exhausted, cannot recover')
          }
        } else {
          console.error('[MapboxGlobe] Map error:', e)
        }
      })
    })
  }

  private setupFog(): void {
    if (!this.map) return
    setupDarkFog(this.map)
  }

  /**
   * Apply teal color scheme to dark map (matches Three.js globe)
   * Only applies to dark style, not satellite
   */
  private applyDarkTealTheme(): void {
    if (!this.map || this.currentStyle !== 'dark') return
    applyTealTheme(this.map)
    console.log('[MapboxGlobe] Applied dark teal theme')
  }

  private setupEventListeners(): void {
    if (!this.map) return

    // Track zoom changes when interactive
    this.map.on('zoomend', () => {
      if (this.isInteractive && this.zoomChangeCallback) {
        const zoomPercent = this.mapboxZoomToPercent(this.map!.getZoom())
        this.zoomChangeCallback(zoomPercent)
      }
    })

    // Map click handler for measure/proximity (unified with Three.js)
    this.map.on('click', (e) => {
      if (this.isInteractive && this.mapClickCallback) {
        this.mapClickCallback(e.lngLat.lng, e.lngLat.lat, e.point.x, e.point.y)
      }
    })

    // Global mousemove handler for freeze timing (tracks cursor movement everywhere)
    this.map.on('mousemove', (e) => {
      if (this.isInteractive && this.mouseMoveCallback) {
        this.mouseMoveCallback(e.point.x, e.point.y)
      }
    })

    // Mouse leave handler - clear coordinates when mouse leaves map
    this.map.on('mouseout', () => {
      if (this.isInteractive && this.mouseLeaveCallback) {
        this.mouseLeaveCallback()
      }
    })

    // Camera move handler - called during pan/rotate/zoom for tooltip position updates
    this.map.on('move', () => {
      if (this.isInteractive && this.cameraMoveCallback) {
        this.cameraMoveCallback()
      }
    })
  }

  // =========================================================================
  // PRIMARY MODE - When Mapbox is the main interactive globe
  // =========================================================================

  /**
   * Enable primary mode - Mapbox becomes the main interactive globe
   * Wheel zoom is handled via unified slider callback (no Mapbox internal zoom)
   */
  enablePrimaryMode(): void {
    if (!this.map || !this.isInitialized || this.isPrimaryMode) return

    this.isPrimaryMode = true
    this.setInteractive(true)

    // Set up wheel handler that routes to unified zoom slider
    // Mapbox's scrollZoom is disabled - we handle it ourselves for consistency
    if (this.container && !this.wheelHandler) {
      this.wheelHandler = (e: WheelEvent) => {
        e.preventDefault()
        e.stopPropagation()

        if (this.wheelZoomCallback && this.map) {
          // Convert wheel delta to zoom direction: negative = zoom in, positive = zoom out
          const delta = e.deltaY > 0 ? -1 : 1  // Invert: wheel down = zoom out = decrease %

          // Get cursor position relative to map container and convert to lat/lng
          const rect = this.container!.getBoundingClientRect()
          const x = e.clientX - rect.left
          const y = e.clientY - rect.top
          const lngLat = this.map.unproject([x, y])

          this.wheelZoomCallback(delta, { lat: lngLat.lat, lng: lngLat.lng })
        }
      }
      this.container.addEventListener('wheel', this.wheelHandler, { passive: false })
    }

    // Visibility/opacity handled by CSS via mapbox-primary-mode class
    document.body.classList.add('mapbox-primary-mode')

    console.log('[MapboxGlobe] Primary mode enabled (wheel zoom via unified slider)')
  }

  /**
   * Disable primary mode - return to Three.js control
   */
  disablePrimaryMode(): void {
    if (!this.isPrimaryMode) return

    this.isPrimaryMode = false
    this.setInteractive(false)
    document.body.classList.remove('mapbox-primary-mode')

    // Remove wheel event handler
    if (this.container && this.wheelHandler) {
      this.container.removeEventListener('wheel', this.wheelHandler)
      this.wheelHandler = null
    }

    console.log('[MapboxGlobe] Primary mode disabled')
  }

  /**
   * Check if in primary mode
   */
  getIsPrimaryMode(): boolean {
    return this.isPrimaryMode
  }

  // =========================================================================
  // ZOOM CONTROL
  // =========================================================================

  /**
   * Set zoom using 0-100 percentage (same scale as Three.js zoom slider)
   */
  setZoomPercent(percent: number): void {
    if (!this.map || !this.isInitialized) return

    const mapboxZoom = this.percentToMapboxZoom(percent)
    this.map.setZoom(mapboxZoom)
  }

  /**
   * Set zoom using percentage, zooming towards a specific point (zoom-at-cursor)
   * The point under cursorLatLng will stay in the same screen position
   */
  setZoomPercentAtPoint(percent: number, cursorLatLng: { lat: number; lng: number }): void {
    if (!this.map || !this.isInitialized) return

    const mapboxZoom = this.percentToMapboxZoom(percent)
    const currentZoom = this.map.getZoom()
    const currentCenter = this.map.getCenter()

    // Calculate how much the center should shift towards the cursor
    // When zooming in, center moves towards cursor; when zooming out, away from cursor
    const zoomFactor = 1 - Math.pow(2, currentZoom - mapboxZoom)

    const newLng = currentCenter.lng + (cursorLatLng.lng - currentCenter.lng) * zoomFactor
    const newLat = currentCenter.lat + (cursorLatLng.lat - currentCenter.lat) * zoomFactor

    this.map.jumpTo({
      center: [newLng, newLat],
      zoom: mapboxZoom
    })
  }

  /**
   * Get current zoom as 0-100 percentage
   */
  getZoomPercent(): number {
    if (!this.map || !this.isInitialized) return 0
    return this.mapboxZoomToPercent(this.map.getZoom())
  }

  /**
   * Set callback for zoom changes (in primary mode)
   * DEPRECATED: Use onWheelZoom instead for unified zoom control
   */
  onZoomChange(callback: ((zoomPercent: number) => void) | null): void {
    this.zoomChangeCallback = callback
  }

  /**
   * Set callback for wheel zoom events (unified with slider)
   * delta: +1 = zoom in, -1 = zoom out
   * cursorLatLng: lat/lng under cursor for zoom-at-cursor behavior
   */
  onWheelZoom(callback: ((delta: number, cursorLatLng?: { lat: number; lng: number }) => void) | null): void {
    this.wheelZoomCallback = callback
  }

  private percentToMapboxZoom(percent: number): number {
    // 0% = ZOOM_MIN, 100% = ZOOM_MAX (full street-level range)
    return MapboxGlobeService.ZOOM_MIN + (percent / 100) * (MapboxGlobeService.ZOOM_MAX - MapboxGlobeService.ZOOM_MIN)
  }

  private mapboxZoomToPercent(mapboxZoom: number): number {
    const percent = ((mapboxZoom - MapboxGlobeService.ZOOM_MIN) / (MapboxGlobeService.ZOOM_MAX - MapboxGlobeService.ZOOM_MIN)) * 100
    return Math.max(0, Math.min(100, Math.round(percent)))
  }

  // =========================================================================
  // CAMERA CONTROL
  // =========================================================================

  /**
   * Set camera position (for syncing from Three.js)
   */
  setCamera(lat: number, lng: number, zoom: number, bearing: number = 0, pitch: number = 0): void {
    if (!this.map || !this.isInitialized) return

    this.map.jumpTo({
      center: [lng, lat],
      zoom: zoom,
      bearing: bearing,
      pitch: pitch
    })
  }

  /**
   * Animate to a new camera position
   */
  easeTo(lat: number, lng: number, zoom: number, bearing: number = 0, pitch: number = 0, duration: number = 300): void {
    if (!this.map || !this.isInitialized) return

    this.map.easeTo({
      center: [lng, lat],
      zoom: zoom,
      bearing: bearing,
      pitch: pitch,
      duration: duration
    })
  }

  /**
   * Fly to coordinates without changing zoom level
   */
  flyTo(lat: number, lng: number, duration: number = 600): void {
    if (!this.map || !this.isInitialized) return

    this.map.easeTo({
      center: [lng, lat],
      duration: duration
    })
  }

  /**
   * Get current camera state
   */
  getCamera(): { lat: number; lng: number; zoom: number; bearing: number; pitch: number } | null {
    if (!this.map || !this.isInitialized) return null

    const center = this.map.getCenter()
    return {
      lat: center.lat,
      lng: center.lng,
      zoom: this.map.getZoom(),
      bearing: this.map.getBearing(),
      pitch: this.map.getPitch()
    }
  }

  // =========================================================================
  // BOUNDS-BASED CAMERA CONTROL (for screen coordinate sync)
  // =========================================================================

  /**
   * Fit map to show specific geographic bounds
   * This is the key method for syncing visible area from Three.js
   */
  fitToBounds(
    bounds: [[number, number], [number, number]] | null,
    center?: [number, number]
  ): void {
    if (!this.map || !this.isInitialized) return

    if (bounds) {
      // bounds format: [[sw_lng, sw_lat], [ne_lng, ne_lat]]
      this.map.fitBounds(bounds, {
        padding: 0,
        duration: 0,
        maxZoom: 18
      })
    } else if (center) {
      // Fallback when bounds unavailable (zoomed way out, corners miss globe)
      this.map.jumpTo({ center, zoom: 1.5 })
    }
  }

  /**
   * Get current visible bounds from Mapbox
   * This is the key method for syncing visible area to Three.js
   */
  getVisibleBounds(): {
    center: [number, number];
    bounds: [[number, number], [number, number]]
  } {
    const mapBounds = this.map!.getBounds()
    const center = this.map!.getCenter()
    return {
      center: [center.lng, center.lat],
      bounds: [
        [mapBounds!.getWest(), mapBounds!.getSouth()], // SW
        [mapBounds!.getEast(), mapBounds!.getNorth()]  // NE
      ]
    }
  }

  // =========================================================================
  // STYLE CONTROL
  // =========================================================================

  /**
   * Set the map style (dark or satellite)
   * All layers will be automatically restored after style loads
   */
  setStyle(style: MapboxTileType): void {
    if (!this.map || !this.isInitialized) return
    if (style === this.currentStyle) return

    // Save current sites to restore after style change
    if (this.currentSites.length > 0) {
      this.pendingSitesAfterStyleLoad = [...this.currentSites]
    }

    // Selection rings and measurements are already stored in currentSelectedSites/currentMeasurements

    this.currentStyle = style
    this.map.setStyle(MapboxGlobeService.STYLES[style])

    // Restore fog, theme, sites, selection rings, and measurements after style loads
    this.map.once('style.load', () => {
      this.setupFog()
      this.applyDarkTealTheme()

      // Restore sites layer if we had one
      if (this.pendingSitesAfterStyleLoad) {
        this.addSitesLayerInternal(this.pendingSitesAfterStyleLoad)
        this.pendingSitesAfterStyleLoad = null
      }

      // Restore selection rings if we had any
      if (this.currentSelectedSites.length > 0) {
        this.setSelectedSites(this.currentSelectedSites)
      }

      // Restore measurements if we had any
      if (this.currentMeasurements.length > 0 || this.currentSinglePoints.length > 0) {
        this.setMeasurementLines(this.currentMeasurements, this.currentSinglePoints)
      }
    })
  }

  getStyle(): MapboxTileType {
    return this.currentStyle
  }

  // =========================================================================
  // VISIBILITY & INTERACTIVITY
  // =========================================================================

  setVisible(visible: boolean): void {
    if (this.container) {
      this.container.style.visibility = visible ? 'visible' : 'hidden'
    }
  }

  private setInteractive(interactive: boolean): void {
    if (!this.map || !this.isInitialized) return
    if (this.isInteractive === interactive) return

    this.isInteractive = interactive

    if (interactive) {
      // NOTE: scrollZoom is DISABLED - we handle wheel events ourselves
      // to keep zoom in sync with the unified slider (no duplicate zoom systems)
      this.map.scrollZoom.disable()
      this.map.boxZoom.enable()
      this.map.dragRotate.enable()
      this.map.dragPan.enable()
      this.map.keyboard.enable()
      this.map.doubleClickZoom.disable()  // Also disable - use unified zoom
      this.map.touchZoomRotate.enable()
      this.map.touchPitch.enable()
    } else {
      this.map.scrollZoom.disable()
      this.map.boxZoom.disable()
      this.map.dragRotate.disable()
      this.map.dragPan.disable()
      this.map.keyboard.disable()
      this.map.doubleClickZoom.disable()
      this.map.touchZoomRotate.disable()
      this.map.touchPitch.disable()
    }
  }

  getInteractive(): boolean {
    return this.isInteractive
  }

  resize(): void {
    if (this.map && this.isInitialized) {
      this.map.resize()
      // Update dot sizes to match new resolution
      this.setDotSize(this.currentDotSize)
    }
  }

  // =========================================================================
  // SITES LAYER (GPU-accelerated circles)
  // =========================================================================

  /**
   * Set callback for site clicks
   */
  onSiteClick(callback: ((siteId: string) => void) | null): void {
    this.siteClickCallback = callback
  }

  /**
   * Set callback for site hover (unified with Three.js tooltip system)
   * Called with siteId and cursor position when hovering, null when not
   */
  onSiteHover(callback: ((siteId: string | null, x: number, y: number) => void) | null): void {
    this.siteHoverCallback = callback
  }

  /**
   * Set callback for map clicks (unified with Three.js measure/proximity)
   * Called with lng/lat and screen coords when clicking anywhere on map (not just sites)
   */
  onMapClick(callback: ((lng: number, lat: number, screenX: number, screenY: number) => void) | null): void {
    this.mapClickCallback = callback
  }

  /**
   * Set callback for global mouse move (for freeze timing)
   * Called with screen coordinates whenever mouse moves on the map
   */
  onMouseMove(callback: ((x: number, y: number) => void) | null): void {
    this.mouseMoveCallback = callback
  }

  /**
   * Set callback for when mouse leaves the map
   * Used to clear coordinates display
   */
  onMouseLeave(callback: (() => void) | null): void {
    this.mouseLeaveCallback = callback
  }

  /**
   * Set callback for camera move events (pan/rotate/zoom)
   * Used to update frozen tooltip positions during camera movement
   */
  onCameraMove(callback: (() => void) | null): void {
    this.cameraMoveCallback = callback
  }

  /**
   * Set cursor style on the Mapbox canvas
   * Use 'crosshair' for measure/proximity mode, 'grab' for normal mode
   * This becomes the "base" cursor that's restored when not hovering over sites
   */
  setCursor(cursor: 'grab' | 'crosshair' | 'default'): void {
    if (!this.map) return
    this.baseCursor = cursor
    this.map.getCanvas().style.cursor = cursor
  }

  /**
   * Add or update sites layer
   * Uses in-place data updates when source already exists to avoid layer flash
   */
  setSites(sites: MapboxSiteData[]): void {
    if (!this.map || !this.isInitialized) return

    this.currentSites = sites

    // Check if source already exists - update in place to avoid flash
    const source = this.map.getSource('sites') as mapboxgl.GeoJSONSource
    if (source) {
      const geojson = this.sitesToGeoJSON(sites)
      source.setData(geojson)
    } else {
      // First time - create the layers
      this.addSitesLayerInternal(sites)
    }
  }

  /**
   * Update colors of existing sites without recreating the layer
   */
  updateSiteColors(sites: MapboxSiteData[]): void {
    if (!this.map || !this.isInitialized) return

    this.currentSites = sites

    const source = this.map.getSource('sites') as mapboxgl.GeoJSONSource
    if (source) {
      // Update the data in place
      const geojson = this.sitesToGeoJSON(sites)
      source.setData(geojson)
    } else {
      // Layer doesn't exist, create it
      this.addSitesLayerInternal(sites)
    }
  }

  /**
   * Clear sites layer
   */
  clearSites(): void {
    if (!this.map) return

    this.currentSites = []

    if (this.map.getLayer('sites-circles')) {
      this.map.removeLayer('sites-circles')
    }
    if (this.map.getLayer('sites-shadow')) {
      this.map.removeLayer('sites-shadow')
    }
    if (this.map.getSource('sites')) {
      this.map.removeSource('sites')
    }
  }

  /**
   * Set selected sites to show green selection rings around
   * Matches the green pulsing ring style from 3D globe
   * Uses in-place data updates to avoid layer flicker
   */
  setSelectedSites(sites: Array<{ id: string; lng: number; lat: number }>): void {
    // Store for restoration after style change
    this.currentSelectedSites = [...sites]

    if (!this.map || !this.isInitialized) return

    // Create GeoJSON for selection points
    const geojson: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: sites.map(site => ({
        type: 'Feature' as const,
        properties: { id: site.id },
        geometry: { type: 'Point' as const, coordinates: [site.lng, site.lat] }
      }))
    }

    // Update existing source data instead of remove/recreate cycle
    // This prevents the flash/flicker when clicking sites
    const source = this.map.getSource('selection-rings') as mapboxgl.GeoJSONSource
    if (source) {
      source.setData(geojson)
    } else {
      // Only create layer if it doesn't exist
      this.map.addSource('selection-rings', {
        type: 'geojson',
        data: geojson
      })

      // Add green ring layer (matches 3D globe style: lime green #32CD32)
      this.map.addLayer({
        id: 'selection-rings',
        type: 'circle',
        source: 'selection-rings',
        paint: {
          'circle-radius': 14,
          'circle-color': 'rgba(0,0,0,0)',
          'circle-stroke-color': '#32CD32',
          'circle-stroke-width': 3,
          'circle-opacity': 1
        }
      })
    }
  }

  /**
   * Clear selection rings
   */
  clearSelectedSites(): void {
    this.currentSelectedSites = []

    if (!this.map) return

    if (this.map.getLayer('selection-rings')) {
      this.map.removeLayer('selection-rings')
    }
    if (this.map.getSource('selection-rings')) {
      this.map.removeSource('selection-rings')
    }
  }

  /**
   * Project lng/lat to screen coordinates
   * Returns null if map not initialized
   */
  projectToScreen(lng: number, lat: number): { x: number; y: number } | null {
    if (!this.map || !this.isInitialized) return null
    const point = this.map.project([lng, lat])
    return { x: point.x, y: point.y }
  }

  /**
   * Unproject screen coordinates to lat/lng
   * Returns null if map not initialized or point is invalid
   */
  unprojectToLatLng(x: number, y: number): { lat: number; lng: number } | null {
    if (!this.map || !this.isInitialized) return null
    try {
      const lngLat = this.map.unproject([x, y])
      return { lat: lngLat.lat, lng: lngLat.lng }
    } catch {
      return null
    }
  }

  /**
   * Calculate scale bar based on actual screen distance measurement
   * Uses two points on screen and measures their geographic distance
   * Works correctly for globe projection (not just Web Mercator)
   */
  getScaleBar(): { km: number; pixels: number } | null {
    if (!this.map || !this.isInitialized) return null

    // Get center of the map
    const canvas = this.map.getCanvas()
    const centerX = canvas.width / 2
    const centerY = canvas.height / 2

    // Test with 100 pixels horizontal distance from center
    const testPixels = 100
    const p1 = this.map.unproject([centerX - testPixels / 2, centerY])
    const p2 = this.map.unproject([centerX + testPixels / 2, centerY])

    if (!p1 || !p2) return null

    // Calculate actual geographic distance using Haversine formula
    const R = 6371 // Earth radius in km
    const lat1 = p1.lat * Math.PI / 180
    const lat2 = p2.lat * Math.PI / 180
    const dLat = (p2.lat - p1.lat) * Math.PI / 180
    const dLng = (p2.lng - p1.lng) * Math.PI / 180

    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1) * Math.cos(lat2) *
              Math.sin(dLng / 2) * Math.sin(dLng / 2)
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
    const distanceKm = R * c

    // km per pixel
    const kmPerPixel = distanceKm / testPixels

    // Target ~100-150 pixel bar width
    const targetPixels = 120
    const targetKm = kmPerPixel * targetPixels

    // Round to nice values
    const niceValues = [
      0.001, 0.002, 0.005, // meters
      0.01, 0.02, 0.05,    // 10m, 20m, 50m
      0.1, 0.2, 0.5,       // 100m, 200m, 500m
      1, 2, 5,             // 1km, 2km, 5km
      10, 20, 50,          // 10km, 20km, 50km
      100, 200, 500,       // 100km, 200km, 500km
      1000, 2000, 5000     // 1000km, 2000km, 5000km
    ]

    let bestKm = niceValues[0]
    for (const km of niceValues) {
      if (km <= targetKm * 1.5) bestKm = km
    }

    const barPixels = bestKm / kmPerPixel
    if (barPixels > 15 && barPixels < 400 && !isNaN(barPixels)) {
      return { km: bestKm, pixels: Math.round(barPixels) }
    }

    return null
  }

  /**
   * Set dot size (1-15 range, matches Three.js slider)
   * Updates existing layer if present
   */
  setDotSize(size: number): void {
    this.currentDotSize = size

    if (!this.map || !this.isInitialized) return

    // Scale by viewport height (reference: 1080p) so dots appear same visual size on all resolutions
    // Mapbox handles devicePixelRatio internally, so we only scale by resolution
    const resolutionScale = window.innerHeight / 1080
    const baseRadius = size * 0.8 * resolutionScale
    const shadowRadius = baseRadius * 1.6  // Shadow 60% larger than dot
    const shadowOffset = Math.max(2, size * 0.4 * resolutionScale)  // Shadow offset scales with size

    // Update main circles layer
    if (this.map.getLayer('sites-circles')) {
      this.map.setPaintProperty('sites-circles', 'circle-radius', [
        'interpolate', ['linear'], ['zoom'],
        0, baseRadius,
        5, baseRadius * 1.2,
        10, baseRadius * 1.5,
        15, baseRadius * 2
      ])
    }

    // Update shadow layer - size and offset scale with dot size
    if (this.map.getLayer('sites-shadow')) {
      this.map.setPaintProperty('sites-shadow', 'circle-radius', [
        'interpolate', ['linear'], ['zoom'],
        0, shadowRadius,
        5, shadowRadius * 1.2,
        10, shadowRadius * 1.5,
        15, shadowRadius * 2
      ])
      this.map.setPaintProperty('sites-shadow', 'circle-translate', [shadowOffset, shadowOffset])
    }
  }

  /**
   * Get current dot size
   */
  getDotSize(): number {
    return this.currentDotSize
  }

  private sitesToGeoJSON(sites: MapboxSiteData[]): GeoJSON.FeatureCollection {
    return {
      type: 'FeatureCollection',
      features: sites.map(site => ({
        type: 'Feature' as const,
        properties: {
          id: site.id,
          color: site.color
        },
        geometry: {
          type: 'Point' as const,
          coordinates: [site.longitude, site.latitude]
        }
      }))
    }
  }

  private addSitesLayerInternal(sites: MapboxSiteData[]): void {
    if (!this.map) return

    // Clear existing layers
    if (this.map.getLayer('sites-circles')) {
      this.map.removeLayer('sites-circles')
    }
    if (this.map.getLayer('sites-shadow')) {
      this.map.removeLayer('sites-shadow')
    }
    if (this.map.getSource('sites')) {
      this.map.removeSource('sites')
    }

    if (sites.length === 0) return

    // Scale by viewport height (reference: 1080p) so dots appear same visual size on all resolutions
    // Mapbox handles devicePixelRatio internally, so we only scale by resolution
    const resolutionScale = window.innerHeight / 1080
    // Base size that scales with dotSize slider (1-15 range)
    const baseRadius = this.currentDotSize * 0.8 * resolutionScale
    const shadowRadius = baseRadius * 1.6  // Shadow 60% larger than dot
    const shadowOffset = Math.max(2, this.currentDotSize * 0.4 * resolutionScale)  // Shadow offset scales with size

    // Add source
    this.map.addSource('sites', {
      type: 'geojson',
      data: this.sitesToGeoJSON(sites)
    })

    // Shadow layer (rendered first, underneath) - soft blur offset
    this.map.addLayer({
      id: 'sites-shadow',
      type: 'circle',
      source: 'sites',
      paint: {
        'circle-radius': [
          'interpolate', ['linear'], ['zoom'],
          0, shadowRadius,
          5, shadowRadius * 1.2,
          10, shadowRadius * 1.5,
          15, shadowRadius * 2
        ],
        'circle-color': '#000000',
        'circle-opacity': 0.6,
        'circle-blur': 1,
        'circle-translate': [shadowOffset, shadowOffset]
      }
    })

    // Main crisp circle layer - no stroke, 70% opacity to match Three.js dots
    this.map.addLayer({
      id: 'sites-circles',
      type: 'circle',
      source: 'sites',
      paint: {
        'circle-radius': [
          'interpolate', ['linear'], ['zoom'],
          0, baseRadius,
          5, baseRadius * 1.2,
          10, baseRadius * 1.5,
          15, baseRadius * 2
        ],
        'circle-color': ['get', 'color'],
        'circle-opacity': 0.7,
        'circle-blur': 0  // Crisp edges, no stroke
      }
    })

    // Click handler
    this.map.on('click', 'sites-circles', (e) => {
      if (e.features && e.features.length > 0 && this.siteClickCallback) {
        const siteId = e.features[0].properties?.id
        if (siteId) {
          this.siteClickCallback(siteId)
        }
      }
    })

    // Hover handler for tooltips - reports siteId and cursor position
    this.map.on('mousemove', 'sites-circles', (e) => {
      if (this.map) this.map.getCanvas().style.cursor = 'pointer'
      if (e.features && e.features.length > 0 && this.siteHoverCallback) {
        const siteId = e.features[0].properties?.id
        if (siteId) {
          this.siteHoverCallback(siteId, e.point.x, e.point.y)
        }
      }
    })

    this.map.on('mouseleave', 'sites-circles', () => {
      // Reset to base cursor (grab or crosshair depending on mode)
      if (this.map) this.map.getCanvas().style.cursor = this.baseCursor
      // Report null to clear tooltip
      if (this.siteHoverCallback) {
        this.siteHoverCallback(null, 0, 0)
      }
    })

    console.log(`[MapboxGlobe] Added ${sites.length} sites with size ${this.currentDotSize}`)
  }

  // Legacy compatibility
  addMarkers(sites: MapboxSiteData[]): void {
    this.setSites(sites)
  }

  clearMarkers(): void {
    this.clearSites()
  }

  // =========================================================================
  // MEASUREMENT OVERLAYS (lines and markers)
  // =========================================================================

  /**
   * Set measurement lines to display on the map
   * Each measurement has start/end coords, color, and optional label
   */
  setMeasurementLines(
    measurements: Array<{
      id: string
      start: [number, number]  // [lng, lat]
      end: [number, number]    // [lng, lat]
      color: string            // hex color
      label?: string           // distance label text
      startSnapped?: boolean   // true = ring marker, false = filled circle
      endSnapped?: boolean     // true = ring marker, false = filled circle
    }>,
    singlePoints?: Array<{     // Optional standalone points (e.g., first point of in-progress measurement)
      coords: [number, number]
      color: string
      snapped: boolean
    }>
  ): void {
    // Store for restoration after style change
    this.currentMeasurements = measurements.map(m => ({ ...m }))
    this.currentSinglePoints = singlePoints ? singlePoints.map(p => ({ ...p })) : []

    if (!this.map || !this.isInitialized) return

    console.log('[Mapbox] setMeasurementLines called:', { measurements: measurements.length, singlePoints: singlePoints?.length ?? 0 })
    if (measurements.length > 0) console.log('[Mapbox] First measurement:', measurements[0])
    if (singlePoints && singlePoints.length > 0) console.log('[Mapbox] Single points:', singlePoints)

    // Remove existing layers and source
    if (this.map.getLayer('measurement-labels')) {
      this.map.removeLayer('measurement-labels')
    }
    if (this.map.getLayer('measurement-lines')) {
      this.map.removeLayer('measurement-lines')
    }
    if (this.map.getLayer('measurement-points-filled')) {
      this.map.removeLayer('measurement-points-filled')
    }
    if (this.map.getLayer('measurement-points-ring')) {
      this.map.removeLayer('measurement-points-ring')
    }
    if (this.map.getSource('measurements')) {
      this.map.removeSource('measurements')
    }

    if (measurements.length === 0 && (!singlePoints || singlePoints.length === 0)) return

    // Create GeoJSON for lines
    const lineFeatures: GeoJSON.Feature[] = measurements.map(m => ({
      type: 'Feature',
      properties: { id: m.id, color: m.color },
      geometry: {
        type: 'LineString',
        coordinates: [m.start, m.end]
      }
    }))

    // Create GeoJSON for endpoints (markers) with snapped info
    const pointFeatures: GeoJSON.Feature[] = []
    measurements.forEach(m => {
      pointFeatures.push({
        type: 'Feature',
        properties: { id: m.id + '-start', color: m.color, snapped: m.startSnapped ?? false },
        geometry: { type: 'Point', coordinates: m.start }
      })
      pointFeatures.push({
        type: 'Feature',
        properties: { id: m.id + '-end', color: m.color, snapped: m.endSnapped ?? false },
        geometry: { type: 'Point', coordinates: m.end }
      })
    })

    // Add standalone single points (e.g., first point of in-progress measurement)
    if (singlePoints) {
      singlePoints.forEach((p, i) => {
        pointFeatures.push({
          type: 'Feature',
          properties: { id: `single-${i}`, color: p.color, snapped: p.snapped },
          geometry: { type: 'Point', coordinates: p.coords }
        })
      })
    }

    // Create GeoJSON for labels at midpoints
    const labelFeatures: GeoJSON.Feature[] = measurements
      .filter(m => m.label)
      .map(m => {
        // Calculate midpoint
        const midLng = (m.start[0] + m.end[0]) / 2
        const midLat = (m.start[1] + m.end[1]) / 2
        return {
          type: 'Feature' as const,
          properties: { id: m.id + '-label', label: m.label, color: m.color },
          geometry: { type: 'Point' as const, coordinates: [midLng, midLat] }
        }
      })

    console.log('[Mapbox] Point features:', pointFeatures.map(f => ({ coords: f.geometry, snapped: f.properties?.snapped })))

    // Add source with lines, points, and labels
    this.map.addSource('measurements', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: [...lineFeatures, ...pointFeatures, ...labelFeatures]
      }
    })

    // Add line layer
    this.map.addLayer({
      id: 'measurement-lines',
      type: 'line',
      source: 'measurements',
      filter: ['==', ['geometry-type'], 'LineString'],
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 2,
        'line-opacity': 0.8
      }
    })

    // Add square markers for non-snapped points (using text symbol with square character)
    this.map.addLayer({
      id: 'measurement-points-filled',
      type: 'symbol',
      source: 'measurements',
      filter: ['all',
        ['==', ['geometry-type'], 'Point'],
        ['!', ['has', 'label']],
        ['!=', ['coalesce', ['get', 'snapped'], false], true]
      ],
      layout: {
        'text-field': '■',  // Unicode filled square
        'text-size': 14,
        'text-allow-overlap': true
      },
      paint: {
        'text-color': ['get', 'color'],
        'text-halo-color': '#ffffff',
        'text-halo-width': 2,
        'text-opacity': 1
      }
    })

    // Add ring markers for snapped points (hollow circle with colored stroke)
    // Size matches the green selection ring style (12px radius, 3px stroke)
    this.map.addLayer({
      id: 'measurement-points-ring',
      type: 'circle',
      source: 'measurements',
      filter: ['all',
        ['==', ['geometry-type'], 'Point'],
        ['!', ['has', 'label']],
        ['==', ['coalesce', ['get', 'snapped'], false], true]
      ],
      paint: {
        'circle-radius': 12,
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-color': ['get', 'color'],
        'circle-stroke-width': 3,
        'circle-opacity': 1
      }
    })

    // Add label layer (symbol layer for text)
    if (labelFeatures.length > 0) {
      this.map.addLayer({
        id: 'measurement-labels',
        type: 'symbol',
        source: 'measurements',
        filter: ['has', 'label'],
        layout: {
          'text-field': ['get', 'label'],
          'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
          'text-size': 14,
          'text-anchor': 'center',
          'text-allow-overlap': true
        },
        paint: {
          'text-color': '#000000',
          'text-halo-color': ['get', 'color'],
          'text-halo-width': 2
        }
      })
    }
  }

  /**
   * Clear all measurement overlays
   */
  clearMeasurements(): void {
    this.currentMeasurements = []
    this.currentSinglePoints = []

    if (!this.map) return

    if (this.map.getLayer('measurement-labels')) {
      this.map.removeLayer('measurement-labels')
    }
    if (this.map.getLayer('measurement-lines')) {
      this.map.removeLayer('measurement-lines')
    }
    if (this.map.getLayer('measurement-points-filled')) {
      this.map.removeLayer('measurement-points-filled')
    }
    if (this.map.getLayer('measurement-points-ring')) {
      this.map.removeLayer('measurement-points-ring')
    }
    if (this.map.getSource('measurements')) {
      this.map.removeSource('measurements')
    }
  }

  /**
   * Find nearest snap target within given pixel radius
   * Checks both sites and measurement points
   * Returns [lng, lat] if found, null otherwise
   */
  findSnapTarget(
    clickX: number,
    clickY: number,
    maxDistPx: number,
    measurementPoints: Array<[number, number]>  // [lng, lat] coords to check
  ): [number, number] | null {
    if (!this.map) return null

    let nearestCoords: [number, number] | null = null
    let nearestDist = Infinity

    // Helper to check a point
    const checkPoint = (lng: number, lat: number) => {
      const screenPos = this.map!.project([lng, lat])
      const dx = screenPos.x - clickX
      const dy = screenPos.y - clickY
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (dist < maxDistPx && dist < nearestDist) {
        nearestDist = dist
        nearestCoords = [lng, lat]
      }
    }

    // Check all sites
    for (const site of this.currentSites) {
      checkPoint(site.longitude, site.latitude)
    }

    // Check measurement points
    for (const [lng, lat] of measurementPoints) {
      checkPoint(lng, lat)
    }

    return nearestCoords
  }

  // =========================================================================
  // PROXIMITY CIRCLE OVERLAY
  // =========================================================================

  /**
   * Set proximity circle to display on the map
   * Center is [lng, lat], radius is in kilometers
   */
  setProximityCircle(center: [number, number] | null, radiusKm: number = 100): void {
    if (!this.map || !this.isInitialized) return

    // Remove existing layers and source
    if (this.map.getLayer('proximity-circle-fill')) {
      this.map.removeLayer('proximity-circle-fill')
    }
    if (this.map.getLayer('proximity-circle-stroke')) {
      this.map.removeLayer('proximity-circle-stroke')
    }
    if (this.map.getLayer('proximity-center')) {
      this.map.removeLayer('proximity-center')
    }
    if (this.map.getSource('proximity')) {
      this.map.removeSource('proximity')
    }

    if (!center) return

    // Generate circle polygon (64 points)
    const circleCoords = this.generateCircleCoords(center, radiusKm, 64)

    // Add source
    this.map.addSource('proximity', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Polygon',
              coordinates: [circleCoords]
            }
          },
          {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Point',
              coordinates: center
            }
          }
        ]
      }
    })

    // Add fill layer (subtle red fill)
    this.map.addLayer({
      id: 'proximity-circle-fill',
      type: 'fill',
      source: 'proximity',
      filter: ['==', '$type', 'Polygon'],
      paint: {
        'fill-color': '#ff4444',
        'fill-opacity': 0.1
      }
    })

    // Add stroke layer (bright red outline)
    this.map.addLayer({
      id: 'proximity-circle-stroke',
      type: 'line',
      source: 'proximity',
      filter: ['==', '$type', 'Polygon'],
      paint: {
        'line-color': '#ff4444',
        'line-width': 2,
        'line-opacity': 0.8
      }
    })

    // Add center point marker (red dot with white outline)
    this.map.addLayer({
      id: 'proximity-center',
      type: 'circle',
      source: 'proximity',
      filter: ['==', '$type', 'Point'],
      paint: {
        'circle-radius': 6,
        'circle-color': '#ff4444',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2
      }
    })
  }

  /**
   * Clear proximity circle overlay
   */
  clearProximityCircle(): void {
    if (!this.map) return

    if (this.map.getLayer('proximity-circle-fill')) {
      this.map.removeLayer('proximity-circle-fill')
    }
    if (this.map.getLayer('proximity-circle-stroke')) {
      this.map.removeLayer('proximity-circle-stroke')
    }
    if (this.map.getLayer('proximity-center')) {
      this.map.removeLayer('proximity-center')
    }
    if (this.map.getSource('proximity')) {
      this.map.removeSource('proximity')
    }
  }

  /**
   * Generate circle coordinates using Haversine formula
   */
  private generateCircleCoords(center: [number, number], radiusKm: number, numPoints: number): number[][] {
    const coords: number[][] = []
    const [lng, lat] = center
    const earthRadiusKm = 6371

    for (let i = 0; i <= numPoints; i++) {
      const bearing = (i / numPoints) * 2 * Math.PI
      const latRad = lat * Math.PI / 180
      const lngRad = lng * Math.PI / 180
      const angularDistance = radiusKm / earthRadiusKm

      const newLatRad = Math.asin(
        Math.sin(latRad) * Math.cos(angularDistance) +
        Math.cos(latRad) * Math.sin(angularDistance) * Math.cos(bearing)
      )
      const newLngRad = lngRad + Math.atan2(
        Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latRad),
        Math.cos(angularDistance) - Math.sin(latRad) * Math.sin(newLatRad)
      )

      coords.push([
        newLngRad * 180 / Math.PI,
        newLatRad * 180 / Math.PI
      ])
    }

    return coords
  }

  // =========================================================================
  // UTILITY
  // =========================================================================

  getMap(): mapboxgl.Map | null {
    return this.map
  }

  getIsInitialized(): boolean {
    return this.isInitialized
  }

  dispose(): void {
    this.clearSites()
    this.siteClickCallback = null
    this.zoomChangeCallback = null
    this.wheelZoomCallback = null
    this.siteHoverCallback = null
    this.mapClickCallback = null
    this.mouseMoveCallback = null
    this.mouseLeaveCallback = null
    this.cameraMoveCallback = null
    this.pendingSitesAfterStyleLoad = null
    this.currentSelectedSites = []
    this.currentMeasurements = []
    this.currentSinglePoints = []
    document.body.classList.remove('mapbox-primary-mode')

    if (this.map) {
      this.map.remove()
      this.map = null
    }
    this.container = null
    this.isInitialized = false
    this.isInteractive = false
    this.isPrimaryMode = false
  }
}

/**
 * Convert Three.js camera position to Mapbox camera parameters
 */
export function threeJsCameraToMapbox(
  cameraPosition: { x: number; y: number; z: number },
  cameraTarget: { x: number; y: number; z: number } = { x: 0, y: 0, z: 0 },
  globeRadius: number = 1.0
): { lat: number; lng: number; zoom: number; bearing: number; pitch: number } {
  const dx = cameraPosition.x - cameraTarget.x
  const dy = cameraPosition.y - cameraTarget.y
  const dz = cameraPosition.z - cameraTarget.z

  const distance = Math.sqrt(dx * dx + dy * dy + dz * dz)

  const nx = dx / distance
  const ny = dy / distance
  const nz = dz / distance

  const lat = Math.asin(ny) * (180 / Math.PI)
  const lng = Math.atan2(nz, -nx) * (180 / Math.PI) - 180
  const normalizedLng = lng < -180 ? lng + 360 : lng > 180 ? lng - 360 : lng

  const surfaceDistance = distance - globeRadius
  const maxDist = 1.44
  const minDist = 0.02

  const t = Math.max(0, Math.min(1, (maxDist - surfaceDistance) / (maxDist - minDist)))
  const zoom = 1.5 + t * 16.5

  const bearing = 0
  const pitch = Math.min(60, t * 60)

  return { lat, lng: normalizedLng, zoom, bearing, pitch }
}
