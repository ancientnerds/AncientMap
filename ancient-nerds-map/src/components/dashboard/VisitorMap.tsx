import { useMemo } from 'react'

import centroids from '../../data/country_centroids.json'
import land from '../../data/world_land.json'
import { BarList } from './BarList'
import { countryName, fmtInt } from './format'
import { dotRadius, MAP_H, MAP_W, project, ringPath } from './mapMath'
import { Panel, Status } from './Panel'
import type { MapData } from './types'
import type { Loaded } from './useStats'

const LIST_ROWS = 8

/** ISO-2 → [lon, lat] (scripts/build_country_centroids.py). */
const CENTROIDS: Record<string, number[]> = centroids

/** Natural Earth 110m outer rings, simplified to one decimal
 *  (scripts/build_country_centroids.py). Bundled, not fetched: *.geojson is
 *  LFS-tracked in this repo and the dashboard needs no round trip for it. */
const LAND_RINGS: number[][][] = land

/**
 * Where the visitors are: one dot per country, sized by its sessions over the
 * whole history, and the ranked list beside it - dots alone are guesswork on
 * a phone (owner, 2026-10-10: always every visitor, no hour slider).
 */
export function VisitorMap({ state }: { state: Loaded<MapData> }) {
  const landPath = useMemo(() => LAND_RINGS.map(ringPath).join(' '), [])
  const ranked = (state.data?.points ?? []).map(p => [p.country, p.sessions] as const).sort((a, b) => b[1] - a[1])
  const max = ranked.length ? ranked[0][1] : 0
  const total = ranked.reduce((sum, [, n]) => sum + n, 0)
  const unmapped = ranked.filter(([code]) => !CENTROIDS[code])

  return (
    <Panel question="Where are the visitors?" wide>
      <div className="dash-map">
        <svg viewBox={`0 0 ${MAP_W} ${MAP_H}`} role="img" aria-label="World map of visitor sessions per country">
          <path className="dash-map-land" d={landPath} />
          {ranked.map(([code, sessions]) => {
            const centre = CENTROIDS[code]
            if (!centre) return null
            const [cx, cy] = project([centre[0], centre[1]])
            return (
              <circle key={code} className="dash-map-dot" cx={cx} cy={cy} r={dotRadius(sessions, max)}>
                <title>{`${countryName(code)}: ${fmtInt(sessions)} sessions`}</title>
              </circle>
            )
          })}
        </svg>
      </div>
      <Status state={state} />
      {state.data && (
        <>
          <p className="dash-note">
            {fmtInt(total)} sessions from {fmtInt(ranked.length)} countries since tracking began
            {unmapped.length > 0 && ` · no dot for: ${unmapped.map(([code]) => countryName(code)).join(', ')}`}
          </p>
          <BarList
            items={ranked.slice(0, LIST_ROWS).map(([code, sessions]) => ({ key: code, label: countryName(code), value: sessions }))}
            empty="No sessions yet."
          />
        </>
      )}
    </Panel>
  )
}
