export interface WebcamEntry {
  id: string
  skylineId: string
  name: string
  slug: string
  lat: number
  lon: number
  region: string
  flag: string
  timezone: string
}

let _cache: WebcamEntry[] | null = null

export async function fetchWebcams(): Promise<WebcamEntry[]> {
  if (_cache) return _cache
  const resp = await fetch('/data/webcams.json')
  if (!resp.ok) return []
  _cache = await resp.json()
  return _cache!
}

/** Haversine distance in km */
export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

/** Get webcams near a coordinate, sorted by distance */
export function filterByProximity(
  webcams: WebcamEntry[],
  lat: number,
  lon: number,
  radiusKm: number = 50
): (WebcamEntry & { distanceKm: number })[] {
  return webcams
    .map(w => ({ ...w, distanceKm: haversineKm(lat, lon, w.lat, w.lon) }))
    .filter(w => w.distanceKm <= radiusKm)
    .sort((a, b) => a.distanceKm - b.distanceKm)
}

export function getThumbnailUrl(skylineId: string): string {
  return `https://cdn.skylinewebcams.com/live${skylineId}.jpg`
}

export function getPageUrl(slug: string): string {
  return `https://www.skylinewebcams.com/en/webcam/${slug}.html`
}
