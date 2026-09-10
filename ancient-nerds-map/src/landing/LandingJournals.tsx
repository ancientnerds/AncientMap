/**
 * The weekly Journal section: a NERV window with a portal on /articles.html.
 *
 * Same shape as the Stories section (2026-09-10): the live journal hub runs
 * scaled down in the window and lists its own issues, so the payload carries
 * a count and nothing else.
 */
import type { LandingRoute } from '../types/anRoute'
import LandingWindow from './LandingWindow'
import PagePortal from './PagePortal'
import SectionHead from './SectionHead'

interface Props {
  data: NonNullable<LandingRoute['journals']>
}

export default function LandingJournals({ data }: Props) {
  const { total } = data
  return (
    <section className="ll-section" id="journal-live" aria-labelledby="ll-fig-2">
      <SectionHead fig={2} name="weekly journal" status={`${total} issues · every Sunday`} />
      <LandingWindow
        title={
          <>
            {'>_ portal — '}
            <b>/articles.html</b>
          </>
        }
        openHref="/articles.html"
        openTitle="Open journals"
      >
        <PagePortal
          src="/articles.html"
          title="Weekly journals — live view"
          openHref="/articles.html"
          openLabel="Open journals"
        />
      </LandingWindow>
      <div className="ll-foot">
        <span>every Sunday · sourced, cited, illustrated</span>
        <a href="/articles.html">all {total} journals →</a>
      </div>
    </section>
  )
}
