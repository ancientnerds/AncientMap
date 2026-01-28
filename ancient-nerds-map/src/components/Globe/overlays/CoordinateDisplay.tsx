/**
 * CoordinateDisplay - Shows cursor coordinates on the globe
 * Pure presentational component for displaying lat/lon coordinates
 */

interface CoordinateDisplayProps {
  coords: { lat: number; lon: number } | null
  visible: boolean
}

export function CoordinateDisplay({ coords, visible }: CoordinateDisplayProps) {
  if (!visible || !coords) return null

  return (
    <div className="cursor-coords">
      {Math.abs(coords.lat).toFixed(4)}°{coords.lat >= 0 ? 'N' : 'S'}, {Math.abs(coords.lon).toFixed(4)}°{coords.lon >= 0 ? 'E' : 'W'}
    </div>
  )
}
