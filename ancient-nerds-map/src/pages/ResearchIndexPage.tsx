/**
 * ResearchIndexPage — /research/, the open-access research library hub.
 *
 * A real listing since react-ssr Task 12: the payload carries every
 * published paper, so the crawler, the no-JS visitor and the hydrated page
 * all see the same cards. Before the cutover researchMain redirected this
 * route to /theo.html#research-library before mount — crawlers saw nothing.
 *
 * The cards are Theo's image cards since 2026-09-10 (owner: "the research
 * library should have the cards, not plain headings") — PaperCard, the very
 * component /theo.html renders, with the footer line the public library has
 * always printed. The homepage shows this page through its portal, so the
 * cards live here and nowhere else.
 *
 * The papers are AI-generated (Theo pipeline) — the Art. 50 notice
 * banner is mandatory here, exactly like on the paper pages.
 */

import Breadcrumbs from '../components/layout/Breadcrumbs'
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import PaperCard from '../components/theo/PaperCard'
import { paperCardFooter } from '../seo/display'
import { useRoute } from '../seo/RouteContext'

import '../styles/story-page.css'

export default function ResearchIndexPage() {
  const route = useRoute()
  if (route?.type !== 'researchIndex') return null
  const { papers } = route

  return (
    <div className="story-page">
      <PageHeader currentPage="theo">
        <span className="page-header-title">Research</span>
      </PageHeader>
      <AiNoticeBanner message="Research paper text is AI-generated; images are from cited sources. Always verify claims with original sources." />
      <main className="story-main">
        <Breadcrumbs trail={[{ name: 'Home', path: '/' }, { name: 'Research' }]} />
        <h1 className="story-title">Research Library</h1>
        <div className="story-meta">{papers.length} open-access papers · CC BY 4.0</div>
        <div className="theo-public-grid">
          {papers.map(p => (
            <PaperCard
              key={p.slug}
              href={`/research/${p.slug}`}
              paper={{ title: p.title, cover: p.hero_image_url, description: p.summary }}
              footer={paperCardFooter({
                author: p.author,
                published_at: p.published_at,
                sources_analyzed: p.sources_analyzed,
                words: p.word_count,
              })}
            />
          ))}
        </div>
        <CommunityCta />
      </main>
    </div>
  )
}
