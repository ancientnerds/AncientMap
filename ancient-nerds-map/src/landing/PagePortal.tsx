/**
 * PagePortal — the real page inside a NERV window: a screenshot always, the
 * live page on top of it where a desktop can afford one.
 *
 * Owner, 2026-09-10: "I want a kind of portal to the pages — like a
 * screenshot that shows the current state", and a day later, from the phone:
 * "On the phone everything flickers quite a bit — are screenshots maybe
 * better after all?" Both, then. Every portal carries a poster — a real
 * screenshot of its page, captured against production every six hours by
 * .github/workflows/previews.yml and served from /data/previews/. Phones and
 * tablets see nothing else: no second page load, no layout thrash, no
 * flicker. Hover-capable desktops at 900 px and up mount the <iframe> over
 * the poster, so the window there is never stale.
 *
 * The frame is DECORATION, not a second browser: pointer-events off,
 * tabIndex -1, aria-hidden. Nothing inside it can be scrolled, clicked or
 * tabbed into, so a wheel or a swipe over the portal scrolls the homepage
 * (owner, 2026-09-10: "scrolling inside the portal is prevented so I can
 * scroll the page normally"). The one interactive thing is the link that
 * covers the whole box and carries the CTA into the page.
 *
 * What the server sends is NOT the iframe. SSR and the first client render
 * emit the container, the poster and that link, so the two trees match and a
 * crawler sees an image and a link instead of a frame it will not follow.
 * Beyond the media query the frame is held back by Save-Data — a whole
 * second page is exactly what that header asks us not to load — and it waits
 * until the window scrolls into view (IntersectionObserver, 200 px ahead),
 * so three portals do not cost three page loads on a homepage nobody
 * scrolled.
 *
 * Scale: the frame is laid out at a desktop 1280×800 and transformed to the
 * container's width, which a ResizeObserver writes into --ll-portal-scale.
 */
import { useEffect, useRef, useState } from 'react'

interface Props {
  /** Same-origin page the portal shows, e.g. "/news.html". */
  src: string
  /** Screenshot of that page under /data/previews/, e.g. "/data/previews/news.jpg". */
  poster: string
  title: string
  openHref: string
  openLabel: string
}

/** Layout width of the framed page — the scale divisor, so it lives here. */
const FRAME_WIDTH = 1280
/** ...and its layout height, which the poster is captured at. */
const FRAME_HEIGHT = 800
/**
 * Where a live frame is worth its cost: a pointer to reveal it with and room
 * to read it in. Decided once at mount — this is a class of device, not a
 * window size to follow around.
 */
const DESKTOP = '(hover: hover) and (min-width: 900px)'
/** Save-Data is not in lib.dom: the Network Information API is a draft. */
type SaveDataNavigator = Navigator & { connection?: { saveData?: boolean } }

export default function PagePortal({ src, poster, title, openHref, openLabel }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [live, setLive] = useState(false)

  useEffect(() => {
    const el = box.current
    if (!el) return
    if ((navigator as SaveDataNavigator).connection?.saveData) return
    if (!window.matchMedia(DESKTOP).matches) return
    // Measuring starts before the frame exists, so the very first painted
    // frame is already at the right scale instead of at the CSS default.
    const resize = new ResizeObserver(entries => {
      for (const entry of entries) {
        el.style.setProperty('--ll-portal-scale', String(entry.contentRect.width / FRAME_WIDTH))
      }
    })
    resize.observe(el)
    const visible = new IntersectionObserver(
      entries => {
        if (!entries.some(e => e.isIntersecting)) return
        visible.disconnect()
        setLive(true)
      },
      { rootMargin: '200px' },
    )
    visible.observe(el)
    return () => {
      resize.disconnect()
      visible.disconnect()
    }
  }, [])

  return (
    <div className="ll-portal" data-src={src} ref={box}>
      <img
        className="ll-portal-poster"
        src={poster}
        alt={`${title} — current view`}
        width={FRAME_WIDTH}
        height={FRAME_HEIGHT}
        loading="lazy"
        decoding="async"
      />
      {live && (
        <iframe
          className="ll-portal-frame"
          src={src}
          title={title}
          loading="lazy"
          referrerPolicy="same-origin"
          tabIndex={-1}
          aria-hidden="true"
        />
      )}
      {/* aria-label, because the visible text ends in a glyph a screen reader
          would read as "north east arrow". */}
      <a className="ll-portal-link" href={openHref} aria-label={openLabel}>
        <span className="cta-primary ll-portal-cta">{`${openLabel} ↗`}</span>
      </a>
    </div>
  )
}
