/**
 * LayoutBox registration. In lint mode every overlay and every text element
 * of a block measures itself after each frame's render (useLayoutEffect, so
 * before Remotion takes the screenshot) and stores its box in the Registry;
 * LayoutGuard then checks all boxes of the frame. Outside lint mode nothing
 * is measured.
 */
import React, { createContext, useContext, useLayoutEffect, useRef } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useCurrentFrame, useCurrentScale } from 'remotion'

import type { Box, BoxKind } from './geometry'

export class Registry {
  readonly enabled: boolean
  readonly boxes = new Map<string, Box>()
  readonly overflow = new Set<string>()

  constructor(enabled: boolean) {
    this.enabled = enabled
  }

  set(box: Box, overflowing: boolean): void {
    this.boxes.set(box.id, box)
    if (overflowing) this.overflow.add(box.id)
    else this.overflow.delete(box.id)
  }

  remove(id: string): void {
    this.boxes.delete(id)
    this.overflow.delete(id)
  }
}

const LayoutContext = createContext<Registry | null>(null)

/** Boxes are measured relative to this element (found with closest(), which works during layout effects). */
const ROOT_ATTR = 'data-layout-root'

export const LayoutProvider: React.FC<{ registry: Registry; children: ReactNode }> = ({ registry, children }) => (
  <LayoutContext.Provider value={registry}>
    <div {...{ [ROOT_ATTR]: '' }} style={{ position: 'absolute', inset: 0 }}>
      {children}
    </div>
  </LayoutContext.Provider>
)

export function useRegistry(): Registry {
  const registry = useContext(LayoutContext)
  if (!registry) throw new Error('LayoutBox used outside LayoutProvider')
  return registry
}

/** Measure the element behind the returned ref every frame and register it as `id`. */
export function useLayoutBox<T extends HTMLElement>(id: string, kind: BoxKind, allow: readonly string[] = []): React.RefObject<T> {
  const ref = useRef<T>(null)
  const registry = useRegistry()
  const frame = useCurrentFrame()
  const scale = useCurrentScale()
  const allowKey = allow.join('|')
  useLayoutEffect(() => {
    if (!registry.enabled) return
    const el = ref.current
    const root = el?.closest(`[${ROOT_ATTR}]`)
    if (!el || !root) throw new Error(`LayoutBox ${id}: element not mounted inside the LayoutProvider`)
    const r = el.getBoundingClientRect()
    const o = root.getBoundingClientRect()
    const rect = { x: (r.left - o.left) / scale, y: (r.top - o.top) / scale, w: r.width / scale, h: r.height / scale }
    // Only a box that clips (overflow hidden) can hide text; its content must fit.
    const clips = getComputedStyle(el).overflow === 'hidden'
    const overflowing = kind === 'text' && clips && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
    registry.set({ id, kind, rect, allow: allowKey ? allowKey.split('|') : [] }, overflowing)
    return () => registry.remove(id)
  }, [registry, id, kind, allowKey, frame, scale])
  return ref
}

export const LayoutBox: React.FC<{
  id: string
  kind: BoxKind
  allow?: readonly string[]
  style?: CSSProperties
  children?: ReactNode
}> = ({ id, kind, allow, style, children }) => {
  const ref = useLayoutBox<HTMLDivElement>(id, kind, allow)
  return (
    <div ref={ref} style={style}>
      {children}
    </div>
  )
}
