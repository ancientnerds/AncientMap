import { useRef, useLayoutEffect } from 'react'

interface FitTextProps {
  text: string
  maxPx: number
  minPx: number
  lines: number
  lineHeight?: number
  className?: string
}

const cache = new Map<string, number>()

export function FitText({ text, maxPx, minPx, lines, lineHeight = 1.45, className }: FitTextProps) {
  const ref = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return

    const key = `${text}|${el.clientWidth}|${maxPx}|${minPx}|${lines}`
    const cached = cache.get(key)
    if (cached) {
      el.style.fontSize = `${cached}px`
      return
    }

    let size = maxPx
    el.style.fontSize = `${size}px`

    while (el.scrollHeight > el.clientHeight && size > minPx) {
      size -= 0.5
      el.style.fontSize = `${size}px`
    }

    if (el.scrollHeight > el.clientHeight) {
      el.style.display = '-webkit-box'
      el.style.webkitBoxOrient = 'vertical'
      el.style.webkitLineClamp = `${lines}`
    }

    cache.set(key, size)
  }, [text, maxPx, minPx, lines, lineHeight])

  const height = lines * maxPx * lineHeight

  return (
    <div
      ref={ref}
      className={className}
      style={{ height, lineHeight, overflow: 'hidden', fontSize: maxPx }}
    >
      {text}
    </div>
  )
}
