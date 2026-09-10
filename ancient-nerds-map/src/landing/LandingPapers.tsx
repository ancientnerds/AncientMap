/**
 * The research Papers section: a NERV window with a portal on /research/,
 * and under it the six newest papers as a gallery.
 *
 * The gallery is Theo's card, the very component the public research library
 * renders (2026-09-10, owner: "Why is the research paper gallery so boring?
 * Why doesn't it look like Theo's research tasks, where you get cards with
 * images?"). It replaced the link list beside the portal — a hero image says
 * more than a row of numbers, and the numbers are still in the footer.
 *
 * The Theo line stays outside the window: it is the state of the agent, not
 * part of any one paper.
 */
import PaperCard from '../components/theo/PaperCard'
import { paperCardFooter } from '../seo/display'
import type { LandingRoute } from '../types/anRoute'
import LandingWindow from './LandingWindow'
import PagePortal from './PagePortal'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

interface Props {
  data: NonNullable<LandingRoute['papers']>
}

export default function LandingPapers({ data }: Props) {
  const { items, total, theo } = data
  return (
    <section className="ll-section" id="papers-live" aria-labelledby="ll-fig-3">
      <SectionHead fig={3} name="research papers" status={`${total} public · CC BY 4.0 · by Theo`} />
      <LandingWindow
        title={
          <>
            {'>_ portal — '}
            <b>/research/</b>
          </>
        }
        openHref="/research/"
        openTitle="Open research library"
      >
        <PagePortal
          src="/research/"
          title="Research library — live view"
          openHref="/research/"
          openLabel="Open research library"
        />
      </LandingWindow>
      <div className="theo-public-grid ll-gallery">
        {items.map(p => (
          <PaperCard
            key={p.slug}
            href={p.path}
            paper={{ title: p.title, cover: p.hero_image_url, description: p.summary }}
            footer={paperCardFooter(p)}
          />
        ))}
      </div>
      {theo && (
        <a className="ll-theo" href="/theo.html">
          <span>
            <i className="ll-pulse" /> Theo is researching: <b>{theo.question}</b>
            {theo.started_at ? <> · started <RelativeTime iso={theo.started_at} /></> : null} · {theo.sites_found.toLocaleString('en-US')} sites found
          </span>
          <span>watch live →</span>
        </a>
      )}
      <div className="ll-foot">
        <span>papers publish when the citation gate passes · all titles are listed below</span>
        <a href="/research/">research library →</a>
      </div>
    </section>
  )
}
