import { BarList, type BarItem } from './BarList'
import { fmtInt, fmtShare } from './format'
import { HowCounted, Panel, Status } from './Panel'
import type { DeviceCount, DevicesData, LanguageCount } from './types'
import type { Loaded } from './useStats'

/** How many language rows the list draws. SQL_DEVICES deliberately carries no
 *  LIMIT — the panel divides by the row total, so a cut tail would shrink the
 *  denominator — and a ninety-day window can hand a half-width panel dozens of
 *  tags. Whatever is cut here still counts in the subtag line under the lists,
 *  which is folded from every row. */
const LANGUAGE_ROWS = 6

/** The words the backend folds device strings to (stats_analysis.py
 *  DEVICE_GROUPS). Umami's own device report calls a desktop machine with a
 *  screen of 1920 px or less a "laptop"; we fold that into desktop, so the
 *  label has to say so — a founder reading both reports sees a laptop row
 *  there and none here, and that is the same machines, not a contradiction.
 *  A word Umami invents later is printed as it arrived. */
const DEVICE_LABELS: Record<string, string> = {
  desktop: 'Desktop, laptops included',
  mobile: 'Mobile',
  tablet: 'Tablet',
  unknown: 'No screen size reported',
}

/**
 * One device bucket, with its share printed next to the count it came from.
 * At 168 sessions (2026-09-19) four sessions move the share by three points,
 * so a percentage alone would be read as precision this sample cannot carry.
 */
export function deviceItem(d: DeviceCount, sessions: number): BarItem {
  return {
    key: `device:${d.device}`,
    label: DEVICE_LABELS[d.device] ?? d.device,
    value: d.sessions,
    hint: `${fmtShare(d.sessions, sessions)} of ${fmtInt(sessions)}`,
  }
}

/** One language row, titled with the full tag the browser asked for: en-GB is
 *  not en-US, and that difference is the only thing a tag knows. No share —
 *  the smallest live tag is four sessions and "2 %" of 168 is noise. */
export function languageItem(l: LanguageCount): BarItem {
  return { key: `lang:${l.language}`, label: l.language, value: l.sessions }
}

/**
 * "Mobile is 45 of 168 sessions (27 %)." — the one headline this panel has,
 * and the number a reading of Umami's device report got wrong by folding its
 * laptop row into phones. Tablets are their own row and are not in here.
 * A bucket with no sessions is absent from the list, which is zero.
 */
export function mobileLine(d: DevicesData): string {
  // Nothing, not the sentence the empty list above already prints — the note
  // is a second voice, not an echo.
  if (d.sessions === 0) return ''
  const mobile = d.devices.find(x => x.device === 'mobile')?.sessions ?? 0
  return `Mobile is ${fmtInt(mobile)} of ${fmtInt(d.sessions)} sessions (${fmtShare(mobile, d.sessions)}).`
}

/** "By primary subtag: en 114, zh 11, de 7, tr 4 of 168 sessions." — the one
 *  resolution at which this sample says something: en-US and en-GB are one
 *  audience, and five separate rows of 93 / 21 / 11 / 7 / 4 are not. */
export function groupLine(groups: LanguageCount[], sessions: number): string {
  // Empty for the same reason as mobileLine(): the language list says it.
  if (groups.length === 0) return ''
  const parts = groups.map(g => `${g.language} ${fmtInt(g.sessions)}`).join(', ')
  return `By primary subtag: ${parts} of ${fmtInt(sessions)} sessions.`
}

/** What the visitors browse with, and what language they asked us for. */
export function Devices({ state }: { state: Loaded<DevicesData> }) {
  const d = state.data
  return (
    <Panel question="What do they browse with, and in what language?">
      <Status state={state} />
      {d && (
        <>
          <h3>Devices</h3>
          <BarList
            items={d.devices.map(x => deviceItem(x, d.sessions))}
            empty="No session in this window."
          />
          <h3>Languages</h3>
          <BarList
            items={d.languages.slice(0, LANGUAGE_ROWS).map(languageItem)}
            empty="No browser sent a language tag in this window."
          />
          <p className="dash-note">
            {mobileLine(d)} {groupLine(d.language_groups, d.sessions)}
          </p>
          <HowCounted>
            At most {LANGUAGE_ROWS} tags are listed; the subtag line covers every session in the window. A
            client that sent no tag has a device row and no language row, which is why the language counts
            can add up to less than the sessions. Every session with an event is in here, confirmed human
            or not — the fingerprints the Scrapers panel flags are inside these numbers, and they are one
            machine each.
          </HowCounted>
        </>
      )}
    </Panel>
  )
}
