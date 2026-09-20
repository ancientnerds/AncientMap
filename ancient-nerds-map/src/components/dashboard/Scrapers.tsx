import { BarList, type BarItem } from './BarList'
import { fmtInt, fmtShare } from './format'
import { Panel, Status } from './Panel'
import type { Cluster, ClustersData, Overview } from './types'
import type { Loaded } from './useStats'

/** One fingerprint as a bar row: screen, browser and operating system. */
export function clusterItem(c: Cluster): BarItem {
  const parts = [c.screen, c.browser, c.os].filter(Boolean)
  return {
    key: parts.join('|') || 'unknown',
    label: parts.length ? parts.join(' · ') : 'unknown machine',
    value: c.sessions,
    hint: 'sessions',
  }
}

/**
 * How much of the session count above is one machine. The rule is one rule: a
 * page load several session ids reached inside the same minute. Cookieless
 * analytics gives a stateless client a fresh id per request, so that is the
 * one thing a headless fetcher cannot hide.
 */
export function Scrapers({ state, overview }: { state: Loaded<ClustersData>; overview: Loaded<Overview> }) {
  const c = state.data
  // The denominator lives in another endpoint. When /overview has not answered
  // (or failed), print the count alone — never "38 of 0 sessions (0 %)".
  const all = overview.data?.sessions.all ?? null
  return (
    <Panel question="How many of those are one machine?">
      <Status state={state} />
      {c && (
        <>
          <BarList
            items={c.clusters.map(clusterItem)}
            empty="No path was touched by several session ids inside one minute in this window."
          />
          <p className="dash-note">
            {fmtInt(c.flagged)}
            {all === null ? '' : ` of ${fmtInt(all)} sessions (${fmtShare(c.flagged, all)})`} sat inside a
            group that {c.min_ids} or more session ids reached on the same path in the same minute. The
            two numbers cover the same window but are up to five minutes apart — this panel refreshes
            every five minutes, the session count every minute. Read every other number on this page with
            that subtracted. Declared crawlers never get this far: Umami drops GPTBot, ClaudeBot and
            PerplexityBot before the insert, so they are invisible here — "and the rest are people" does
            not follow.
          </p>
        </>
      )}
    </Panel>
  )
}
