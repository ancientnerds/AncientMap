/**
 * Coordinate parsing and formatting utilities
 * Supports multiple coordinate formats: DMS, DDM, decimal, Google Maps URLs
 */

/**
 * Convert DMS (degrees, minutes, seconds) to decimal degrees
 */
export function dmsToDecimal(degrees: number, minutes: number, seconds: number): number {
  return degrees + minutes / 60 + seconds / 3600
}

/**
 * Format coordinates for display: "45.1234° N, 12.5678° E"
 * @param lng Longitude
 * @param lat Latitude
 */
export function formatCoordinate(lng: number, lat: number): string {
  const latAbs = Math.abs(lat).toFixed(4)
  const latDir = lat >= 0 ? 'N' : 'S'
  const lngAbs = Math.abs(lng).toFixed(4)
  const lngDir = lng >= 0 ? 'E' : 'W'
  return `${latAbs}° ${latDir}, ${lngAbs}° ${lngDir}`
}

/**
 * Universal coordinate parser - supports many formats
 * Returns [lng, lat] or null if invalid
 *
 * Supported formats:
 * - Google Maps URLs (@lat,lng / ?q=lat,lng / place/lat,lng / search/lat,lng)
 * - DMS: 45° 7' 24.24" N, 12° 34' 4.8" E
 * - DDM: 45° 7.404' N, 12° 34.08' E
 * - Decimal with directions: 45.1234° N, 12.5678° E or N 45.1234, E 12.5678
 * - Simple signed decimal: 45.1234, 12.5678
 */
export function parseAnyCoordinate(input: string): [number, number] | null {
  if (!input || !input.trim()) return null
  const str = input.trim()

  // Helper to validate and return coordinates
  const validate = (lat: number, lng: number): [number, number] | null => {
    if (isNaN(lat) || isNaN(lng)) return null
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null
    return [lng, lat]
  }

  // 1. Google Maps URL patterns
  // https://maps.google.com/?q=45.1234,12.5678
  // https://www.google.com/maps/place/45.1234,12.5678
  // https://www.google.com/maps/@45.1234,12.5678,15z
  if (str.includes('google.com/maps') || str.includes('maps.google')) {
    // Try @lat,lng,zoom format
    const atMatch = str.match(/@(-?\d+\.?\d*),(-?\d+\.?\d*)/)
    if (atMatch) {
      return validate(parseFloat(atMatch[1]), parseFloat(atMatch[2]))
    }
    // Try ?q=lat,lng or place/lat,lng format
    const qMatch = str.match(/[?&]q=(-?\d+\.?\d*),(-?\d+\.?\d*)/)
    if (qMatch) {
      return validate(parseFloat(qMatch[1]), parseFloat(qMatch[2]))
    }
    const placeMatch = str.match(/place\/(-?\d+\.?\d*),(-?\d+\.?\d*)/)
    if (placeMatch) {
      return validate(parseFloat(placeMatch[1]), parseFloat(placeMatch[2]))
    }
    // Try /search/lat,lng format
    const searchMatch = str.match(/\/search\/(-?\d+\.?\d*),(-?\d+\.?\d*)/)
    if (searchMatch) {
      return validate(parseFloat(searchMatch[1]), parseFloat(searchMatch[2]))
    }
  }

  // 2. Full DMS format: 45° 7' 24.24" N, 12° 34' 4.8" E (or compact without spaces)
  // Also handles: 45°7'24"N 12°34'5"E or 45 7 24 N, 12 34 5 E
  const dmsPattern = /(-?\d+)\s*°?\s*(\d+)\s*['′]?\s*(\d+\.?\d*)\s*["″]?\s*([NSns])\s*[,\s]\s*(-?\d+)\s*°?\s*(\d+)\s*['′]?\s*(\d+\.?\d*)\s*["″]?\s*([EWew])/
  const dmsMatch = str.match(dmsPattern)
  if (dmsMatch) {
    let lat = dmsToDecimal(parseFloat(dmsMatch[1]), parseFloat(dmsMatch[2]), parseFloat(dmsMatch[3]))
    let lng = dmsToDecimal(parseFloat(dmsMatch[5]), parseFloat(dmsMatch[6]), parseFloat(dmsMatch[7]))
    if (dmsMatch[4].toUpperCase() === 'S') lat = -lat
    if (dmsMatch[8].toUpperCase() === 'W') lng = -lng
    return validate(lat, lng)
  }

  // 3. DDM format: 45° 7.404' N, 12° 34.08' E (degrees + decimal minutes)
  const ddmPattern = /(-?\d+)\s*°?\s*(\d+\.?\d*)\s*['′]?\s*([NSns])\s*[,\s]\s*(-?\d+)\s*°?\s*(\d+\.?\d*)\s*['′]?\s*([EWew])/
  const ddmMatch = str.match(ddmPattern)
  if (ddmMatch) {
    let lat = parseFloat(ddmMatch[1]) + parseFloat(ddmMatch[2]) / 60
    let lng = parseFloat(ddmMatch[4]) + parseFloat(ddmMatch[5]) / 60
    if (ddmMatch[3].toUpperCase() === 'S') lat = -lat
    if (ddmMatch[6].toUpperCase() === 'W') lng = -lng
    return validate(lat, lng)
  }

  // 4. Decimal with directions: 45.1234° N, 12.5678° E or 45.1234 N 12.5678 E
  // Also: N 45.1234, E 12.5678 (direction first)
  const decDirPattern1 = /(-?\d+\.?\d*)\s*°?\s*([NSns])\s*[,\s]\s*(-?\d+\.?\d*)\s*°?\s*([EWew])/
  const decDirMatch1 = str.match(decDirPattern1)
  if (decDirMatch1) {
    let lat = parseFloat(decDirMatch1[1])
    let lng = parseFloat(decDirMatch1[3])
    if (decDirMatch1[2].toUpperCase() === 'S') lat = -lat
    if (decDirMatch1[4].toUpperCase() === 'W') lng = -lng
    return validate(lat, lng)
  }

  // Direction first: N 45.1234, E 12.5678
  const decDirPattern2 = /([NSns])\s*(-?\d+\.?\d*)\s*°?\s*[,\s]\s*([EWew])\s*(-?\d+\.?\d*)/
  const decDirMatch2 = str.match(decDirPattern2)
  if (decDirMatch2) {
    let lat = parseFloat(decDirMatch2[2])
    let lng = parseFloat(decDirMatch2[4])
    if (decDirMatch2[1].toUpperCase() === 'S') lat = -lat
    if (decDirMatch2[3].toUpperCase() === 'W') lng = -lng
    return validate(lat, lng)
  }

  // 5. Simple signed decimal: 45.1234, 12.5678 or 45.1234 12.5678 (lat, lng order)
  const simplePattern = /^(-?\d+\.?\d*)\s*[,\s]\s*(-?\d+\.?\d*)$/
  const simpleMatch = str.match(simplePattern)
  if (simpleMatch) {
    const lat = parseFloat(simpleMatch[1])
    const lng = parseFloat(simpleMatch[2])
    return validate(lat, lng)
  }

  return null
}

/**
 * Apply mask to coordinate input - auto-insert formatting characters
 * Format: XX.XXXX° N, XXX.XXXX° E
 * @returns Object with formatted string and detected directions
 */
export function applyCoordMask(input: string): { formatted: string; latDir: 'N' | 'S'; lngDir: 'E' | 'W' } {
  const chars = input.toUpperCase().split('')
  let digits = ''
  let latDir: 'N' | 'S' = 'N'
  let lngDir: 'E' | 'W' = 'E'

  // Extract digits and direction toggles
  for (const char of chars) {
    if (/\d/.test(char)) {
      digits += char
    } else if (char === 'S') {
      latDir = 'S'
    } else if (char === 'W') {
      lngDir = 'W'
    } else if (char === 'N') {
      latDir = 'N'
    } else if (char === 'E') {
      lngDir = 'E'
    }
  }

  // Limit to 13 digits (2+4 lat, 3+4 lng)
  digits = digits.slice(0, 13)

  if (digits.length === 0) return { formatted: '', latDir, lngDir }

  let result = ''

  // Build result progressively
  if (digits.length <= 2) {
    result = digits
  } else if (digits.length <= 6) {
    result = `${digits.slice(0, 2)}.${digits.slice(2)}`
  } else if (digits.length <= 9) {
    result = `${digits.slice(0, 2)}.${digits.slice(2, 6)}° ${latDir}, ${digits.slice(6)}`
  } else if (digits.length < 13) {
    result = `${digits.slice(0, 2)}.${digits.slice(2, 6)}° ${latDir}, ${digits.slice(6, 9)}.${digits.slice(9)}`
  } else {
    result = `${digits.slice(0, 2)}.${digits.slice(2, 6)}° ${latDir}, ${digits.slice(6, 9)}.${digits.slice(9)}° ${lngDir}`
  }

  return { formatted: result, latDir, lngDir }
}
