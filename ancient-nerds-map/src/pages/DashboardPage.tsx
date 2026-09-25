/**
 * The founders dashboard at https://stats.ancientnerds.com/ — fourteen panels,
 * each titled with the question it answers, fed by /api/stats/* behind the
 * an_stats cookie (api/routes/stats_access.py). Mobile first: one column,
 * two from 720 px. Umami itself stays one link away.
 */
import { useState } from 'react'

import anLogo from '../components/dashboard/an-logo-green.svg'
import { Attention } from '../components/dashboard/Attention'

import { Devices } from '../components/dashboard/Devices'
import { FeedbackInbox } from '../components/dashboard/FeedbackInbox'
import { GlobeReach } from '../components/dashboard/GlobeReach'
import { LiveNow } from '../components/dashboard/LiveNow'
import { Members } from '../components/dashboard/Members'
import { Paths } from '../components/dashboard/Paths'
import { Problems } from '../components/dashboard/Problems'
import { Pulse } from '../components/dashboard/Pulse'
import { Reading } from '../components/dashboard/Reading'
import { Scrapers } from '../components/dashboard/Scrapers'
import { SessionTypes } from '../components/dashboard/SessionTypes'
import { Sources } from '../components/dashboard/Sources'
import { TopContent } from '../components/dashboard/TopContent'
import type {
  ClustersData,
  ContentData,
  CountriesData,
  DevicesData,
  FeedbackData,
  GlobeData,
  JourneysData,
  LiveData,
  MapData,
  MembersData,
  Overview,
  ProblemsData,
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
  const overview = useStats<Overview>(`overview?days=${days}`)
  const map = useStats<MapData>('map?days=1')
  // Fixed windows (now / today / 7 / 30) — the range switch does not touch them.
  const countries = useStats<CountriesData>('countries')
  // Fixed 30-minute window, same 60 s cadence as everything else on the page.
  const live = useStats<LiveData>('live')
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
  // not replace the other thirteen panels with "Session expired".
  const panels = [
    overview, countries, map, live, globe, clusters,
    content, feedback, sources, journeys, problems, devices,
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
        </div>
        <nav className="dash-nav" aria-label="Other pages">
          <a href={UMAMI_HREF}>Umami</a>
          <a href="/logout">Sign out</a>
        </nav>
      </header>
      {/* Under the switch, because that is where it is read: the switch is
          inert for five of the fourteen panels and, until 2026-10-17, returns
          identical numbers for the other nine. Without this line a founder
          concludes the switch is broken, which is the correct conclusion from
          the evidence on screen. */}
      <p className="dash-note">
        The range drives nine panels. Live now, Where are the visitors, Members and Feedback have windows
        of their own, and Who is here has four — only its last sentence follows the range. Until 17
        October both settings return the same numbers everywhere: the tracker's first event is 17
        September.
      </p>
      {unauthorized ? (
        <Entry />
      ) : (
        <div className="dash-grid">
          <Attention problems={problems} globe={globe} content={content} />
          <Pulse state={overview} countries={countries} />
          <LiveNow state={live} />
          <GlobeReach state={globe} />
          <Scrapers state={clusters} overview={overview} />
          <Problems state={problems} />
          <VisitorMap state={map} />
          <Sources state={sources} />
          <SessionTypes state={overview} />
          <Members state={members} />
          <Paths state={journeys} />
          <Reading state={journeys} />
          <Devices state={devices} />
          <TopContent state={content} />
          <FeedbackInbox state={feedback} />
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
