import { BarList } from './BarList'
import { fmtInt, fmtShare } from './format'
import { Panel, Status } from './Panel'
import type { Overview, SessionKind } from './types'
import type { Loaded } from './useStats'

/** Display order and labels of api/services/founders_stats.py Session.kind. */
const KINDS: Array<[SessionKind, string]> = [
  ['entdecker', 'Entdecker — Globus, Sites geöffnet'],
  ['leser', 'Leser — Stories, Journals'],
  ['forscher', 'Forscher — Papers, Lyra'],
  ['sucher', 'Sucher — gesucht, nichts geöffnet'],
  ['sonstige', 'Sonstige'],
]

/** What the confirmed-human sessions did, as shares of the window. */
export function SessionTypes({ state }: { state: Loaded<Overview> }) {
  const o = state.data
  return (
    <Panel question="Was tun die Besucher?">
      <Status state={state} />
      {o && (
        <>
          <BarList
            items={KINDS.map(([kind, label]) => {
              const n = o.types[kind] ?? 0
              return { key: kind, label, value: n, hint: fmtShare(n, o.sessions.human) }
            })}
            empty="Keine Sessions im Zeitraum."
          />
          <p className="dash-note">
            Bestätigt menschlich: {fmtInt(o.sessions.human)} von {fmtInt(o.sessions.all)} Sessions — eine Interaktion oder
            eine zweite Seite. Der Rest kann Bot oder abspringender Mensch sein.
          </p>
        </>
      )}
    </Panel>
  )
}
