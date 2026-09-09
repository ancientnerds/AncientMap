/**
 * LandingLive — the three data-fresh homepage sections rendered into
 * index.html's #root by the SSR sidecar (api/routes/landing_html.py).
 * Hero and screenshot sections around #root stay static HTML; this tree
 * is the only React on the page.
 */
import LandingJournals from '../landing/LandingJournals'
import LandingPapers from '../landing/LandingPapers'
import LandingStories from '../landing/LandingStories'
import { useRoute } from '../seo/RouteContext'

import '../styles/landing-live.css'

export default function LandingLive() {
  const route = useRoute()
  if (route?.type !== 'landing') return null
  return (
    <div className="landing-live">
      {route.stories && <LandingStories initial={route.stories} total={route.stats.stories} />}
      {route.journals && <LandingJournals data={route.journals} />}
      {route.papers && <LandingPapers data={route.papers} />}
    </div>
  )
}
