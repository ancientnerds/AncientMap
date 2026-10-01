/**
 * The scene block library. Every key here has an entry in schemas.ts
 * REGISTRY_BLOCKS (test/registry.test.ts keeps them equal). A block brings its
 * component, the semantic checks a schema cannot express, the local cue verbs
 * it interprets with their valid targets, and the images calculateMetadata must
 * measure for it. checkBlocks() runs the checks and the cue rules of a parsed
 * timeline: local verbs (show, hide, highlight, stamp) must name a target the
 * block shows; introduce needs a ClaimBoard listing the claim; a meter cue needs
 * a Meter in the episode; status cues may target any claim (EvidenceCard and
 * ClaimBoard show them). The cue table below is the single definition of the
 * local cue rules: plan C's script check mirrors it before voice and capture.
 * A ShareCard, the end card and the one place the link appears in the picture,
 * may only be the last scene (owner rule). Every string the video draws must be
 * drawable by the brand fonts, in upper case too (theme/glyphs.ts; owner
 * decision 32: only drawn strings are checked): the block's `drawn` prop paths
 * (schemas.ts), the drawn strings of its capture props (captureStrings), the
 * captions, credits, chapter titles and the thumbnail teasers. A scene that a
 * hook caption is on screen in must keep the registry's hook limits (the stage
 * under the captions is 140 px shorter; schemas.ts).
 */
import type React from 'react'

import { validate } from '../schema'
import { glyphReason, unsupportedChar } from '../theme/glyphs'
import { type LocalVerb, type Timeline, sceneHasCaptions } from '../timeline'
import { BarChart, type BarChartProps, checkBarChart } from './BarChart'
import { ClaimBoard, type ClaimBoardProps } from './ClaimBoard'
import { Diagram, type DiagramProps, checkDiagram } from './Diagram'
import { EvidenceCard, type EvidenceCardProps } from './EvidenceCard'
import { GlobeShot, type GlobeShotProps, checkGlobeShot, globePins } from './GlobeShot'
import { ListCard, type ListCardProps } from './ListCard'
import { MapboxFlyover, checkMapboxFlyover } from './MapboxFlyover'
import { MapboxTopdown, type MapboxTopdownProps, checkMapboxTopdown, pinsOf } from './MapboxTopdown'
import { Meter, checkMeter } from './Meter'
import { PhotoPlate, type PhotoPlateProps, checkPhotoPlate } from './PhotoPlate'
import { PlatformClip, checkPlatformClip } from './PlatformClip'
import { QuoteCard, type QuoteCardProps, checkQuoteCard } from './QuoteCard'
import { ScaleDrawing, type ScaleDrawingProps, checkScaleDrawing } from './ScaleDrawing'
import { ShareCard } from './ShareCard'
import { ScaleZoom, type ScaleZoomProps, checkScaleZoom } from './ScaleZoom'
import { CAPTURE_PROPS, REGISTRY_BLOCKS } from './schemas'
import { SourceViewer, type SourceViewerProps, checkSourceViewer } from './SourceViewer'
import { Timeline as TimelineBlock, type TimelineProps, checkTimeline } from './Timeline'
import type { BlockProps, Capture, CheckContext } from './types'
import { UnitGrid, type UnitGridProps, checkUnitGrid } from './UnitGrid'

type Targets<P> = (props: P) => string[]

export type BlockDef = {
  component: React.FC<BlockProps<unknown>>
  check: (props: unknown, ctx: CheckContext) => string[]
  cues: Partial<Record<LocalVerb, Targets<unknown>>>
  images: (props: unknown) => string[]
}

/** Erase the props type: parseTimeline() has validated the props against the block's schema. */
function block<P>(
  component: React.FC<BlockProps<P>>,
  opts: { check?: (props: P, ctx: CheckContext) => string[]; cues?: Partial<Record<LocalVerb, Targets<P>>>; images?: (props: P) => string[] } = {},
): BlockDef {
  return {
    component: component as unknown as React.FC<BlockProps<unknown>>,
    check: (props, ctx) => (opts.check ? opts.check(props as P, ctx) : []),
    cues: (opts.cues ?? {}) as Partial<Record<LocalVerb, Targets<unknown>>>,
    images: (props) => (opts.images ? opts.images(props as P) : []),
  }
}

const ids = (items: readonly { id: string }[]) => items.map((i) => i.id)
const markers = (p: PhotoPlateProps) => ids(p.image.markers)
const pins = (p: MapboxTopdownProps) => pinsOf(p.map).map((pin) => pin.id)
const evidence = (p: { evidence: { id: string } }) => [p.evidence.id]

export const BLOCKS: Record<string, BlockDef> = {
  PhotoPlate: block(PhotoPlate, { check: checkPhotoPlate, cues: { show: markers, hide: markers, highlight: markers }, images: (p) => [p.image.src] }),
  MapboxTopdown: block(MapboxTopdown, { check: checkMapboxTopdown, cues: { show: pins, highlight: pins } }),
  PlatformClip: block(PlatformClip, { check: checkPlatformClip }),
  GlobeShot: block(GlobeShot, { check: checkGlobeShot, cues: { show: (p: GlobeShotProps) => globePins(p.clip).map((pin) => pin.id) } }),
  MapboxFlyover: block(MapboxFlyover, { check: checkMapboxFlyover }),
  SourceViewer: block(SourceViewer, { check: checkSourceViewer, cues: { highlight: (p: SourceViewerProps) => evidence(p) } }),
  EvidenceCard: block(EvidenceCard, { cues: { highlight: (p: EvidenceCardProps) => evidence(p), stamp: (p: EvidenceCardProps) => evidence(p) } }),
  QuoteCard: block(QuoteCard, { check: checkQuoteCard, cues: { highlight: (p: QuoteCardProps) => evidence(p) } }),
  ClaimBoard: block(ClaimBoard, { cues: { highlight: (p: ClaimBoardProps) => ids(p.claims) } }),
  Meter: block(Meter, { check: checkMeter }),
  ScaleDrawing: block(ScaleDrawing, { check: checkScaleDrawing, cues: { show: (p: ScaleDrawingProps) => ids(p.objects) } }),
  UnitGrid: block(UnitGrid, { check: checkUnitGrid, cues: { show: (p: UnitGridProps) => ids(p.groups) } }),
  BarChart: block(BarChart, { check: checkBarChart, cues: { show: (p: BarChartProps) => ids(p.bars) } }),
  Timeline: block(TimelineBlock, { check: checkTimeline, cues: { show: (p: TimelineProps) => ids(p.events) } }),
  Diagram: block(Diagram, { check: checkDiagram, cues: { show: (p: DiagramProps) => ids(p.elements) } }),
  ListCard: block(ListCard, { cues: { show: (p: ListCardProps) => ids(p.items) } }),
  ShareCard: block(ShareCard),
  ScaleZoom: block(ScaleZoom, { check: checkScaleZoom, cues: { show: (p: ScaleZoomProps) => [p.small.id, p.large.id] } }),
}

export function blockDef(name: string): BlockDef {
  const def = BLOCKS[name]
  if (!def) throw new Error(`block ${name} has no component`)
  return def
}

/**
 * The strings a `drawn` pattern reaches in `value`, with their paths below `at`
 * ("props.claims[0].label"). Keys are separated by '.', a key suffixed with
 * '[]' walks every element of that array; an absent optional prop yields nothing.
 */
export function drawnStrings(value: unknown, patterns: readonly string[], at: string): [string, string][] {
  const walk = (v: unknown, parts: readonly string[], path: string): [string, string][] => {
    if (parts.length === 0) return typeof v === 'string' ? [[path, v]] : []
    if (typeof v !== 'object' || v === null || Array.isArray(v)) return []
    const [part, ...rest] = parts
    const key = part.endsWith('[]') ? part.slice(0, -2) : part
    const next = (v as Record<string, unknown>)[key]
    if (!part.endsWith('[]')) return walk(next, rest, `${path}.${key}`)
    return Array.isArray(next) ? next.flatMap((item, i) => walk(item, rest, `${path}.${key}[${i}]`)) : []
  }
  return patterns.flatMap((pattern) => walk(value, pattern.split('.'), at))
}

/**
 * The strings a capture puts on screen: its credits and the label of a globe
 * `place` or top-down `pin` event. Event names, targets, URLs (SourceViewer and
 * the cards draw only the ASCII hostname), a source `page` event's title (the
 * page's own <title>, kept as a record; owner decision 32) and the `gpu` event's
 * renderer are never drawn.
 */
export function captureStrings(capture: Pick<Capture, 'events' | 'credits'>, at: string): [string, string][] {
  const out: [string, string][] = capture.credits.map((c, i): [string, string] => [`${at}.credits[${i}]`, c])
  capture.events.forEach((e, i) => {
    if ((e.name === 'place' || e.name === 'pin') && e.label !== undefined) out.push([`${at}.events[${i}].label`, e.label])
  })
  return out
}

/** Every drawn string of a scene's props: the block's `drawn` paths and its capture props' drawn strings. */
function sceneStrings(block: string, props: Record<string, unknown>): [string, string][] {
  const captures = CAPTURE_PROPS.filter((k) => k in props).flatMap((k) => captureStrings(props[k] as Capture, `props.${k}`))
  return [...drawnStrings(props, REGISTRY_BLOCKS[block].drawn, 'props'), ...captures]
}

/** The error for a character of `text` the brand fonts cannot draw, as written or in upper case, or null. */
function glyphProblem(where: string, at: string, text: string): string | null {
  const ch = unsupportedChar(text)
  return ch === null ? null : `${where}: ${at}: ${glyphReason(ch)}`
}

/** Throws with every semantic defect, every bad cue and every undrawable character of the timeline. */
export function checkBlocks(timeline: Timeline): void {
  const errors: string[] = []
  const boardClaims = new Set(
    timeline.scenes.filter((s) => s.block === 'ClaimBoard').flatMap((s) => ids((s.props as unknown as ClaimBoardProps).claims)),
  )
  const hasMeter = timeline.scenes.some((s) => s.block === 'Meter')
  const texts: [string, string][] = [
    ...timeline.captions.map((c, i): [string, string] => [`captions[${i}].text`, c.text]),
    ...timeline.credits.map((c, i): [string, string] => [`credits[${i}].text (scene ${c.sceneId})`, c.text]),
    ...timeline.chapters.map((c, i): [string, string] => [`chapters[${i}].title`, c.title]),
    ...timeline.thumbnails.map((c, i): [string, string] => [`thumbnails[${i}].text`, c.text]),
  ]
  for (const [at, text] of texts) {
    const problem = glyphProblem('timeline', at, text)
    if (problem) errors.push(problem)
  }
  const last = timeline.scenes[timeline.scenes.length - 1]
  for (const scene of timeline.scenes) {
    const def = blockDef(scene.block)
    const where = `scene ${scene.id} (${scene.block})`
    // owner rule: the link appears only on the end card (and in the description)
    if (scene.block === 'ShareCard' && scene !== last) errors.push(`${where}: ShareCard is the end card; only the last scene may use it`)
    for (const e of def.check(scene.props, { fps: timeline.fps, durationInFrames: scene.durationInFrames })) errors.push(`${where}: ${e}`)
    // a scene a hook caption is on screen in has a stage 140 px shorter: the registry's hook limits bind
    if (sceneHasCaptions(timeline, scene)) {
      for (const e of validate(REGISTRY_BLOCKS[scene.block].props, scene.props, 'props', true)) errors.push(`${where}: ${e}`)
    }
    for (const [at, text] of sceneStrings(scene.block, scene.props)) {
      const problem = glyphProblem(where, at, text)
      if (problem) errors.push(problem)
    }
    for (const cue of scene.cues) {
      if (cue.do === 'introduce') {
        if (!boardClaims.has(cue.target)) errors.push(`${where}: introduce ${cue.target}: no ClaimBoard of the episode lists this claim`)
      } else if (cue.do === 'meter') {
        if (!hasMeter) errors.push(`${where}: a meter cue needs a Meter scene in the episode`)
      } else if (cue.do !== 'status') {
        const targets = def.cues[cue.do]
        if (!targets) errors.push(`${where}: the block does not take ${cue.do} cues`)
        else if (!targets(scene.props).includes(cue.target)) errors.push(`${where}: ${cue.do} ${cue.target}: not a target of this block (${targets(scene.props).join(', ') || 'none'})`)
      }
    }
  }
  if (errors.length) throw new Error(`timeline.json block checks failed:\n  ${errors.join('\n  ')}`)
}

/** Every image calculateMetadata measures before the first frame. */
export function imagesToMeasure(timeline: Timeline): string[] {
  return timeline.scenes.flatMap((s) => blockDef(s.block).images(s.props))
}
