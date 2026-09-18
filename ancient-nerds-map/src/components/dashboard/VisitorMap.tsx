import { useMemo, useState } from 'react'

import centroids from '../../data/country_centroids.json'
import land from '../../data/world_land.json'
import { BarList } from './BarList'
import { countryName, fmtHour, fmtInt } from './format'
import { dotRadius, hourWeights, MAP_H, MAP_W, project, ringPath } from './mapMath'
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
 * Where today's visitors are: one dot per country, sized by sessions, for one
 * UTC hour of the day or the whole day. The list beside it is the readable
 * version of the same numbers — dots alone are guesswork on a phone.
 */
export function VisitorMap({ state }: { state: Loaded<MapData> }) {
  const landPath = useMemo(() => LAND_RINGS.map(ringPath).join(' '), [])
  // The whole day is the honest default: opening on the current UTC hour
  // showed two dots next to a caption that said "last 24 hours".
  const [hour, setHour] = useState<number | null>(null)
  const weights = hourWeights(state.data?.points ?? [], hour)
  const ranked = Object.entries(weights).sort((a, b) => b[1] - a[1])
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
              <circle key={code} className="dash-map-dot" cx={cx} cy={cy} r={dotRadius(sessions)}>
                <title>{`${countryName(code)}: ${fmtInt(sessions)} sessions`}</title>
              </circle>
            )
          })}
        </svg>
        <div className="dash-map-controls">
          <input
            type="range"
            min={0}
            max={23}
            value={hour ?? 0}
            disabled={hour === null}
            aria-label="Hour of the day (UTC)"
            onChange={e => setHour(Number(e.target.value))}
          />
          <span className="dash-map-hour">{hour === null ? 'Whole day' : `${fmtHour(hour)} UTC`}</span>
          <button
            type="button"
            className="dash-toggle"
            aria-pressed={hour === null}
            onClick={() => setHour(hour === null ? new Date().getUTCHours() : null)}
          >
            All hours
          </button>
        </div>
      </div>
      <Status state={state} />
      {state.data && (
        <>
          <p className="dash-note">
            {fmtInt(total)} sessions in {fmtInt(ranked.length)} countries,{' '}
            {hour === null ? 'last 24 hours' : `at ${fmtHour(hour)} UTC`}
            {unmapped.length > 0 && ` · no dot for: ${unmapped.map(([code]) => countryName(code)).join(', ')}`}
          </p>
          <BarList
            items={ranked.slice(0, LIST_ROWS).map(([code, sessions]) => ({ key: code, label: countryName(code), value: sessions }))}
            empty="No sessions in this hour."
          />
        </>
      )}
    </Panel>
  )
}
