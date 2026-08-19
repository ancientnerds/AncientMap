/**
 * SignificanceInfo — the "?" next to the significance slider.
 *
 * Click/tap instead of a hover tooltip so it works on touch too. Outside
 * click and Escape close it. Deliberately a sibling of the slider's <label>,
 * never inside it: a button within a label forwards its click to the range
 * input and would move the slider.
 */

import { useEffect, useRef, useState } from 'react'
import { getSignificanceLabel } from './significance'

/** Scale rows, top down — labels come from the same table the cards stamp. */
const SCALE: Array<[number, string]> = [
  [9, '9–10'],
  [7, '7–8'],
  [5, '5–6'],
  [3, '3–4'],
  [1, '1–2'],
]

export default function SignificanceInfo({ mode }: { mode: 'min' | 'max' }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null
      if (target && !containerRef.current?.contains(target)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('touchstart', onDown, { passive: true })
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('touchstart', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <span className="news-page-sig-info" ref={containerRef}>
      <button
        type="button"
        className="news-page-sig-info-btn"
        aria-label="How the significance score works"
        aria-expanded={open}
        onClick={() => setOpen(v => !v)}
      >
        ?
      </button>
      {open && (
        <span role="tooltip" className="news-page-sig-info-bubble">
          <strong>Significance</strong> — Lyra scores every story 1–10 while
          reading the source.
          <span className="news-page-sig-scale">
            {SCALE.map(([level, range]) => (
              <span key={range}>
                <b>{range}</b> {getSignificanceLabel(level)}
              </span>
            ))}
          </span>
          {mode === 'max'
            ? 'Sorted low to high, the slider is a ceiling: only stories at or below the value.'
            : 'The slider is a floor: only stories at or above the value.'}
        </span>
      )}
    </span>
  )
}
