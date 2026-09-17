import { pageType } from '../../analytics'
import { fmtStamp } from './format'
import { Panel, Status } from './Panel'
import type { FeedbackData } from './types'
import type { Loaded } from './useStats'

const MAIN_ORIGIN = 'https://ancientnerds.com'

/** Labels of src/analytics/feedback.ts FeedbackPromptKind (site_page and lyra_answer arrive with Part A). */
const PROMPT_LABELS: Record<string, string> = {
  search_empty: 'Leere Suche',
  story_end: 'Story-Ende',
  not_found: 'Seite fehlt',
  site_page: 'Site-Seite',
  lyra_answer: 'Lyra-Antwort',
}

/** Every feedback answer of the last 30 days, newest first: when, where, what. */
export function FeedbackInbox({ state }: { state: Loaded<FeedbackData> }) {
  const f = state.data
  return (
    <Panel question="Was sagen die Besucher?" wide>
      <Status state={state} />
      {f && f.items.length === 0 && <p className="dash-empty">Kein Feedback in 30 Tagen.</p>}
      {f && f.items.length > 0 && (
        <ul className="dash-feedback">
          {f.items.map(it => (
            <li key={`${it.created_at}:${it.url_path}:${it.text}`}>
              <span className="dash-feedback-meta">
                <span>{fmtStamp(it.created_at)}</span>
                <span>{PROMPT_LABELS[it.prompt ?? ''] ?? it.prompt ?? '—'}</span>
                {it.answer === 'yes' && <span className="dash-chip dash-chip--yes">Ja</span>}
                {it.answer === 'no' && <span className="dash-chip dash-chip--no">Nein</span>}
                {it.url_path && (
                  <a href={`${MAIN_ORIGIN}${it.url_path}`} title={it.url_path}>
                    {pageType(it.url_path)}
                  </a>
                )}
              </span>
              {it.text && <span className="dash-feedback-text">{it.text}</span>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
