/**
 * The founders dashboard at https://stats.ancientnerds.com/ — eight panels,
 * each titled with the question it answers, fed by /api/stats/* behind the
 * an_stats cookie (api/routes/stats_access.py). Mobile first: one column,
 * two from 720 px. Umami itself stays one link away.
 */
import { useState } from 'react'

import { FeedbackInbox } from '../components/dashboard/FeedbackInbox'
import { Journeys } from '../components/dashboard/Journeys'
import { Problems } from '../components/dashboard/Problems'
import { Pulse } from '../components/dashboard/Pulse'
import { SessionTypes } from '../components/dashboard/SessionTypes'
import { Sources } from '../components/dashboard/Sources'
import { TopContent } from '../components/dashboard/TopContent'
import type {
  ContentData,
  FeedbackData,
  JourneysData,
  MapData,
  Overview,
  ProblemsData,
  SourcesData,
} from '../components/dashboard/types'
import { useStats } from '../components/dashboard/useStats'
import { VisitorMap } from '../components/dashboard/VisitorMap'

/** Same target as the entry page's button (stats_access.gate_html): OAuth on the main host, handoff back here. */
const ENTRY_HREF = 'https://ancientnerds.com/api/auth/discord?return_to=%2Fapi%2Fauth%2Fstats-handoff'
/** Umami's own UI on this host; the deploy names the website id in .env. */
const UMAMI_HREF = `/websites/${import.meta.env.VITE_UMAMI_WEBSITE_ID ?? ''}`

type Days = 7 | 30

function Entry() {
  return (
    <section className="dash-panel dash-entry">
      <h2>Sitzung abgelaufen</h2>
      <p>Die Founder-Sitzung gilt zwölf Stunden. Einmal neu anmelden, dann geht es hier weiter.</p>
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
  const content = useStats<ContentData>(`content?days=${days}`)
  const feedback = useStats<FeedbackData>('feedback?days=30')
  const sources = useStats<SourcesData>(`sources?days=${days}`)
  const journeys = useStats<JourneysData>(`journeys?days=${days}`)
  const problems = useStats<ProblemsData>(`problems?days=${days}`)
  const panels = [overview, map, content, feedback, sources, journeys, problems]
  const unauthorized = panels.some(s => s.error === 'unauthorized')

  return (
    <main className="dash">
      <header className="dash-header">
        <a className="dash-mark" href="/">
          <b>Ancient Nerds</b> · Founders
        </a>
        <div className="dash-range" role="group" aria-label="Zeitraum">
          {([7, 30] as Days[]).map(d => (
            <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)}>
              {d} Tage
            </button>
          ))}
        </div>
        <nav className="dash-nav" aria-label="Weitere Seiten">
          <a href={UMAMI_HREF}>Umami</a>
          <a href="/logout">Abmelden</a>
        </nav>
      </header>
      {unauthorized ? (
        <Entry />
      ) : (
        <div className="dash-grid">
          <Pulse state={overview} days={days} />
          <VisitorMap state={map} />
          <SessionTypes state={overview} />
          <Sources state={sources} />
          <Journeys state={journeys} />
          <Problems state={problems} />
          <TopContent state={content} />
          <FeedbackInbox state={feedback} />
        </div>
      )}
      <footer className="dash-footer">
        Cookielos: Besucher werden nur innerhalb eines Kalendermonats wiedererkannt. Zeiten in UTC wie in Umami.
      </footer>
    </main>
  )
}
