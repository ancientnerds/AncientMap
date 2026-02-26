import { useRef, useLayoutEffect } from 'react'

interface FitTextProps {
  text: string
  maxPx: number
  lines: number
  lineHeight?: number
  className?: string
}

const cache = new Map<string, number>()

export function FitText({ text, maxPx, lines, lineHeight = 1.45, className }: FitTextProps) {
  const ref = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return

    function fit() {
      const el = ref.current
      if (!el) return

      const w = el.clientWidth
      const h = el.clientHeight
      if (h === 0 || w === 0) return

      const key = `${text}|${w}|${h}|${maxPx}|${lines}`
      const cached = cache.get(key)
      if (cached) {
        el.style.fontSize = `${cached}px`
        return
      }

      // Quick check: does it fit at maxPx?
      el.style.fontSize = `${maxPx}px`
      if (el.scrollHeight <= h) {
        cache.set(key, maxPx)
        return
      }

      // Binary search between 1px and maxPx, 0.25px precision
      let lo = 1
      let hi = maxPx
      while (hi - lo > 0.25) {
        const mid = (lo + hi) / 2
        el.style.fontSize = `${mid}px`
        if (el.scrollHeight <= h) {
          lo = mid
        } else {
          hi = mid
        }
      }

      el.style.fontSize = `${lo}px`
      cache.set(key, lo)
    }

    fit()

    const ro = new ResizeObserver(() => fit())
    ro.observe(el)

    return () => ro.disconnect()
  }, [text, maxPx, lines, lineHeight])

  const height = lines * maxPx * lineHeight

  return (
    <div
      ref={ref}
      className={className}
      style={{
        height,
        lineHeight,
        overflow: 'hidden',
        fontSize: maxPx,
        textAlign: 'justify',
        textAlignLast: 'left',
        textWrap: 'pretty',
        flexShrink: 1,
        minHeight: 0,
      }}
    >
      {text}
    </div>
  )
}
