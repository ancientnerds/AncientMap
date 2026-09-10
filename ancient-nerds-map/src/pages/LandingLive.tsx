/**
 * LandingLive — the four data-fresh homepage sections rendered into
 * index.html's #root by the SSR sidecar (api/routes/landing_html.py).
 * Hero and screenshot sections around #root stay static HTML; this tree
 * is the only React on the page.
 *
 * Four portals, one shape (PortalSection.tsx), laid out two by two from
 * 901 px up (landing-live.css): Stories and Journal on the first row,
 * Papers and Sites on the second (owner, 2026-09-11: "stories and journal
 * on one row, research and sites on the second"). Document order is the
 * same, so a phone, a screen reader and a crawler read them in that order.
 */
import PortalSection from '../landing/PortalSection'
import TheoLine from '../landing/TheoLine'
import { useRoute } from '../seo/RouteContext'

import '../styles/landing-live.css'

/** 1759673 → "1,759,673". Explicit en-US: the SSR host has a locale of its own. */
const count = (n: number) => n.toLocaleString('en-US')

export default function LandingLive() {
  const route = useRoute()
  if (route?.type !== 'landing') return null
  const { stats, journals, papers } = route
  return (
    <div className="landing-live">
      <PortalSection
        id="stories-live"
        fig={1}
        name="stories, live"
        status={`${count(stats.stories)} stories · newest first`}
        page="/news.html"
        poster="/data/previews/news.jpg"
        title="Stories"
        openLabel="Open stories"
        archive={{ href: '/news-archive/', title: 'Story archive' }}
        foot={{ note: 'lead = highest significance of the last 48h · then newest first', link: 'all stories →' }}
      />
      {journals && (
        <PortalSection
          id="journal-live"
          fig={2}
          name="weekly journal"
          status={`${journals.total} issues · every Sunday`}
          page="/articles.html"
          poster="/data/previews/articles.jpg"
          title="Weekly journals"
          openLabel="Open journals"
          foot={{ note: 'every Sunday · sourced, cited, illustrated', link: `all ${journals.total} journals →` }}
        />
      )}
      {papers && (
        <PortalSection
          id="papers-live"
          fig={3}
          name="research papers"
          status={`${papers.total} public · CC BY 4.0 · by Theo`}
          page="/research/"
          poster="/data/previews/research.jpg"
          title="Research library"
          openLabel="Open research library"
          foot={{ note: 'papers publish when the citation gate passes · all titles are listed below', link: 'research library →' }}
        >
          {papers.theo && <TheoLine theo={papers.theo} />}
        </PortalSection>
      )}
      <PortalSection
        id="sites-live"
        fig={4}
        name="site search"
        status={`${count(stats.sites)} sites · ${stats.sources} sources`}
        page="/search.html"
        view="/search.html?random"
        poster="/data/previews/search.jpg"
        title="Site search"
        openLabel="Open site search"
        archive={{ href: '/sites/', title: 'Sites by country' }}
        foot={{ note: 'type three letters or hit Random · filter by country, category, period and source', link: 'search all sites →' }}
      />
    </div>
  )
}
