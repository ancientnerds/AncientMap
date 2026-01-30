/**
 * EmpireMinimap - Interactive Mapbox map showing empire boundaries
 * Uses outdoors style with dark teal theme to match the main globe
 * Empire boundaries match the same color/style as the 3D globe
 */

import { useEffect, useRef, useCallback } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { MAPBOX } from '../config/mapboxConstants'
import { getEmpireById } from '../config/empireData'
import { applyDarkTealTheme, setupDarkFog, hexToRgba } from '../utils/mapboxTheme'

interface EmpireMinimapProps {
  empireId: string
  year: number
  empireColor: number // hex color as number (e.g., 0xFF7777) - same as globe
}

export default function EmpireMinimap({ empireId, year, empireColor }: EmpireMinimapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const loadingRef = useRef(false)
  const currentYearRef = useRef<number | null>(null)

  // Get empire file path from config (same source as globe)
  const empire = getEmpireById(empireId)
  const empireFile = empire?.file

  /**
   * Load empire GeoJSON boundaries and display on map
   * Uses same data source as the 3D globe: /data/historical/{empire}/{year}.geojson
   */
  const loadBoundaries = useCallback(async (map: mapboxgl.Map, file: string, yearToLoad: number) => {
    // Prevent concurrent loads
    if (loadingRef.current) return
    if (currentYearRef.current === yearToLoad) return

    loadingRef.current = true
    currentYearRef.current = yearToLoad

    try {
      // Same GeoJSON path as empireRenderer.ts
      const response = await fetch(`/data/historical/${file}/${yearToLoad}.geojson`)
      if (!response.ok) {
        console.warn(`[EmpireMinimap] Failed to load ${file}/${yearToLoad}.geojson`)
        return
      }
      const geojson = await response.json()

      // Update or create source
      const source = map.getSource('empire-boundaries') as mapboxgl.GeoJSONSource
      if (source) {
        source.setData(geojson)
      } else {
        // First load - create source and layers
        map.addSource('empire-boundaries', {
          type: 'geojson',
          data: geojson
        })

        // Fill layer - semi-transparent (same 15% opacity as globe fill)
        map.addLayer({
          id: 'empire-fill',
          type: 'fill',
          source: 'empire-boundaries',
          paint: {
            'fill-color': hexToRgba(empireColor, 0.15),
            'fill-opacity': 1
          }
        })

        // Border layer - solid color (same 90% opacity as globe border)
        map.addLayer({
          id: 'empire-border',
          type: 'line',
          source: 'empire-boundaries',
          paint: {
            'line-color': hexToRgba(empireColor, 0.9),
            'line-width': 2
          }
        })
      }

      // Fit map to empire bounds
      fitMapToBounds(map, geojson)

    } catch (error) {
      console.warn('[EmpireMinimap] Error loading boundaries:', error)
    } finally {
      loadingRef.current = false
    }
  }, [empireColor])

  /**
   * Calculate bounding box from GeoJSON and fit map to it
   */
  const fitMapToBounds = (map: mapboxgl.Map, geojson: any) => {
    if (!geojson.features || geojson.features.length === 0) return

    let minLng = Infinity, minLat = Infinity
    let maxLng = -Infinity, maxLat = -Infinity

    const processCoords = (coords: any): void => {
      if (typeof coords[0] === 'number') {
        // Single coordinate [lng, lat]
        const [lng, lat] = coords as [number, number]
        minLng = Math.min(minLng, lng)
        minLat = Math.min(minLat, lat)
        maxLng = Math.max(maxLng, lng)
        maxLat = Math.max(maxLat, lat)
      } else {
        // Nested array
        for (const c of coords) {
          processCoords(c)
        }
      }
    }

    for (const feature of geojson.features) {
      if (feature.geometry?.coordinates) {
        processCoords(feature.geometry.coordinates)
      }
    }

    if (minLng !== Infinity) {
      map.fitBounds(
        [[minLng, minLat], [maxLng, maxLat]],
        { padding: 20, duration: 300, maxZoom: 6 }
      )
    }
  }

  // Initialize Mapbox map
  useEffect(() => {
    if (!containerRef.current || !MAPBOX.ACCESS_TOKEN) return

    mapboxgl.accessToken = MAPBOX.ACCESS_TOKEN

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/outdoors-v12',
      projection: 'globe',
      zoom: 2,
      center: [20, 35], // Default to Mediterranean area
      interactive: true,
      attributionControl: false,
      logoPosition: 'bottom-right'
    })

    map.on('load', () => {
      // Apply same theme as main globe
      setupDarkFog(map)
      applyDarkTealTheme(map)

      mapRef.current = map

      // Load initial boundaries
      if (empireFile) {
        loadBoundaries(map, empireFile, year)
      }
    })

    // Disable scroll zoom (let parent scroll the popup)
    map.scrollZoom.disable()
    // Enable drag to pan
    map.dragPan.enable()

    return () => {
      mapRef.current = null
      map.remove()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Update boundaries when year changes (slider interaction)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !empireFile) return
    if (!map.isStyleLoaded()) return

    loadBoundaries(map, empireFile, year)
  }, [year, empireFile, loadBoundaries])

  // Update colors if empire color changes
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return

    if (map.getLayer('empire-fill')) {
      map.setPaintProperty('empire-fill', 'fill-color', hexToRgba(empireColor, 0.15))
    }
    if (map.getLayer('empire-border')) {
      map.setPaintProperty('empire-border', 'line-color', hexToRgba(empireColor, 0.9))
    }
  }, [empireColor])

  return (
    <div className="empire-minimap-container">
      <div ref={containerRef} className="empire-minimap" />
    </div>
  )
}
