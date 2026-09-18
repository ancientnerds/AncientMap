import { BarList } from './BarList'
import { Panel, Status } from './Panel'
import type { SourceRow, SourcesData } from './types'
import type { Loaded } from './useStats'

export type SourceBucket = 'search' | 'ai' | 'discord' | 'youtube' | 'direct' | 'other'

const BUCKET_LABELS: Array<[SourceBucket, string]> = [
  ['search', 'Search'],
  ['ai', 'AI assistants'],
  ['discord', 'Discord'],
  ['youtube', 'YouTube'],
  ['direct', 'Direct'],
  ['other', 'Other'],
]

const RAW_ROWS = 8

/** The founders' six buckets over pipeline/stats_analysis.py source_family(). */
export function sourceBucket(family: string): SourceBucket {
  const f = family.toLowerCase()
  if (f === 'google' || f === 'search') return 'search'
  if (f === 'ai') return 'ai'
  if (f === 'direct') return 'direct'
  if (f.includes('discord')) return 'discord'
  if (f.includes('youtube') || f.includes('youtu.be')) return 'youtube'
  return 'other'
}

/** Sessions per bucket, in the fixed display order. */
export function bucketTotals(rows: SourceRow[]): Array<[SourceBucket, string, number]> {
  const totals: Record<SourceBucket, number> = { search: 0, ai: 0, discord: 0, youtube: 0, direct: 0, other: 0 }
  for (const r of rows) totals[sourceBucket(r.family)] += r.sessions
  return BUCKET_LABELS.map(([bucket, label]) => [bucket, label, totals[bucket]])
}

/** Where the sessions came from: six buckets, then the raw referrers behind them. */
export function Sources({ state }: { state: Loaded<SourcesData> }) {
  const s = state.data
  return (
    <Panel question="Where do they come from?">
      <Status state={state} />
      {s && (
        <>
          <BarList
            items={bucketTotals(s.sources).map(([bucket, label, n]) => ({ key: bucket, label, value: n }))}
            empty="No sessions in this window."
          />
          <h3>Individual sources</h3>
          <BarList
            items={s.sources.slice(0, RAW_ROWS).map(r => ({ key: r.source, label: r.source, value: r.sessions }))}
            empty="No sources."
          />
        </>
      )}
    </Panel>
  )
}
