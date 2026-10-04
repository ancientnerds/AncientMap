/**
 * Graphics-only demo timeline (demo-timeline.json): the default props of both
 * compositions, so `npm run studio` (public dir = ancient-nerds-map/public,
 * fonts only) shows every block that needs no media. The timeline and block
 * tests use it as fixture. Evidence and claims mirror the Baalbek pilot's shapes.
 */
import { parseTimeline } from '../timeline'
import demo from './demo-timeline.json'

export const DEMO_TIMELINE = parseTimeline(demo)
