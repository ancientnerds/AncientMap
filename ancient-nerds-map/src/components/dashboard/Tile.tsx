import { Flags } from './Flag'
import { fmtInt } from './format'
import type { CountryCount } from './types'

interface TileProps {
  label: string
  /** The number, already counted by the backend. */
  value: number
  sub: string
  subCls?: string
  /** Flags filling the space beside the number. Omitted, the number is alone. */
  countries?: CountryCount[]
}

/**
 * One labelled number with its sub-line. The number keeps its size; anything
 * beside it gets whatever is left (owner, 2026-09-19).
 */
export function Tile({ label, value, sub, subCls, countries }: TileProps) {
  return (
    <div className="dash-tile">
      <span className="dash-tile-label">{label}</span>
      <div className="dash-tile-main">
        <span className="dash-tile-value">{fmtInt(value)}</span>
        {countries && <Flags rows={countries} />}
      </div>
      <span className={subCls ? `dash-tile-sub ${subCls}` : 'dash-tile-sub'}>{sub}</span>
    </div>
  )
}
