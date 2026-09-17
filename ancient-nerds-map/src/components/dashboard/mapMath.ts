/**
 * Pure helpers behind the visitor map: an equirectangular projection onto a
 * 1000×500 canvas, GeoJSON rings as SVG path strings, and the per-country
 * session weights for one hour of the day. No DOM, so vitest covers them.
 */

/** One row of GET /api/stats/map: sessions per country, city and UTC hour. */
export type MapPoint = { country: string; city: string | null; hour: number; sessions: number }

/** A Natural Earth land feature: rings of [lon, lat] pairs. */
export const MAP_W = 1000
export const MAP_H = 500

/** lon/lat → canvas x/y (integers: the SVG path stays small). */
export function project([lon, lat]: [number, number]): [number, number] {
  return [Math.round(((lon + 180) / 360) * MAP_W), Math.round(((90 - lat) / 180) * MAP_H)]
}

/** One ring as `M…L…Z`; GeoJSON repeats the first point at the end, `Z` already closes. */
export function ringPath(ring: number[][]): string {
  const [first] = ring
  const last = ring[ring.length - 1]
  const open = last[0] === first[0] && last[1] === first[1] ? ring.slice(0, -1) : ring
  return (
    open
      .map(([lon, lat], i) => {
        const [x, y] = project([lon, lat])
        return `${i === 0 ? 'M' : 'L'}${x} ${y}`
      })
      .join('') + 'Z'
  )
}

/** Sessions per country for one UTC hour, or for the whole day when `hour` is null. */
export function hourWeights(points: MapPoint[], hour: number | null): Record<string, number> {
  const out: Record<string, number> = {}
  for (const p of points) {
    if (hour !== null && p.hour !== hour) continue
    out[p.country] = (out[p.country] ?? 0) + p.sessions
  }
  return out
}

/** Dot radius in canvas units: readable at one session, not a blob at a hundred. */
export function dotRadius(sessions: number): number {
  return 4 + 3 * Math.sqrt(sessions)
}
