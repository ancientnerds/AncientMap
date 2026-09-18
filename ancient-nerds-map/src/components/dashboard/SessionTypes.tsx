import { BarList } from './BarList'
import { fmtInt, fmtShare } from './format'
import { Panel, Status } from './Panel'
import type { Overview, SessionKind } from './types'
import type { Loaded } from './useStats'

/** Display order and labels of pipeline/stats_analysis.py Session.kind. */
const KINDS: Array<[SessionKind, string]> = [
  ['explorer', 'Explorers — globe, sites opened'],
  ['reader', 'Readers — stories, journals'],
  ['researcher', 'Researchers — papers, Lyra'],
  ['searcher', 'Searchers — searched, opened nothing'],
  ['other', 'Other'],
]

/** What the confirmed-human sessions did, as shares of the window. */
export function SessionTypes({ state }: { state: Loaded<Overview> }) {
  const o = state.data
  return (
    <Panel question="What do visitors do?">
      <Status state={state} />
      {o && (
        <>
          <BarList
            items={KINDS.map(([kind, label]) => {
              const n = o.types[kind] ?? 0
              return { key: kind, label, value: n, hint: fmtShare(n, o.sessions.human) }
            })}
            empty="No sessions in this window."
          />
          <p className="dash-note">
            Confirmed human: {fmtInt(o.sessions.human)} of {fmtInt(o.sessions.all)} sessions — an interaction or a
            second page. The rest may be a bot, or a person who bounced.
          </p>
        </>
      )}
    </Panel>
  )
}
