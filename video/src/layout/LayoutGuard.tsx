/**
 * Lint-mode reporter. Rendered as the LAST child of the LayoutProvider, so its
 * layout effect runs after every LayoutBox of the frame has registered (React
 * runs layout effects subtree by subtree in sibling order). It reports once
 * the brand fonts are in (LayoutBox.tsx) and then on every frame. Each
 * violation is one console.error line of JSON, which scripts/lint.ts collects
 * through onBrowserLog (test/gpu/guard.gpu.ts proves it in a real browser):
 *   {"type":"layout-violation","frame":123,"a":"captions","b":"b01:lt","reason":"overlap"}
 */
import React, { useLayoutEffect } from 'react'
import { useCurrentFrame } from 'remotion'

import { type Violation, findViolations } from './geometry'
import { useLayoutState } from './LayoutBox'

export const VIOLATION_TYPE = 'layout-violation'

/** The console line of one violation at `frame` (scripts/args.ts parseViolation reads it back). */
export function violationLine(frame: number, v: Violation): string {
  return JSON.stringify({ type: VIOLATION_TYPE, frame, a: v.a, b: v.b, reason: v.reason })
}

export const LayoutGuard: React.FC = () => {
  const frame = useCurrentFrame()
  const { registry, fontsReady } = useLayoutState()
  useLayoutEffect(() => {
    // Before the brand fonts are in, nothing is measured (LayoutBox.tsx) and there is nothing to report.
    if (!fontsReady) return
    for (const v of findViolations([...registry.boxes.values()], [...registry.overflow])) console.error(violationLine(frame, v))
  }, [frame, registry, fontsReady])
  if (!registry.enabled) throw new Error('LayoutGuard needs a lint-mode Registry (new Registry(true)): this one measures nothing')
  return null
}
