/**
 * JournalHub — die Übersicht /articles/ mit Lead-Ausgabe und Thumbnails.
 *
 * Seit 2026-10-12 ist das die einzige Liste im Journal: der Crawl-Hub
 * /articles/ zeichnet aus dem Route-Payload genau das Layout, das vorher nur
 * die Standalone-SPA /articles.html drew (Hero + Thumbnail-Grid). Klassen und
 * Reihenfolge sind deshalb unverändert aus deren Markup übernommen — kein
 * neuer Entwurf, derselbe an der kanonischen URL.
 *
 * Alle Karten sind echte <a href="/articles/{slug}">: crawlbar, mit
 * Mittelklick und ohne JavaScript erreichbar. Die Lead-Ausgabe trägt den
 * <h2>, das <h1> der Seite bleibt "Weekly Archaeology Journal".
 */

import type { JournalIndexCard } from '../../types/anRoute'

/** Jul 27 – Aug 2, bzw. mit Jahr, wenn die Woche über eine Grenze läuft. */
function weekRange(card: JournalIndexCard): string | null {
  if (!card.week_start || !card.week_end) return null
  const start = new Date(card.week_start)
  const end = new Date(card.week_end)
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }
  const withYear: Intl.DateTimeFormatOptions = { ...opts, year: 'numeric' }
  if (start.getFullYear() !== end.getFullYear()) {
    return `${start.toLocaleDateString('en-US', withYear)} – ${end.toLocaleDateString('en-US', withYear)}`
  }
  return `${start.toLocaleDateString('en-US', opts)} – ${end.toLocaleDateString('en-US', opts)}`
}

function ReadTime({ minutes }: { minutes: number }) {
  return <span className="articles-reader-readtime">~{minutes} min read</span>
}

function JournalCard({ card, lead }: { card: JournalIndexCard; lead?: boolean }) {
  const range = weekRange(card)
  const image = card.thumbnail_url ? (
    <img
      src={card.thumbnail_url}
      alt={card.title}
      className={lead ? 'articles-hero-img' : 'articles-grid-card-img'}
      loading="lazy"
    />
  ) : null

  // Lead: Titel und Datum über einem zweispaltigen Kopf (Text links, Bild
  // rechts). Karte: Bild oben, darunter Titel, Datum, Blurb — die Reihenfolge
  // des alten /articles.html-Markups, auf die .articles-grid-card-img mit
  // eigenem Abstand geschrieben ist.
  if (lead) {
    return (
      <a className="articles-hero" href={`/articles/${card.slug}`}>
        <h2 className="articles-hero-title">{card.title}</h2>
        <span className="articles-hero-date">
          {range}
          <ReadTime minutes={card.reading_minutes} />
        </span>
        <div className="articles-hero-body">
          {card.summary && <p className="articles-hero-summary">{card.summary}</p>}
          {image}
        </div>
        <div className="articles-hero-actions">
          <span className="articles-hero-cta">Read Journal</span>
        </div>
      </a>
    )
  }

  return (
    <a className="articles-grid-card" href={`/articles/${card.slug}`}>
      {image}
      <h2 className="articles-grid-card-title">{card.title}</h2>
      <span className="articles-grid-card-date">
        {range}
        <ReadTime minutes={card.reading_minutes} />
      </span>
      {card.summary && <p className="articles-grid-card-summary">{card.summary}</p>}
    </a>
  )
}

export default function JournalHub({ cards }: { cards: JournalIndexCard[] }) {
  if (cards.length === 0) {
    return <div className="articles-page-empty">No journals yet. Check back soon.</div>
  }
  const [lead, ...older] = cards
  return (
    <>
      <JournalCard card={lead} lead />
      {older.length > 0 && (
        <section className="articles-grid-section">
          <span className="articles-grid-label">PREVIOUS JOURNALS</span>
          <div className="articles-grid">
            {older.map(card => (
              <JournalCard key={card.slug} card={card} />
            ))}
          </div>
        </section>
      )}
    </>
  )
}