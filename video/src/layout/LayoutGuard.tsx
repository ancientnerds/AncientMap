/**
 * Lint-mode reporter. Rendered as the LAST child of the LayoutProvider, so its
 * layout effect runs after every LayoutBox of the frame has registered (React
 * runs layout effects subtree by subtree in sibling order). Each violation is
 * one console.error line of JSON, which scripts/lint.ts collects through
 * onBrowserLog:
 *   {"type":"layout-violation","frame":123,"a":"captions","b":"b01:lt","reason":"overlap"}
 */
import React, { useLayoutEffect } from 'react'
import { useCurrentFrame } from 'remotion'

import { type Violation, findViolations } from './geometry'
import { useRegistry } from './LayoutBox'

export const VIOLATION_TYPE = 'layout-violation'

/** The console line of one violation at `frame` (scripts/args.ts parseViolation reads it back). */
export function violationLine(frame: number, v: Violation): string {
  return JSON.stringify({ type: VIOLATION_TYPE, frame, a: v.a, b: v.b, reason: v.reason })
}

export const LayoutGuard: React.FC = () => {
  const frame = useCurrentFrame()
  const registry = useRegistry()
  useLayoutEffect(() => {
    for (const v of findViolations([...registry.boxes.values()], [...registry.overflow])) console.error(violationLine(frame, v))
  }, [frame, registry])
  return null
}
