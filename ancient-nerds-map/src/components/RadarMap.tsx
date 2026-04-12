/**
 * RadarMap - Mapbox 2D map showing Lyra radar sites as colored dots.
 * A scan line sweeps around the globe (longitude-based); dots glow when hit.
 * Dots are colored by period (age) matching the main globe's color scheme.
 * Hover calls onHoverItem, click calls onPinItem (parent renders the card).
 */

import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MAPBOX } from '../config/mapboxConstants'
import { applyDarkTealTheme, setupDarkFog } from '../utils/mapboxTheme'

interface RadarMapItem {
  id: string
  display_name: string
  enrichment_status: string
  enrichment_score: number
  country: string | null
  site_type: string | null
  period_name: string | null
  lat: number | null
  lon: number | null
}

interface RadarMapProps {
  items: RadarMapItem[]
  onHoverItem?: (id: string | null) => void
  onPinItem?: (id: string | null) => void
  children?: ReactNode
}

const SWEEP_MS = 12000 // 12 seconds per full rotation
const GLOW_MS = 1200

/** Power curve so 75% = yellow, 85% = yellow-green, 95%+ = green — matches LyraRadarPage scoreColor */
function scoreToColor(pct: number): string {
  const hue = Math.round(Math.pow(pct / 100, 2.5) * 120)
  return `hsl(${hue}, 72%, 55%)`
}

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
          score: it.enrichment_score,
          color: scoreToColor(it.enrichment_score),
        },
      })),
  }
}

/** Convert longitude (-180..180) to 0..360 for wrap-safe comparisons */
function lonToDeg(lon: number): number {
  return lon < 0 ? lon + 360 : lon
}

export default function RadarMap({ items, onHoverItem, onPinItem, children }: RadarMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const scanAnimRef = useRef<number>(0)
  const glowTimers = useRef<Map<string, number>>(new Map())
  const prevScanDegRef = useRef(0)
  const geojsonRef = useRef<GeoJSON.FeatureCollection>(buildGeoJSON(items))
  const onHoverItemRef = useRef(onHoverItem)
  const onPinItemRef = useRef(onPinItem)
  onHoverItemRef.current = onHoverItem
  onPinItemRef.current = onPinItem

  geojsonRef.current = buildGeoJSON(items)

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

      // ── Radar sites ──
      map.addSource('radar-sites', {
        type: 'geojson',
        data: geojsonRef.current,
        promoteId: 'id',
      })

      map.addLayer({
        id: 'radar-glow',
        type: 'circle',
        source: 'radar-sites',
        paint: {
          'circle-radius': ['case', ['boolean', ['feature-state', 'glow'], false], 14, 0],
          'circle-color': ['get', 'color'],
          'circle-opacity': ['case', ['boolean', ['feature-state', 'glow'], false], 0.35, 0],
          'circle-blur': 1,
        },
      })

      map.addLayer({
        id: 'radar-dots',
        type: 'circle',
        source: 'radar-sites',
        paint: {
          'circle-radius': ['case', ['boolean', ['feature-state', 'glow'], false], 7, 5],
          'circle-color': ['get', 'color'],
          'circle-opacity': 0.85,
        },
      })

      // ── Scan ring (two opposite meridians = full great circle) ──
      const emptyRing: GeoJSON.Feature = {
        type: 'Feature',
        geometry: {
          type: 'MultiLineString',
          coordinates: [[[0, -85], [0, 85]], [[180, -85], [180, 85]]],
        },
        properties: {},
      }

      map.addSource('scan-line', { type: 'geojson', data: emptyRing })

      // Ring glow (wide + blurry)
      map.addLayer({
        id: 'scan-line-glow',
        type: 'line',
        source: 'scan-line',
        paint: { 'line-color': 'rgba(78, 205, 196, 0.25)', 'line-width': 6, 'line-blur': 4 },
      }, 'radar-glow')

      // Ring bright (thin + sharp)
      map.addLayer({
        id: 'scan-line-bright',
        type: 'line',
        source: 'scan-line',
        paint: { 'line-color': 'rgba(78, 205, 196, 0.7)', 'line-width': 1.5 },
      }, 'radar-glow')

      // ── Interaction ──
      map.on('mouseenter', 'radar-dots', (e) => {
        map.getCanvas().style.cursor = 'pointer'
        const id = e.features?.[0]?.properties?.id
        if (id) onHoverItemRef.current?.(id)
      })

      map.on('mouseleave', 'radar-dots', () => {
        map.getCanvas().style.cursor = ''
        onHoverItemRef.current?.(null)
      })

      map.on('click', (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ['radar-dots'] })
        if (features.length > 0) {
          const id = features[0].properties?.id
          if (id) onPinItemRef.current?.(id)
        } else {
          onPinItemRef.current?.(null)
        }
      })

      startScan()
    })

    map.scrollZoom.enable()
    map.dragPan.enable()
    map.doubleClickZoom.enable()

    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(containerRef.current)

    function startScan() {
      let sweepStart = performance.now()
      prevScanDegRef.current = 0

      const tick = (now: number) => {
        if (!mapRef.current) return
        const m = mapRef.current
        const progress = ((now - sweepStart) % SWEEP_MS) / SWEEP_MS

        // 0-360 degree space → -180..180 longitude
        const scanDeg = progress * 360
        const scanLon = scanDeg <= 180 ? scanDeg : scanDeg - 360
        const oppLon = scanLon > 0 ? scanLon - 180 : scanLon + 180

        // Update scan ring (two opposite meridians)
        const lineSrc = m.getSource('scan-line') as mapboxgl.GeoJSONSource
        if (lineSrc) {
          lineSrc.setData({
            type: 'Feature',
            geometry: {
              type: 'MultiLineString',
              coordinates: [
                [[scanLon, -85], [scanLon, 85]],
                [[oppLon, -85], [oppLon, 85]],
              ],
            },
            properties: {},
          })
        }

        // Hit detection — check both the primary and opposite meridian
        const prevDeg = prevScanDegRef.current
        const oppScanDeg = (scanDeg + 180) % 360
        const oppPrevDeg = (prevDeg + 180) % 360

        for (const feat of geojsonRef.current.features) {
          const lon = (feat.geometry as GeoJSON.Point).coordinates[0]
          const siteDeg = lonToDeg(lon)
          const id = feat.properties!.id as string

          // Primary line
          let hit = scanDeg >= prevDeg
            ? siteDeg >= prevDeg && siteDeg < scanDeg
            : siteDeg >= prevDeg || siteDeg < scanDeg

          // Opposite line
          if (!hit) {
            hit = oppScanDeg >= oppPrevDeg
              ? siteDeg >= oppPrevDeg && siteDeg < oppScanDeg
              : siteDeg >= oppPrevDeg || siteDeg < oppScanDeg
          }

          if (hit && !glowTimers.current.has(id)) {
            m.setFeatureState({ source: 'radar-sites', id }, { glow: true })
            glowTimers.current.set(id, window.setTimeout(() => {
              if (mapRef.current) {
                mapRef.current.setFeatureState({ source: 'radar-sites', id }, { glow: false })
              }
              glowTimers.current.delete(id)
            }, GLOW_MS))
          }
        }

        prevScanDegRef.current = scanDeg
        scanAnimRef.current = requestAnimationFrame(tick)
      }

      scanAnimRef.current = requestAnimationFrame(tick)
    }

    return () => {
      cancelAnimationFrame(scanAnimRef.current)
      glowTimers.current.forEach(t => clearTimeout(t))
      glowTimers.current.clear()
      resizeObserver.disconnect()
      mapRef.current = null
      map.remove()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const source = map.getSource('radar-sites') as mapboxgl.GeoJSONSource
    if (source) source.setData(geojsonRef.current)
  }, [items]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="radar-map-container">
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      {children}
    </div>
  )
}
