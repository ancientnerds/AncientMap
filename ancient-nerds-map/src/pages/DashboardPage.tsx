/**
 * The founders dashboard at https://stats.ancientnerds.com/ — twenty-one panels,
 * each titled with the question it answers, fed by /api/stats/* behind the
 * an_stats cookie (api/routes/stats_access.py). Mobile first: one column,
 * two from 720 px. Umami itself stays one link away.
 */
import anLogo from '../components/dashboard/an-logo-green.svg'
import { Attention } from '../components/dashboard/Attention'
import { Crawlers } from '../components/dashboard/Crawlers'
import { Creators } from '../components/dashboard/Creators'

import { Devices } from '../components/dashboard/Devices'
import { FeedbackInbox } from '../components/dashboard/FeedbackInbox'
import { FieldVitals } from '../components/dashboard/FieldVitals'
import { GlobeReach } from '../components/dashboard/GlobeReach'
import { Growth } from '../components/dashboard/Growth'
import { LiveNow } from '../components/dashboard/LiveNow'
import { Members } from '../components/dashboard/Members'
import { panelId } from '../components/dashboard/Panel'
import { Paths } from '../components/dashboard/Paths'
import { Problems } from '../components/dashboard/Problems'
import { Pulse } from '../components/dashboard/Pulse'
import { Reading } from '../components/dashboard/Reading'
import { Scrapers } from '../components/dashboard/Scrapers'
import { SearchGoogle } from '../components/dashboard/SearchGoogle'
import { ServerLoad } from '../components/dashboard/ServerLoad'
import { SessionTypes } from '../components/dashboard/SessionTypes'
import { Sources } from '../components/dashboard/Sources'
import { TopContent } from '../components/dashboard/TopContent'
import type {
  ClustersData,
  ContentData,
  CountriesData,
  CrawlersData,
  CreatorsData,
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
  ServerData,
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

/** The tracker's first event (Umami, 2026-09-17 10:03 UTC). Every panel that
 *  counts visits reads the whole history from here (owner, 2026-10-10: "ich
 *  will immer alle Werte sehen, nicht die letzten x Tage"). */
const TRACKER_START = Date.UTC(2026, 8, 17)
const DAY_MS = 86_400_000
/** Days back to the tracker's first event, today included; the page loads
 *  once, and a day's growth while it stays open is the next load's. */
const ALL_DAYS = Math.ceil((Date.now() - TRACKER_START) / DAY_MS) + 1
/** The one panel that keeps a window: a JavaScript error fixed a month ago
 *  would otherwise stay red in the list and in the warnings for good. */
const PROBLEM_DAYS = 7

/** The jump bar: a short name for every panel, in the page's order, linked to
 *  the panel's anchor (panelId of its question). Twenty-one panels run to
 *  11,000 px on a desktop and 16,000 on a phone; this is the way across. */
const JUMPS: Array<[string, string]> = [
  ['Now', 'Who is here right now?'],
  ['Growth', 'Is the audience growing?'],
  ['Google', 'How does Google see us?'],
  ['Map', 'Where are the visitors?'],
  ['Server', 'Is the server keeping up?'],
  ['Sources', 'Where do they come from, and how many do we miss?'],
  ['Content', 'What gets opened, what gets searched?'],
  ['Creators', 'How much do we send to the creators?'],
  ['Crawlers', 'Who crawls us?'],
  ['Speed', 'Are we fast for Google?'],
  ['Globe', 'Does the globe actually come up?'],
  ['Paths', 'How do they move through the site, and where do they leave?'],
  ['Reading', 'How far do they read?'],
  ['Kinds', 'What do visitors do?'],
  ['Devices', 'What do they browse with, and in what language?'],
  ['Members', 'Who signed up, and did they come back?'],
  ['Attention', 'What needs attention?'],
  ['Problems', 'Where does the platform fail them?'],
  ['Feedback', 'What do visitors say?'],
  ['Live', 'What are they looking at right now?'],
  ['Scrapers', 'How many of those are one machine?'],
]

function JumpBar() {
  return (
    <nav className="dash-jumps" aria-label="Panels">
      {JUMPS.map(([name, question]) => (
        <a key={name} href={`#${panelId(question)}`}>
          {name}
        </a>
      ))}
    </nav>
  )
}

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
  const overview = useStats<Overview>(`overview?days=${ALL_DAYS}`)
  const map = useStats<MapData>(`map?days=${ALL_DAYS}`)
  // Fixed windows (now / today / 7 / 30): the question is who is here.
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
  const crawlers = useStats<CrawlersData>(`crawlers?days=${ALL_DAYS}`, 300_000)
  // The host samples itself every five minutes; asking more often shows nothing new.
  const server = useStats<ServerData>('server', 300_000)
  const globe = useStats<GlobeData>(`globe?days=${ALL_DAYS}`)
  // Five minutes: a scraper fingerprint does not change from minute to minute,
  // and this is the one query that has to sort every event in the window.
  const clusters = useStats<ClustersData>(`clusters?days=${ALL_DAYS}`, 300_000)
  const content = useStats<ContentData>(`content?days=${ALL_DAYS}`)
  const creators = useStats<CreatorsData>(`creators?days=${ALL_DAYS}`, 300_000)
  const feedback = useStats<FeedbackData>(`feedback?days=${ALL_DAYS}`)
  const sources = useStats<SourcesData>(`sources?days=${ALL_DAYS}`)
  // One request for two panels: the scroll ladder travels inside /journeys, so
  // Paths and Reading share this state and Reading costs no query of its own.
  const journeys = useStats<JourneysData>(`journeys?days=${ALL_DAYS}`)
  const problems = useStats<ProblemsData>(`problems?days=${PROBLEM_DAYS}`)
  const devices = useStats<DevicesData>(`devices?days=${ALL_DAYS}`)
  // Five minutes, all-time counts: five members do not move in sixty seconds.
  const members = useStats<MembersData>('members', 300_000)
  // `members` is deliberately not in this array. It is the only route on a
  // different database behind a different dependency, and one hiccup there must
  // not replace the other twenty panels with "Session expired".
  const panels = [
    overview, countries, daily, search, vitals, crawlers, server, map, live, globe,
    clusters, content, creators, feedback, sources, journeys, problems, devices,
  ]
  const unauthorized = panels.some(s => s.error === 'unauthorized')

  return (
    <main className="dash">
      <header className="dash-header">
        <a className="dash-mark" href="/">
          <img className="dash-logo" src={anLogo} alt="" width={22} height={20} />
          <b>Ancient Nerds</b> · Founders
        </a>
        <nav className="dash-nav" aria-label="Other pages">
          <a href={UMAMI_HREF}>Umami</a>
          <a href="/logout">Sign out</a>
        </nav>
      </header>
      {!unauthorized && <JumpBar />}
      {unauthorized ? (
        <Entry />
      ) : (
        <div className="dash-grid">
          {/* Owner, 2026-10-10: the charts, the map and the bar lists first -
              who is here, whether the audience grows, Google, the map - then
              the rest of the pictures, and the panels that are mostly text
              last. The narrow panels go in pairs, so the two-column grid has
              no hole before the last one. */}
          <Pulse state={overview} countries={countries} />
          <Growth state={daily} />
          <SearchGoogle state={search} />
          <VisitorMap state={map} />
          <ServerLoad state={server} />
          <Sources state={sources} daily={daily} />
          <TopContent state={content} />
          <Creators state={creators} />
          <Crawlers state={crawlers} />
          <FieldVitals state={vitals} />
          <GlobeReach state={globe} />
          <Paths state={journeys} />
          <Reading state={journeys} />
          <SessionTypes state={overview} />
          <Devices state={devices} />
          <Members state={members} />
          <Attention problems={problems} globe={globe} content={content} search={search} vitals={vitals} server={server} />
          <Problems state={problems} />
          <FeedbackInbox state={feedback} />
          <LiveNow state={live} />
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
