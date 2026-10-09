/**
 * Pure helpers behind the visitor map: an equirectangular projection onto a
 * 1000×500 canvas, GeoJSON rings as SVG path strings, and the per-country
 * dot sizes. No DOM, so vitest covers them.
 */

/** One row of GET /api/stats/map: the sessions of one country over the whole history. */
export type MapPoint = { country: string; sessions: number }

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

/** Dot radius in canvas units, by area against the busiest country: readable
 *  at one session, and the busiest country a dot, not a continent - the map
 *  counts the whole history, so a fixed scale would grow without end. */
export function dotRadius(sessions: number, max: number): number {
  return 4 + 22 * Math.sqrt(sessions / Math.max(max, 1))
}
