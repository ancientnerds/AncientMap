import { useState } from 'react'

import { pageType } from '../../analytics'
import { fmtStamp } from './format'
import { Panel, Status } from './Panel'
import type { FeedbackData, FeedbackItem } from './types'
import type { Loaded } from './useStats'

const MAIN_ORIGIN = 'https://ancientnerds.com'

/** Labels of src/analytics/feedback.ts FeedbackPromptKind. */
const PROMPT_LABELS: Record<string, string> = {
  search_empty: 'Empty search',
  story_end: 'Story',
  not_found: 'Missing page',
  site_page: 'Site page',
  paper_end: 'Paper',
  journal_end: 'Journal',
  lyra_answer: 'Lyra answer',
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

/** Five minutes: the window in which the sentence belongs to the vote. */
const PAIR_WINDOW_MS = 5 * 60 * 1000

/**
 * One complaint, one row. ThumbsFeedback sends the verdict the moment it is
 * given and the sentence a few seconds later, so an unfinished comment never
 * costs us the vote — but the inbox would otherwise list a commented thumbs
 * down twice and count it twice in the filter. Keep the row that carries the
 * sentence; drop the bare vote it belongs to.
 */
export function collapsePairs(items: FeedbackItem[]): FeedbackItem[] {
  const key = (i: FeedbackItem) =>
    [i.prompt, i.answer, i.site, i.paper, i.journal, i.story, i.url_path].join('|')
  const withText = items.filter(i => i.text && i.text.trim())
  return items.filter(bare => {
    if (bare.text && bare.text.trim()) return true
    const at = Date.parse(bare.created_at)
    return !withText.some(
      full =>
        key(full) === key(bare) && Math.abs(Date.parse(full.created_at) - at) <= PAIR_WINDOW_MS
    )
  })
}

/**
 * Every feedback answer of the last 30 days, newest first: when, what was
 * rated, the verdict and the sentence. The filter starts on the criticism,
 * because that is the half that asks for work.
 */
export function FeedbackInbox({ state }: { state: Loaded<FeedbackData> }) {
  const [onlyCriticism, setOnlyCriticism] = useState(true)
  const all = collapsePairs(state.data?.items ?? [])
  const critical = all.filter(isCriticism)
  const items = onlyCriticism ? critical : all

  return (
    <Panel question="What do visitors say?" wide>
      <Status state={state} />
      {state.data && (
        <div className="dash-feedback-filter" role="group" aria-label="Filter feedback">
          <button
            type="button"
            className={onlyCriticism ? 'is-active' : undefined}
            onClick={() => setOnlyCriticism(true)}
          >
            Criticism &amp; comments ({critical.length})
          </button>
          <button
            type="button"
            className={onlyCriticism ? undefined : 'is-active'}
            onClick={() => setOnlyCriticism(false)}
          >
            Everything ({all.length})
          </button>
        </div>
      )}
      {state.data && items.length === 0 && (
        <p className="dash-empty">
          {onlyCriticism ? 'No criticism in 30 days.' : 'No feedback in 30 days.'}
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
                  {it.answer === 'yes' && <span className="dash-chip dash-chip--yes">Yes</span>}
                  {it.answer === 'no' && <span className="dash-chip dash-chip--no">No</span>}
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
