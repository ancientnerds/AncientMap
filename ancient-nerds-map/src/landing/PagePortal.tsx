/**
 * PagePortal — the real page, scaled down, running inside a NERV window.
 *
 * Owner, 2026-09-10: "I want a kind of portal to the pages — like a
 * screenshot that shows the current state." Not a screenshot: an <iframe> on
 * the live URL, so the window is never stale and there is no second renderer
 * to keep in sync.
 *
 * The frame is DECORATION, not a second browser: pointer-events off,
 * tabIndex -1, aria-hidden. Nothing inside it can be scrolled, clicked or
 * tabbed into, so a wheel or a swipe over the portal scrolls the homepage
 * (owner, 2026-09-10: "scrolling inside the portal is prevented so I can
 * scroll the page normally"). The one interactive thing is the link that
 * covers the whole box and carries the CTA into the page.
 *
 * What the server sends is NOT the iframe. SSR and the first client render
 * emit the container and that link, so the two trees match and a crawler
 * sees a link instead of a frame it will not follow. The frame appears after
 * mount on every viewport — phones included, they get the 4/3 box — except
 * under Save-Data, where a whole second page is exactly what the header asks
 * us not to load, and only once the window scrolls into view
 * (IntersectionObserver, 200 px ahead), so three portals do not cost three
 * page loads on a homepage nobody scrolled.
 *
 * Scale: the frame is laid out at a desktop 1280×800 and transformed to the
 * container's width, which a ResizeObserver writes into --ll-portal-scale.
 */
import { useEffect, useRef, useState } from 'react'

interface Props {
  /** Same-origin page the portal shows, e.g. "/news.html". */
  src: string
  title: string
  openHref: string
  openLabel: string
}

/** Layout width of the framed page — the scale divisor, so it lives here. */
const FRAME_WIDTH = 1280
/** Save-Data is not in lib.dom: the Network Information API is a draft. */
type SaveDataNavigator = Navigator & { connection?: { saveData?: boolean } }

export default function PagePortal({ src, title, openHref, openLabel }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [live, setLive] = useState(false)

  useEffect(() => {
    const el = box.current
    if (!el) return
    if ((navigator as SaveDataNavigator).connection?.saveData) return
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
