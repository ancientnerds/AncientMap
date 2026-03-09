import { useState, useEffect } from 'react'
import type { UnifiedGalleryItem } from '../types'
import { fetchWebcams, filterByProximity, getThumbnailUrl, getPageUrl } from '../../../data/webcams'

const PROXIMITY_RADIUS_KM = 50

interface UseWebcamDataOptions {
  lat: number
  lng: number
  isOffline: boolean
}

export function useWebcamData({ lat, lng, isOffline }: UseWebcamDataOptions) {
  const [webcamItems, setWebcamItems] = useState<UnifiedGalleryItem[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (isOffline || !lat || !lng) {
      setWebcamItems([])
      return
    }

    setIsLoading(true)
    fetchWebcams()
      .then(all => {
        const nearby = filterByProximity(all, lat, lng, PROXIMITY_RADIUS_KM)
        const items: UnifiedGalleryItem[] = nearby.map(w => ({
          id: `webcam-${w.id}`,
          thumb: getThumbnailUrl(w.skylineId),
          full: getThumbnailUrl(w.skylineId),
          title: w.name,
          source: 'skyline_webcam' as const,
          original: {
            webcamId: w.id,
            skylineId: w.skylineId,
            slug: w.slug,
            pageUrl: getPageUrl(w.slug),
            lat: w.lat,
            lon: w.lon,
            region: w.region,
            flag: w.flag,
            timezone: w.timezone,
            distanceKm: w.distanceKm,
          },
        }))
        setWebcamItems(items)
      })
      .catch(() => setWebcamItems([]))
      .finally(() => setIsLoading(false))
  }, [lat, lng, isOffline])

  return { webcamItems, isLoadingWebcams: isLoading }
}
