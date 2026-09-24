/**
 * Every dashboard panel, rendered. renderToString needs no DOM — the same
 * pattern as CommunityCta.test.tsx and the SSR sidecar — and every panel here
 * is a plain function component, so all three states a founder can meet are
 * reachable from a test: data, "failed", and data that is empty.
 *
 * What this file is for: the guards that exist to keep a number from lying
 * (Scrapers dropping its denominator when /overview is down, Reading refusing
 * to render a heading with nothing under it, TopContent naming only the lists
 * that are actually empty) had no verification of any kind. The screenshot
 * pass answers every endpoint with 200, so it cannot reach them either.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { Devices } from '../Devices'
import { FeedbackInbox } from '../FeedbackInbox'
import { GlobeReach } from '../GlobeReach'
import { LiveNow } from '../LiveNow'
import { Members } from '../Members'
import { Paths } from '../Paths'
import { Problems } from '../Problems'
import { Pulse } from '../Pulse'
import { Reading } from '../Reading'
import { Scrapers } from '../Scrapers'
import { SessionTypes } from '../SessionTypes'
import { Sources } from '../Sources'
import { TopContent } from '../TopContent'
import type {
  ClustersData,
  ContentData,
  CountriesData,
  CountryWindow,
  DevicesData,
  FeedbackData,
  GlobeData,
  JourneysData,
  LiveData,
  MembersData,
  Overview,
  ProblemsData,
  SourcesData,
} from '../types'
import type { Loaded } from '../useStats'
import { VisitorMap } from '../VisitorMap'

const ok = <T,>(data: T): Loaded<T> => ({ data, error: null })
const failed = { data: null, error: 'failed' } as const
const expired = { data: null, error: 'unauthorized' } as const

/** The text under the panel's own title — what is left when the heading and
 *  every tag are gone. A panel whose body is empty is the one thing the page
 *  may not ship. */
function body(html: string): string {
  return html
    .replace(/<h2>.*?<\/h2>/, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

const window0: CountryWindow = { sessions: 0, all: 0, countries: [] }
const hour = { hour: '2026-09-19T08:00:00+00:00', sessions: 0, human: 0, ai: 0 }

const EMPTY = {
  overview: { days: 7, sessions: { all: 0, human: 0, ai: 0 }, types: {}, hours: [hour, hour] } as Overview,
  countries: { now: window0, today: window0, d7: window0, d30: window0 } as CountriesData,
  map: { points: [] },
  live: {
    window_minutes: 30,
    lookback_hours: 24,
    total: 0,
    shown: 0,
    visitors: [],
    last: null,
  } as LiveData,
  globe: {
    loads: 0,
    reached: 0,
    gave_up: 0,
    sessions: { all: 0, reached: 0 },
    ready_ms: { min: null, median: null, max: null, samples: 0 },
    // Explicit, not left to the cast: without these keys the empty-state test
    // below would exercise the old-API branch instead of the empty one.
    not_reached: { gate: 0, unsupported: 0, error: 0, abandoned: 0, no_signal: 0, unmeasured: 0 },
    abandon_ms: { min: null, median: null, max: null, samples: 0 },
  } as GlobeData,
  clusters: { min_ids: 3, flagged: 0, clusters: [] } as ClustersData,
  content: { sites: [], stories: [], papers: [], searches: [] } as ContentData,
  feedback: { items: [] } as FeedbackData,
  journeys: {
    chains: [],
    pages: { sessions: 0, one_page: 0, moving: 0, entries: [], exits: [] },
    outbound: [],
    reading: { steps: [25, 50, 75, 100], readers: 0, pages: [] },
  } as JourneysData,
  problems: { problems: [] } as ProblemsData,
  sources: {
    sources: [],
    log: {
      covered_from: '2026-09-12T00:00:00+00:00',
      covered_days: 7,
      lines: 0,
      unverified: 0,
      families: [],
      hosts: [],
      statuses: [],
    },
    log_reason: null,
  } as SourcesData,
  devices: { sessions: 0, devices: [], languages: [], language_groups: [] } as DevicesData,
  members: {
    members: 0,
    founders: 2,
    newest_signup: null,
    last_login: null,
    acts: [{ act: 'Likes', n: 0, by: 0, at: null }],
  } as MembersData,
}

/** Every panel with an answer that carries nothing. */
const emptyPanels: Array<[string, JSX.Element]> = [
  ['Pulse', <Pulse state={ok(EMPTY.overview)} countries={ok(EMPTY.countries)} />],
  ['LiveNow', <LiveNow state={ok(EMPTY.live)} />],
  ['GlobeReach', <GlobeReach state={ok(EMPTY.globe)} />],
  ['Scrapers', <Scrapers state={ok(EMPTY.clusters)} overview={ok(EMPTY.overview)} />],
  ['Problems', <Problems state={ok(EMPTY.problems)} />],
  ['VisitorMap', <VisitorMap state={ok(EMPTY.map)} />],
  ['Sources', <Sources state={ok(EMPTY.sources)} />],
  ['SessionTypes', <SessionTypes state={ok(EMPTY.overview)} />],
  ['Members', <Members state={ok(EMPTY.members)} />],
  ['Paths', <Paths state={ok(EMPTY.journeys)} />],
  ['Reading', <Reading state={ok(EMPTY.journeys)} />],
  ['Devices', <Devices state={ok(EMPTY.devices)} />],
  ['TopContent', <TopContent state={ok(EMPTY.content)} />],
  ['FeedbackInbox', <FeedbackInbox state={ok(EMPTY.feedback)} />],
]

/** The same panels with nothing at all — a 500 on their endpoint. */
const failedPanels: Array<[string, JSX.Element]> = [
  ['Pulse', <Pulse state={failed} countries={failed} />],
  ['LiveNow', <LiveNow state={failed} />],
  ['GlobeReach', <GlobeReach state={failed} />],
  ['Scrapers', <Scrapers state={failed} overview={failed} />],
  ['Problems', <Problems state={failed} />],
  ['VisitorMap', <VisitorMap state={failed} />],
  ['Sources', <Sources state={failed} />],
  ['SessionTypes', <SessionTypes state={failed} />],
  ['Members', <Members state={failed} />],
  ['Paths', <Paths state={failed} />],
  ['Reading', <Reading state={failed} />],
  ['Devices', <Devices state={failed} />],
  ['TopContent', <TopContent state={failed} />],
  ['FeedbackInbox', <FeedbackInbox state={failed} />],
]

describe('every panel in its empty state', () => {
  it.each(emptyPanels)('%s says something under its title', (_name, element) => {
    const html = renderToString(element)
    expect(html).toContain('<h2>')
    expect(body(html).length).toBeGreaterThan(20)
  })
})

describe('every panel when its endpoint fails', () => {
  it.each(failedPanels)('%s says the data is unavailable', (_name, element) => {
    expect(renderToString(element)).toContain('Data unavailable.')
  })

  it('says "Session expired" instead when the cookie ran out', () => {
    expect(renderToString(<Problems state={expired} />)).toContain('Session expired.')
  })
})

describe('Scrapers', () => {
  it('prints the flagged count alone while /overview has not answered', () => {
    // Two independent fetches on two intervals (300 s and 60 s), so this is an
    // ordinary state. "38 of 0 sessions (0 %)" is what a `?? 0` would print.
    const html = renderToString(
      <Scrapers state={ok({ ...EMPTY.clusters, flagged: 38 })} overview={failed} />
    )
    expect(html).toContain('38')
    expect(html).not.toContain(' of 0 sessions')
    expect(html).not.toContain('(0 %)')
  })

  it('divides by /overview once it is there', () => {
    const html = renderToString(
      <Scrapers
        state={ok({ ...EMPTY.clusters, flagged: 38 })}
        overview={ok({ ...EMPTY.overview, sessions: { all: 168, human: 46, ai: 13 } })}
      />
    )
    expect(html).toContain('of 168 sessions')
  })
})

describe('Pulse', () => {
  it('announces a failed /overview instead of dropping the strip in silence', () => {
    // The tiles come from /countries and the strip from /overview. Before this,
    // a 500 on the heavier of the two left a complete-looking panel with no
    // hourly strip and no AI sentence, and nothing on screen said so.
    const html = renderToString(<Pulse state={failed} countries={ok(EMPTY.countries)} />)
    expect(html).toContain('Data unavailable.')
    expect(html).not.toContain('dash-spark')
  })
})

describe('Reading', () => {
  it('does not render a heading with nothing under it when `reading` is missing', () => {
    // Every deploy has this window: ci.yml builds the frontend (nginx serves
    // the new bundle at once) before it rebuilds the API.
    const older = { ...EMPTY.journeys } as Partial<JourneysData>
    delete older.reading
    const html = renderToString(<Reading state={ok(older as JourneysData)} />)
    expect(html).toContain('Data unavailable.')
    expect(body(html).length).toBeGreaterThan(10)
  })
})

describe('GlobeReach', () => {
  const some: GlobeData = {
    ...EMPTY.globe,
    loads: 12,
    reached: 5,
    gave_up: 7,
    sessions: { all: 9, reached: 4 },
    ready_ms: { min: 3100, median: 4200, max: 9900, samples: 5 },
    not_reached: { gate: 2, unsupported: 1, error: 1, abandoned: 1, no_signal: 2, unmeasured: 0 },
    abandon_ms: { min: 6100, median: null, max: 6100, samples: 1 },
  }

  it('splits the loads that never got there under the two tiles', () => {
    const html = renderToString(<GlobeReach state={ok(some)} />)
    expect(html).toContain('Globe loads')
    expect(html).toContain('<h3>')
    for (const label of ['Stopped at the phone gate', 'Device cannot run the globe', 'Error while starting', 'Left while loading', 'No signal']) {
      expect(html).toContain(label)
    }
    expect(html).not.toContain('Before these were recorded')
    expect(html).toContain('The one load left while loading had waited 6.1 s.')
    expect(html).not.toContain('Data unavailable.')
  })

  it('names the loads from before the endings were recorded while there are any', () => {
    const older = { ...some, not_reached: { ...some.not_reached, no_signal: 0, unmeasured: 2 } }
    const html = renderToString(<GlobeReach state={ok(older)} />)
    expect(html).toContain('Before these were recorded')
    // The stale first load after the deploy belongs there too: the service worker
    // served it from the previous build, which sends no ending (SQL_GLOBE)
    expect(html).toContain(
      'Before these were recorded: loads from before the globe started reporting how a load ends, and the first load after that by a returning visitor, which their browser still ran from the previous build.',
    )
    // Not all of them: a returning visitor from an earlier month is a new Umami session
    expect(html).toContain('Some of those still land in No signal: to Umami a visit in an earlier month is another visitor.')
  })

  it('prints one sentence instead of an all-zero list when every load arrived', () => {
    const all = { ...some, reached: 12, gave_up: 0, not_reached: EMPTY.globe.not_reached }
    const html = renderToString(<GlobeReach state={ok(all)} />)
    expect(html).toContain('Every load in this window reached the globe.')
    expect(html).not.toContain('<h3>')
  })

  it('keeps the tiles and says the split is unavailable when the API predates it', () => {
    // Every deploy has this window: ci.yml builds the frontend (nginx serves
    // the new bundle at once) before it rebuilds the API.
    const older = { ...some } as Partial<GlobeData>
    delete older.not_reached
    delete older.abandon_ms
    const html = renderToString(<GlobeReach state={ok(older as GlobeData)} />)
    expect(html).toContain('Globe loads')
    expect(html).toContain('Reached the globe')
    expect(html).toContain('Data unavailable.')
    expect(html).not.toContain('<h3>')
  })
})

describe('TopContent', () => {
  it('never says an event has not fired while it is ranking that event', () => {
    const filled: ContentData = {
      sites: [{ event_name: 'site_open', label: 'Göbekli Tepe', country: 'Türkiye', results: null, n: 41 }],
      stories: [{ event_name: 'story_open', label: 'bronze-age-crete', country: null, results: null, n: 58 }],
      papers: [{ event_name: 'paper_open', label: '/research/p', country: null, results: null, n: 27 }],
      searches: [{ event_name: 'search', label: 'giza', country: null, results: 14, n: 23 }],
    }
    const html = renderToString(<TopContent state={ok(filled)} />)
    expect(html).toContain('bronze-age-crete')
    expect(html).not.toContain('never fired')
    expect(html).not.toContain('ticket T2')
  })

  it('names the search bug only while the search list is empty', () => {
    const html = renderToString(<TopContent state={ok(EMPTY.content)} />)
    expect(html).toContain('ticket T2')
  })
})

describe('Sources', () => {
  it('explains the missing log instead of drawing empty lists', () => {
    const reason = 'nginx&#x27;s referral log is not readable at /app/logs/referrals.log.'
    const html = renderToString(
      <Sources state={ok({ ...EMPTY.sources, log: null, log_reason: "nginx's referral log is not readable at /app/logs/referrals.log." })} />
    )
    expect(html).toContain(reason)
    expect(html).not.toContain('Hosts nginx saw')
  })

  it('says so in words when the log holds no referred arrival', () => {
    const html = renderToString(<Sources state={ok(EMPTY.sources)} />)
    expect(html).toContain('No referred arrival in this window.')
    expect(html).toContain('Every referred visitor got a page.')
    expect(html).toContain('No sessions in this window.')
  })

  it('counts referrer spam out of the lists and names it in the note', () => {
    const html = renderToString(
      <Sources state={ok({ ...EMPTY.sources, log: { ...EMPTY.sources.log!, unverified: 17 } })} />
    )
    expect(html).toContain('17 arrivals in this window')
    expect(html).not.toContain('Bots and our own development server are out of every list')
  })
})

describe('Problems', () => {
  it('renders a row that can date itself and one that cannot', () => {
    // The `empty_search` fallback is the shape that carries neither: it is
    // folded from the session counter, which knows no moment and no visitor.
    const data: ProblemsData = {
      problems: [
        {
          kind: 'js_error',
          label: 'x is not a function',
          score: 15,
          detail: '5 visitors, 12× on globe',
          at: '2026-09-19T08:12:00+00:00',
          last: { session: 'cf01aa30', country: 'CH', device: 'laptop', browser: 'chrome' },
        },
        {
          kind: 'empty_search',
          label: 'search',
          score: 4,
          detail: '4 searches found nothing',
          at: null,
          last: null,
        },
      ],
    }
    const html = renderToString(<Problems state={ok(data)} />)
    expect(html).toContain('cf01aa30')
    expect(html).toContain('4 searches found nothing')
    // Severity is not carried by colour alone: the dot names its own tier.
    expect(html).toContain('aria-label="high"')
    expect(html).toContain('aria-label="low"')
  })
})
