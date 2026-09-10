/**
 * PagePortal — a screenshot of the real page inside a NERV window, and the
 * link into it.
 *
 * Owner, 2026-09-10: "I want a kind of portal to the pages — like a
 * screenshot that shows the current state." A version in between laid a
 * live <iframe> of the page over the screenshot on desktops, and the verdict
 * on that was: "Those are no screenshots! It lags like hell! The landing
 * page must load super fast — and mobile first!" Four framed pages were four
 * more page loads, four React bundles and the search's whole site index on a
 * homepage nobody asked to run them; that was the lag. So: a screenshot,
 * nothing else — on every device.
 *
 * The poster is a real screenshot of its page, captured against production
 * every six hours by .github/workflows/previews.yml
 * (scripts/capture-previews.mjs) and served from /data/previews/ in two
 * widths: the 640 px frame for phones and narrow cells, the 1280 px one
 * where the window is wider than that at the device's pixel ratio. Lazy,
 * async-decoded and below the fold, it costs the first paint nothing.
 *
 * The one interactive thing is the link that covers the whole box and
 * carries the CTA into the page. No effect, no state, no browser API: the
 * server renders exactly what the client shows.
 */
interface Props {
  /** Poster name under /data/previews/, e.g. "news" — the PAGES table in capture-previews.mjs. */
  poster: string
  /** The page's name for people — the poster alt. */
  title: string
  openHref: string
  openLabel: string
}

/** The capture is 1280×800 (capture-previews.mjs); the 640 variant is the same frame at half scale. */
const POSTER_WIDTH = 1280
const POSTER_HEIGHT = 800
const POSTER_DIR = '/data/previews'

export default function PagePortal({ poster, title, openHref, openLabel }: Props) {
  const full = `${POSTER_DIR}/${poster}.webp`
  const half = `${POSTER_DIR}/${poster}-640.webp`
  return (
    <div className="ll-portal">
      <img
        className="ll-portal-poster"
        src={full}
        srcSet={`${half} 640w, ${full} 1280w`}
        // The window body's width: half the 1200 px page above it, the
        // viewport minus the page and window padding below (landing-live.css).
        sizes="(min-width: 1200px) 540px, (min-width: 901px) calc(50vw - 60px), calc(100vw - 72px)"
        alt={`${title} — current view`}
        width={POSTER_WIDTH}
        height={POSTER_HEIGHT}
        loading="lazy"
        decoding="async"
      />
      {/* aria-label, because the visible text ends in a glyph a screen reader
          would read as "north east arrow". */}
      <a className="ll-portal-link" href={openHref} aria-label={openLabel}>
        <span className="cta-primary ll-portal-cta">{`${openLabel} ↗`}</span>
      </a>
    </div>
  )
}
