/**
 * The Stories section: a NERV window with a portal on /news.html.
 *
 * Nothing but the portal (2026-09-10, owner: "I want a kind of portal to the
 * pages — like a screenshot that shows the current state" and "Why do we
 * still have the list of stories … on the right side?"). The live story page
 * IS the list, so a second one beside it said the same thing twice; the
 * category chips and "load more" went with it, together with the client that
 * refetched /api/news/feed. The section has no state left.
 */
import LandingWindow from './LandingWindow'
import PagePortal from './PagePortal'
import SectionHead from './SectionHead'

export default function LandingStories({ total }: { total: number }) {
  return (
    <section className="ll-section" id="stories-live" aria-labelledby="ll-fig-1">
      <SectionHead fig={1} name="stories, live" status={`${total.toLocaleString('en-US')} stories · newest first`} />
      <LandingWindow
        title={
          <>
            {'>_ portal — '}
            <b>/news.html</b>
          </>
        }
        openHref="/news.html"
        openTitle="Open stories"
        archive={{ href: '/news-archive/', title: 'Story archive' }}
      >
        <PagePortal
          src="/news.html"
          title="Stories — live view"
          openHref="/news.html"
          openLabel="Open stories"
        />
      </LandingWindow>
      <div className="ll-foot">
        <span>lead = highest significance of the last 48h · then newest first</span>
        <a href="/news.html">all stories →</a>
      </div>
    </section>
  )
}
