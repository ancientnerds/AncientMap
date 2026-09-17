import { useState } from 'react'

import { pageType } from '../../analytics'
import { fmtStamp } from './format'
import { Panel, Status } from './Panel'
import type { FeedbackData, FeedbackItem } from './types'
import type { Loaded } from './useStats'

const MAIN_ORIGIN = 'https://ancientnerds.com'

/** Labels of src/analytics/feedback.ts FeedbackPromptKind. */
const PROMPT_LABELS: Record<string, string> = {
  search_empty: 'Leere Suche',
  story_end: 'Story',
  not_found: 'Seite fehlt',
  site_page: 'Site-Seite',
  paper_end: 'Paper',
  journal_end: 'Journal',
  lyra_answer: 'Lyra-Antwort',
}

/** What was rated, as a label and — where we can build one — a link to it.
 *  The event carries an id or a slug; the page it happened on is the fallback. */
export function target(item: FeedbackItem): { label: string; href?: string } {
  if (item.paper) return { label: item.paper, href: `${MAIN_ORIGIN}/research/${item.paper}` }
  if (item.journal) return { label: item.journal, href: `${MAIN_ORIGIN}/articles/${item.journal}` }
  if (item.site) {
    const label = item.country ? `${item.country} · ${item.site.slice(0, 8)}` : item.site.slice(0, 8)
    return { label, href: `${MAIN_ORIGIN}/globe.html#focus=${item.site}` }
  }
  if (item.story) return { label: `Story ${item.story}` }
  if (item.url_path) return { label: pageType(item.url_path), href: `${MAIN_ORIGIN}${item.url_path}` }
  return { label: '—' }
}

/** Criticism is what you act on: a thumbs down, or any written sentence. */
export function isCriticism(item: FeedbackItem): boolean {
  return item.answer === 'no' || Boolean(item.text && item.text.trim())
}

/**
 * Every feedback answer of the last 30 days, newest first: when, what was
 * rated, the verdict and the sentence. The filter starts on the criticism,
 * because that is the half that asks for work.
 */
export function FeedbackInbox({ state }: { state: Loaded<FeedbackData> }) {
  const [onlyCriticism, setOnlyCriticism] = useState(true)
  const all = state.data?.items ?? []
  const critical = all.filter(isCriticism)
  const items = onlyCriticism ? critical : all

  return (
    <Panel question="Was sagen die Besucher?" wide>
      <Status state={state} />
      {state.data && (
        <div className="dash-feedback-filter" role="group" aria-label="Feedback filtern">
          <button
            type="button"
            className={onlyCriticism ? 'is-active' : undefined}
            onClick={() => setOnlyCriticism(true)}
          >
            Kritik &amp; Kommentare ({critical.length})
          </button>
          <button
            type="button"
            className={onlyCriticism ? undefined : 'is-active'}
            onClick={() => setOnlyCriticism(false)}
          >
            Alles ({all.length})
          </button>
        </div>
      )}
      {state.data && items.length === 0 && (
        <p className="dash-empty">
          {onlyCriticism ? 'Keine Kritik in 30 Tagen.' : 'Kein Feedback in 30 Tagen.'}
        </p>
      )}
      {items.length > 0 && (
        <ul className="dash-feedback">
          {items.map(it => {
            const what = target(it)
            return (
              <li
                key={`${it.created_at}:${it.url_path}:${it.text}`}
                className={it.answer === 'no' ? 'is-negative' : undefined}
              >
                <span className="dash-feedback-meta">
                  <span>{fmtStamp(it.created_at)}</span>
                  <span>{PROMPT_LABELS[it.prompt ?? ''] ?? it.prompt ?? '—'}</span>
                  {it.answer === 'yes' && <span className="dash-chip dash-chip--yes">Ja</span>}
                  {it.answer === 'no' && <span className="dash-chip dash-chip--no">Nein</span>}
                  {what.href ? (
                    <a href={what.href} title={what.label}>
                      {what.label}
                    </a>
                  ) : (
                    <span title={what.label}>{what.label}</span>
                  )}
                </span>
                {it.text && <span className="dash-feedback-text">{it.text}</span>}
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
