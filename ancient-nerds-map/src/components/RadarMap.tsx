/**
 * RadarMap - Mapbox 2D map showing Lyra radar sites as colored dots.
 * A green scanning bar sweeps left-to-right; dots glow when the bar passes.
 * Hover shows tooltip, click scrolls to the corresponding radar card.
 */

import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MAPBOX } from '../config/mapboxConstants'
import { applyDarkTealTheme, setupDarkFog } from '../utils/mapboxTheme'

interface RadarMapItem {
  id: string
  display_name: string
  enrichment_status: string
  country: string | null
  site_type: string | null
  period_name: string | null
  lat: number | null
  lon: number | null
}

interface RadarMapProps {
  items: RadarMapItem[]
  onSelectItem: (id: string) => void
}

const STATUS_COLORS: Record<string, string> = {
  enriched: '#4ecdc4',
  pending: '#f9a825',
  enriching: '#f9a825',
  promoted: '#66bb6a',
  rejected: '#ef5350',
}

const SWEEP_MS = 8000  // 8 seconds per sweep
const GLOW_MS = 1200   // 1.2 seconds glow duration

function buildGeoJSON(items: RadarMapItem[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: items
      .filter(it => it.lat != null && it.lon != null)
      .map(it => ({
        type: 'Feature' as const,
        geometry: {
          type: 'Point' as const,
          coordinates: [it.lon!, it.lat!],
        },
        properties: {
          id: it.id,
          name: it.display_name,
          status: it.enrichment_status,
          country: it.country || '',
          period: it.period_name || '',
          color: STATUS_COLORS[it.enrichment_status] || '#f9a825',
        },
      })),
  }
}

export default function RadarMap({ items, onSelectItem }: RadarMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const popupRef = useRef<mapboxgl.Popup | null>(null)
  const scanLineRef = useRef<HTMLDivElement>(null)
  const scanAnimRef = useRef<number>(0)
  const glowTimers = useRef<Map<string, number>>(new Map())
  const prevScanXRef = useRef(0)
  const geojsonRef = useRef<GeoJSON.FeatureCollection>(buildGeoJSON(items))

  // Keep geojson ref in sync
  geojsonRef.current = buildGeoJSON(items)

  // Initialize map
  useEffect(() => {
    if (!containerRef.current || !MAPBOX.ACCESS_TOKEN) return

    mapboxgl.accessToken = MAPBOX.ACCESS_TOKEN

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      projection: 'globe',
      zoom: 2,
      center: [20, 30],
      interactive: true,
      attributionControl: true,
      logoPosition: 'bottom-right',
    })

    map.on('load', () => {
      setupDarkFog(map)
      applyDarkTealTheme(map)
      mapRef.current = map

      // Source with promoteId so setFeatureState works with string IDs
      map.addSource('radar-sites', {
        type: 'geojson',
        data: geojsonRef.current,
        promoteId: 'id',
      })

      // Glow layer (underneath dots) — driven by feature state
      map.addLayer({
        id: 'radar-glow',
        type: 'circle',
        source: 'radar-sites',
        paint: {
          'circle-radius': [
            'case',
            ['boolean', ['feature-state', 'glow'], false],
            14, 0,
          ],
          'circle-color': ['get', 'color'],
          'circle-opacity': [
            'case',
            ['boolean', ['feature-state', 'glow'], false],
            0.35, 0,
          ],
          'circle-blur': 1,
        },
      })

      // Main dots layer — slightly enlarges when glowing
      map.addLayer({
        id: 'radar-dots',
        type: 'circle',
        source: 'radar-sites',
        paint: {
          'circle-radius': [
            'case',
            ['boolean', ['feature-state', 'glow'], false],
            7, 5,
          ],
          'circle-color': ['get', 'color'],
          'circle-stroke-width': 1,
          'circle-stroke-color': [
            'case',
            ['boolean', ['feature-state', 'glow'], false],
            'rgba(255,255,255,0.6)',
            'rgba(255,255,255,0.3)',
          ],
          'circle-opacity': 0.85,
        },
      })

      // Hover: show popup
      map.on('mouseenter', 'radar-dots', (e) => {
        map.getCanvas().style.cursor = 'pointer'
        const feature = e.features?.[0]
        if (!feature || feature.geometry.type !== 'Point') return

        const coords = (feature.geometry as GeoJSON.Point).coordinates.slice() as [number, number]
        const props = feature.properties!

        popupRef.current?.remove()
        popupRef.current = new mapboxgl.Popup({
          closeButton: false,
          closeOnClick: false,
          className: 'radar-map-popup',
          offset: 8,
        })
          .setLngLat(coords)
          .setHTML(`
            <strong>${props.name}</strong>
            ${props.country ? `<br>${props.country}` : ''}
            ${props.period ? `<br><span style="opacity:0.7">${props.period}</span>` : ''}
          `)
          .addTo(map)
      })

      map.on('mouseleave', 'radar-dots', () => {
        map.getCanvas().style.cursor = ''
        popupRef.current?.remove()
        popupRef.current = null
      })

      // Click: scroll to card
      map.on('click', 'radar-dots', (e) => {
        const feature = e.features?.[0]
        if (!feature) return
        const id = feature.properties?.id
        if (id) onSelectItem(id)
      })

      // Start scan animation
      startScan()
    })

    map.scrollZoom.enable()
    map.dragPan.enable()
    map.doubleClickZoom.enable()

    const resizeObserver = new ResizeObserver(() => {
      map.resize()
    })
    resizeObserver.observe(containerRef.current)

    function startScan() {
      const scanLine = scanLineRef.current
      const container = containerRef.current
      if (!scanLine || !container) return

      let sweepStart = performance.now()
      prevScanXRef.current = 0

      const tick = (now: number) => {
        if (!mapRef.current) return
        const progress = ((now - sweepStart) % SWEEP_MS) / SWEEP_MS
        const w = container.offsetWidth
        const h = container.offsetHeight
        const scanX = progress * w

        // Position scan line (right edge = bright line at scanX)
        scanLine.style.transform = `translateX(${scanX - 60}px)`

        // Range-based hit detection: check points between prevScanX and scanX
        const prev = prevScanXRef.current

        // Skip detection on wrap-around (scan jumped from right back to left)
        if (scanX >= prev) {
          const features = geojsonRef.current.features
          for (const feat of features) {
            const coords = (feat.geometry as GeoJSON.Point).coordinates as [number, number]
            const pt = mapRef.current.project(coords as mapboxgl.LngLatLike)
            const id = feat.properties!.id as string

            if (pt.x >= prev && pt.x < scanX && pt.y >= 0 && pt.y <= h && !glowTimers.current.has(id)) {
              mapRef.current.setFeatureState(
                { source: 'radar-sites', id },
                { glow: true },
              )
              glowTimers.current.set(id, window.setTimeout(() => {
                if (mapRef.current) {
                  mapRef.current.setFeatureState(
                    { source: 'radar-sites', id },
                    { glow: false },
                  )
                }
                glowTimers.current.delete(id)
              }, GLOW_MS))
            }
          }
        }

        prevScanXRef.current = scanX
        scanAnimRef.current = requestAnimationFrame(tick)
      }

      scanAnimRef.current = requestAnimationFrame(tick)
    }

    return () => {
      cancelAnimationFrame(scanAnimRef.current)
      glowTimers.current.forEach(t => clearTimeout(t))
      glowTimers.current.clear()
      resizeObserver.disconnect()
      popupRef.current?.remove()
      mapRef.current = null
      map.remove()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Update data when items change
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return

    const source = map.getSource('radar-sites') as mapboxgl.GeoJSONSource
    if (source) {
      source.setData(geojsonRef.current)
    }
  }, [items]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="radar-map-container">
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      <div ref={scanLineRef} className="radar-scan-line" />
    </div>
  )
}
