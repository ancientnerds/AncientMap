/**
 * RadarMap - Mapbox 2D map showing Lyra radar sites as colored dots.
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

export default function RadarMap({ items, onSelectItem }: RadarMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const popupRef = useRef<mapboxgl.Popup | null>(null)

  // Build GeoJSON from items
  const geojson: GeoJSON.FeatureCollection = {
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

  // Initialize map once
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

      // Add source + layer
      map.addSource('radar-sites', {
        type: 'geojson',
        data: geojson,
      })

      map.addLayer({
        id: 'radar-dots',
        type: 'circle',
        source: 'radar-sites',
        paint: {
          'circle-radius': 5,
          'circle-color': ['get', 'color'],
          'circle-stroke-width': 1,
          'circle-stroke-color': 'rgba(255,255,255,0.3)',
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
    })

    map.scrollZoom.enable()
    map.dragPan.enable()
    map.doubleClickZoom.enable()

    const resizeObserver = new ResizeObserver(() => {
      map.resize()
    })
    resizeObserver.observe(containerRef.current)

    return () => {
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
      source.setData(geojson)
    }
  }, [items]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="radar-map-container">
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
