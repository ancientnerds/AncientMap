/**
 * PagePortal — the real page, scaled down, running inside a NERV window.
 *
 * Owner, 2026-09-10: "I want a kind of portal to the pages — like a
 * screenshot that shows the current state." Not a screenshot: an <iframe> on
 * the live URL, so the window is never stale and there is no second renderer
 * to keep in sync.
 *
 * What the server sends is NOT the iframe. SSR and the first client render
 * emit the container, the link into the page and one muted line, so the two
 * trees match and a crawler sees a link instead of a frame it will not
 * follow. The frame appears after mount, and only when it is worth it:
 *
 * - viewport ≥ 900 px — below that the window is one column and a 1280 px
 *   page scaled into a phone is unreadable, so mobile keeps link + line;
 * - no Save-Data — a whole second page is exactly what that header asks us
 *   not to load;
 * - scrolled into view (IntersectionObserver, 200 px ahead), so three
 *   portals do not cost three page loads on a homepage nobody scrolled.
 *
 * Scale: the frame is laid out at a desktop 1280×800 and transformed to the
 * container's width, which a ResizeObserver writes into --ll-portal-scale.
 * Pointer events stay on — the visitor may scroll inside the portal.
 */
import { useEffect, useRef, useState } from 'react'

interface Props {
  /** Same-origin page the portal shows, e.g. "/news.html". */
  src: string
  title: string
  openHref: string
  openLabel: string
}

/** The breakpoint of the landing sections: below it the window is one column. */
const DESKTOP = '(min-width: 900px)'
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
    if (!window.matchMedia(DESKTOP).matches) return
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
        />
      )}
      {/* Once the page is in the frame the link has no room of its own left,
          so it moves into the corner on top of it. */}
      <a className={live ? 'll-portal-open ll-portal-open--over' : 'll-portal-open'} href={openHref}>
        {`${openLabel} ↗`}
      </a>
      {!live && <span className="ll-meta">{`live view of ${src}`}</span>}
    </div>
  )
}
