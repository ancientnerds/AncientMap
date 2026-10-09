/**
 * The founders dashboard at https://stats.ancientnerds.com/ — nineteen panels,
 * each titled with the question it answers, fed by /api/stats/* behind the
 * an_stats cookie (api/routes/stats_access.py). Mobile first: one column,
 * two from 720 px. Umami itself stays one link away.
 */
import { useState } from 'react'

import anLogo from '../components/dashboard/an-logo-green.svg'
import { Attention } from '../components/dashboard/Attention'
import { Crawlers } from '../components/dashboard/Crawlers'

import { Devices } from '../components/dashboard/Devices'
import { FeedbackInbox } from '../components/dashboard/FeedbackInbox'
import { FieldVitals } from '../components/dashboard/FieldVitals'
import { GlobeReach } from '../components/dashboard/GlobeReach'
import { Growth } from '../components/dashboard/Growth'
import { LiveNow } from '../components/dashboard/LiveNow'
import { Members } from '../components/dashboard/Members'
import { Paths } from '../components/dashboard/Paths'
import { Problems } from '../components/dashboard/Problems'
import { Pulse } from '../components/dashboard/Pulse'
import { Reading } from '../components/dashboard/Reading'
import { Scrapers } from '../components/dashboard/Scrapers'
import { SearchGoogle } from '../components/dashboard/SearchGoogle'
import { SessionTypes } from '../components/dashboard/SessionTypes'
import { Sources } from '../components/dashboard/Sources'
import { TopContent } from '../components/dashboard/TopContent'
import type {
  ClustersData,
  ContentData,
  CountriesData,
  CrawlersData,
  DailyData,
  DevicesData,
  FeedbackData,
  FieldVitalsData,
  GlobeData,
  JourneysData,
  LiveData,
  MapData,
  MembersData,
  Overview,
  ProblemsData,
  SearchData,
  SourcesData,
} from '../components/dashboard/types'
import { useStats } from '../components/dashboard/useStats'
import { VisitorMap } from '../components/dashboard/VisitorMap'

/** Same target as the entry page's button (stats_access.gate_html): OAuth on the main host, handoff back here. */
const ENTRY_HREF = 'https://ancientnerds.com/api/auth/discord?return_to=%2Fapi%2Fauth%2Fstats-handoff'
/** The main site's pages run analytics/boot.ts, which reads ?notrack= and sets
 *  or clears the key Umami's tracker checks before every send. The setting
 *  lives in that site's storage, so it is per browser: once on every device. */
const NOTRACK_OFF_HREF = 'https://ancientnerds.com/news.html?notrack=1'
const NOTRACK_ON_HREF = 'https://ancientnerds.com/news.html?notrack=0'
/** Umami's own UI on this host; the deploy names the website id in .env. */
const UMAMI_HREF = `/websites/${import.meta.env.VITE_UMAMI_WEBSITE_ID ?? ''}`

type Days = 7 | 30

function Entry() {
  return (
    <section className="dash-panel dash-entry">
      <h2>Session expired</h2>
      <p>A founder session lasts twelve hours. Sign in once more and this picks up where it left off.</p>
      <a className="dash-btn" href={ENTRY_HREF}>
        Continue with Discord
      </a>
    </section>
  )
}

export default function DashboardPage() {
  const [days, setDays] = useState<Days>(7)
  const [rangeHelp, setRangeHelp] = useState(false)
  const overview = useStats<Overview>(`overview?days=${days}`)
  const map = useStats<MapData>('map?days=1')
  // Fixed windows (now / today / 7 / 30) — the range switch does not touch them.
  const countries = useStats<CountriesData>('countries')
  // Fixed 30-minute window, same 60 s cadence as everything else on the page.
  const live = useStats<LiveData>('live')
  // The whole history, cached five minutes on the server: a day's point only
  // grows during that day.
  const daily = useStats<DailyData>('daily', 300_000)
  // Google's side: Search Console is read once an hour and CrUX once a week on
  // the server, so asking every ten minutes and every hour is plenty.
  const search = useStats<SearchData>('search', 600_000)
  const vitals = useStats<FieldVitalsData>('field-vitals', 3_600_000)
  const crawlers = useStats<CrawlersData>(`crawlers?days=${days}`, 300_000)
  const globe = useStats<GlobeData>(`globe?days=${days}`)
  // Five minutes: a scraper fingerprint does not change from minute to minute,
  // and this is the one query that has to sort every event in the window.
  const clusters = useStats<ClustersData>(`clusters?days=${days}`, 300_000)
  const content = useStats<ContentData>(`content?days=${days}`)
  const feedback = useStats<FeedbackData>('feedback?days=30')
  const sources = useStats<SourcesData>(`sources?days=${days}`)
  // One request for two panels: the scroll ladder travels inside /journeys, so
  // Paths and Reading share this state and Reading costs no query of its own.
  const journeys = useStats<JourneysData>(`journeys?days=${days}`)
  const problems = useStats<ProblemsData>(`problems?days=${days}`)
  const devices = useStats<DevicesData>(`devices?days=${days}`)
  // Five minutes, all-time counts: five members do not move in sixty seconds.
  const members = useStats<MembersData>('members', 300_000)
  // `members` is deliberately not in this array. It is the only route on a
  // different database behind a different dependency, and one hiccup there must
  // not replace the other eighteen panels with "Session expired".
  const panels = [
    overview, countries, daily, search, vitals, crawlers, map, live, globe,
    clusters, content, feedback, sources, journeys, problems, devices,
  ]
  const unauthorized = panels.some(s => s.error === 'unauthorized')

  return (
    <main className="dash">
      <header className="dash-header">
        <a className="dash-mark" href="/">
          <img className="dash-logo" src={anLogo} alt="" width={22} height={20} />
          <b>Ancient Nerds</b> · Founders
        </a>
        <div className="dash-range" role="group" aria-label="Time range">
          {([7, 30] as Days[]).map(d => (
            <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)}>
              {d} days
            </button>
          ))}
          <button
            type="button"
            className="dash-range-help"
            aria-expanded={rangeHelp}
            aria-label="What the range changes"
            onClick={() => setRangeHelp(o => !o)}
          >
            ?
          </button>
        </div>
        <nav className="dash-nav" aria-label="Other pages">
          <a href={UMAMI_HREF}>Umami</a>
          <a href="/logout">Sign out</a>
        </nav>
      </header>
      {/* Under the switch, because that is where it is read, and closed like
          every other explanation on the page: the switch drives only the
          panels that count visits in a window, and until 2026-10-17 both
          settings return the same numbers. Without this line a founder would
          conclude the switch is broken. */}
      <p className="dash-note" hidden={!rangeHelp}>
        The range drives the panels that count visits in a window. Is the audience growing, How does Google see
        us, Are we fast for Google, Live now, Where are the visitors, Members and Feedback have windows of their
        own, and Who is here has four — only its last sentence follows the range. Until 17 October both settings
        return the same numbers everywhere: the tracker's first event is 17 September.
      </p>
      {unauthorized ? (
        <Entry />
      ) : (
        <div className="dash-grid">
          {/* Most relevant first (owner, 2026-10-09: "je weiter ich runterscrolle,
              desto unrelevanter"): what needs doing, whether the audience grows,
              how Google sees us, then who is here and where they come from; the
              detail and the curiosities last. The narrow panels go in pairs, so
              the two-column grid has no hole before the last one. */}
          <Attention problems={problems} globe={globe} content={content} search={search} vitals={vitals} />
          <Growth state={daily} />
          <SearchGoogle state={search} />
          <Pulse state={overview} countries={countries} />
          <Sources state={sources} />
          <TopContent state={content} />
          <Problems state={problems} />
          <FieldVitals state={vitals} />
          <GlobeReach state={globe} />
          <Crawlers state={crawlers} />
          <FeedbackInbox state={feedback} />
          <Paths state={journeys} />
          <Reading state={journeys} />
          <SessionTypes state={overview} />
          <Devices state={devices} />
          <Members state={members} />
          <LiveNow state={live} />
          <VisitorMap state={map} />
          <Scrapers state={clusters} overview={overview} />
        </div>
      )}
      <footer className="dash-footer">
        <p>Cookieless: a visitor is only recognised again within one calendar month. Times in UTC, as in Umami.</p>
        <p>
          Our own visits count like anyone's.{' '}
          <a href={NOTRACK_OFF_HREF}>Stop counting this browser</a> ·{' '}
          <a href={NOTRACK_ON_HREF}>count it again</a> — once on every browser and phone you use; it opens
          the Stories page.
        </p>
      </footer>
    </main>
  )
}
