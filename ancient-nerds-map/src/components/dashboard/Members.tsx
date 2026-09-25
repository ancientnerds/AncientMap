import { BarList, type BarItem } from './BarList'
import { fmtInt, fmtStamp } from './format'
import { HowCounted, Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { MemberAct, MembersData } from './types'
import type { Loaded } from './useStats'

/**
 * One act as a bar row. The hint carries the denominator and the date,
 * because at this size the total alone is a lie: 126 Lyra answers come from
 * two accounts, 125 of them from one (measured 2026-09-19). "126" under a
 * panel headed "Who signed up, and did they come back?" reads as member
 * activity and is one person's week.
 */
export function actItem(a: MemberAct): BarItem {
  const by = `by ${fmtInt(a.by)} ${a.by === 1 ? 'account' : 'accounts'}`
  return {
    key: a.act,
    label: a.act,
    value: a.n,
    hint: a.at ? `${by}, last ${fmtStamp(a.at)}` : 'never',
  }
}

/**
 * The end of the funnel. All-time counts, never a window: at five members a
 * seven-day window reads zero everywhere and says nothing. Aggregates only —
 * the backend never sends a name, an id or a credit balance.
 */
export function Members({ state }: { state: Loaded<MembersData> }) {
  const m = state.data
  return (
    <Panel question="Who signed up, and did they come back?">
      <Status state={state} />
      {m && (
        <>
          <div className="dash-tiles">
            <Tile
              label="Members"
              value={m.members}
              sub={m.newest_signup ? `newest ${fmtStamp(m.newest_signup)}` : 'none yet'}
            />
            <Tile
              label="Founders"
              value={m.founders}
              sub={m.last_login ? `last login ${fmtStamp(m.last_login)}` : 'never'}
            />
          </div>
          <BarList items={m.acts.map(actItem)} empty="Nobody has done anything yet." />
          <HowCounted>
            Everything since the first signup, not the window above — {fmtInt(m.members)} members cannot
            fill a seven-day bucket. The login date is a founder's own; member recency is the date on each
            act row. The account counts are per table and do not add up across rows: three of the four
            key on a member id, research requests on a Discord id. The card game is not counted here: its
            table lives on the API side, which this query may not reach.
          </HowCounted>
        </>
      )}
    </Panel>
  )
}
