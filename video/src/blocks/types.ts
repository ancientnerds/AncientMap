/**
 * What every scene block receives, and the resolved case-file and capture
 * shapes of its props (plan C contract C6; the schemas are in schemas.ts).
 */
import type { SceneCue } from '../cues'
import type { Rect } from '../layout/geometry'
import type { ClaimStatus } from '../theme/colors'
import type { IconName } from './icons'

export type BlockProps<P> = {
  props: P
  /** The scene's cues with scene-relative frames. */
  cues: readonly SceneCue[]
  durationInFrames: number
  /** Prefix of LayoutBox ids, so lint reports name the scene. */
  sceneId: string
  /** Absolute frame of the scene start: global cue state (state.ts) is keyed by absolute frames. */
  sceneFrom: number
  /** Where the block's graphics go: the stage, shorter in scenes with hook captions. */
  stage: Rect
}

export type Label = { title: string; subtitle?: string }

export type Marker = { id: string; box: [number, number, number, number]; label: string }
export type Media = {
  id: string
  src: string
  license: string
  attribution: string
  source_url: string
  depicts: string
  markers: Marker[]
}

export type EvidenceKind = 'fact' | 'quote' | 'quantity' | 'date' | 'image' | 'place'
export type Evidence = {
  id: string
  claim_id: string
  kind: EvidenceKind
  statement: string
  source: { url: string; title: string; tier: number; license: string; quote: string; locator: string }
  paper_anchor: string | null
}

export type Claim = { id: string; label: string; by: string; icon: IconName; status: ClaimStatus }

export type CaptureEvent = {
  t: number
  name: string
  x?: number
  y?: number
  box?: [number, number, number, number]
  target?: string
  label?: string
  url?: string
  title?: string
  lat?: number
  lng?: number
  /** Globe place events: [x, y] in every capture frame from the event on, null while hidden. */
  track?: ([number, number] | null)[]
}
export type Capture = {
  id: string
  kind: 'platform' | 'globe' | 'source' | 'mapbox_topdown'
  src: string
  fps: number | null
  duration_s: number | null
  width: number
  height: number
  events: CaptureEvent[]
  credits: string[]
}

/** What a block's check() gets besides its props. */
export type CheckContext = { fps: number; durationInFrames: number }
