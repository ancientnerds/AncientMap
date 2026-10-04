/**
 * timeline.json: the frame-exact episode compiled by pipeline/studio/timeline.py
 * (spec 2026-09-26 section 4.7, plan C contract C8). parseTimeline() trusts
 * nothing: it checks every field and key, validates each scene's props against
 * the block's schema (blocks/schemas.ts = registry.json) and throws with the
 * JSON path of the first defect. The block semantics and cue targets are
 * checked afterwards by blocks/index.ts checkBlocks(). calculateMetadata and the
 * node scripts both run the two, so a bad timeline fails before a frame renders.
 *
 * Frame convention: every frame number in the file is ABSOLUTE (a frame of the
 * whole episode): scenes[].from, cues[].frame, captions, ticker, chapters,
 * thumbnails and narration clips. SceneView hands blocks scene-relative cue frames.
 */
import { REGISTRY_BLOCKS } from './blocks/schemas'
import { FRAME } from './layout/zones'
import { validate } from './schema'
import { CLAIM_STATUSES, type ClaimStatus } from './theme/colors'

/** The NERV motion is timed in frames at 60 fps; pipeline/studio/script.py fixes fps at 60. */
export const FPS = 60

export const CUE_VERBS = ['show', 'hide', 'highlight', 'stamp', 'introduce', 'status', 'meter'] as const
export type CueVerb = (typeof CUE_VERBS)[number]
/** Verbs a block interprets inside its own scene; the others change episode-wide state (state.ts). */
export const LOCAL_VERBS = ['show', 'hide', 'highlight', 'stamp'] as const
export type LocalVerb = (typeof LOCAL_VERBS)[number]

export type MeterValue = [number, number]
export type Cue = { frame: number; do: CueVerb; target: string; value?: ClaimStatus | MeterValue }
export type Scene = {
  id: string
  from: number
  durationInFrames: number
  block: string
  props: Record<string, unknown>
  cues: Cue[]
}
export type NarrationClip = { src: string; from: number }
export type Duck = { underNarrationDb: number; attackFrames: number; releaseFrames: number }
export type Music = { src: string; gainDb: number; duck: Duck }
export type Caption = { text: string; from: number; to: number }
export type TickerStep = { frame: number; n: number }
export type Chapter = { title: string; frame: number }
export type Credit = { sceneId: string; text: string }
/** A thumbnail candidate (owner decisions 24-25): an episode frame and its 2-4 word teaser. */
export type ThumbnailCandidate = { frame: number; text: string }
export type Timeline = {
  version: 1
  fps: number
  width: number
  height: number
  durationInFrames: number
  audio: { narration: NarrationClip[]; music: Music | null }
  scenes: Scene[]
  captions: Caption[]
  ticker: { evidence: TickerStep[] }
  chapters: Chapter[]
  credits: Credit[]
  thumbnails: ThumbnailCandidate[]
}

/** YouTube's thumbnail A/B test takes three candidates (owner decision 24). */
export const THUMBNAIL_CANDIDATES = 3

class TimelineError extends Error {
  constructor(path: string, message: string) {
    super(`timeline.json ${path}: ${message}`)
    this.name = 'TimelineError'
  }
}

function plain(v: unknown, path: string): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) throw new TimelineError(path, 'expected an object')
  return v as Record<string, unknown>
}
function obj(v: unknown, path: string, required: readonly string[], optional: readonly string[] = []): Record<string, unknown> {
  const o = plain(v, path)
  const missing = required.filter((k) => !(k in o))
  if (missing.length) throw new TimelineError(path, `missing ${missing.join(', ')}`)
  const unknown = Object.keys(o).filter((k) => !required.includes(k) && !optional.includes(k))
  if (unknown.length) throw new TimelineError(path, `unknown key(s) ${unknown.join(', ')}`)
  return o
}
function arr(v: unknown, path: string): unknown[] {
  if (!Array.isArray(v)) throw new TimelineError(path, 'expected an array')
  return v
}
function str(v: unknown, path: string): string {
  if (typeof v !== 'string' || v.length === 0) throw new TimelineError(path, 'expected a non-empty string')
  return v
}
function int(v: unknown, path: string, min = 0): number {
  if (typeof v !== 'number' || !Number.isInteger(v) || v < min) throw new TimelineError(path, `expected an integer >= ${min}`)
  return v
}
function num(v: unknown, path: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new TimelineError(path, 'expected a number')
  return v
}

const ASSET_DIRS = ['voice', 'captures', 'media', 'music'] as const

/** Why `src` is not a clean public-dir path under voice/, captures/, media/ or music/ (null when it is). */
export function assetProblem(src: string): string | null {
  const parts = src.split('/')
  if (!(ASSET_DIRS as readonly string[]).includes(parts[0]) || parts.length < 2) return `"${src}" must lie under ${ASSET_DIRS.map((d) => `${d}/`).join(', ')}`
  if (src.includes('\\') || src.includes(':') || parts.some((p) => p === '' || p === '.' || p === '..')) return `"${src}" is not a clean relative path`
  return null
}

/** Every string under a "src" key anywhere in `value` (props, audio). */
export function collectSrcs(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(collectSrcs)
  if (typeof value === 'object' && value !== null) {
    const o = value as Record<string, unknown>
    const own = typeof o.src === 'string' ? [o.src] : []
    return [...own, ...Object.entries(o).filter(([k]) => k !== 'src').flatMap(([, v]) => collectSrcs(v))]
  }
  return []
}

function parseCue(raw: unknown, path: string, from: number, end: number): Cue {
  const c = obj(raw, path, ['frame', 'do', 'target'], ['value'])
  const frame = int(c.frame, `${path}.frame`)
  if (frame < from || frame >= end) throw new TimelineError(path, `frame ${frame} outside the scene [${from}, ${end})`)
  const verb = str(c.do, `${path}.do`)
  if (!(CUE_VERBS as readonly string[]).includes(verb)) throw new TimelineError(`${path}.do`, `"${verb}" is not one of ${CUE_VERBS.join(', ')}`)
  const target = str(c.target, `${path}.target`)
  const cue: Cue = { frame, do: verb as CueVerb, target }
  if (verb === 'status') {
    if (!(CLAIM_STATUSES as readonly unknown[]).includes(c.value)) throw new TimelineError(`${path}.value`, `a status cue needs one of ${CLAIM_STATUSES.join(', ')}`)
    cue.value = c.value as ClaimStatus
  } else if (verb === 'meter') {
    const v = c.value
    if (target !== 'meter' || !Array.isArray(v) || v.length !== 2 || !v.every((x) => Number.isInteger(x) && x >= 0) || v[0] + v[1] !== 100) {
      throw new TimelineError(path, 'a meter cue targets "meter" with value [a, b], two integers summing to 100')
    }
    cue.value = [v[0], v[1]]
  } else if ('value' in c) {
    throw new TimelineError(`${path}.value`, `a ${verb} cue takes no value`)
  }
  return cue
}

function parseScene(raw: unknown, path: string): Scene {
  const s = obj(raw, path, ['id', 'from', 'durationInFrames', 'block', 'props', 'cues'])
  const id = str(s.id, `${path}.id`)
  const from = int(s.from, `${path}.from`)
  const durationInFrames = int(s.durationInFrames, `${path}.durationInFrames`, 1)
  const block = str(s.block, `${path}.block`)
  const entry = REGISTRY_BLOCKS[block]
  if (!entry) throw new TimelineError(`${path}.block`, `unknown block "${block}"`)
  const props = plain(s.props, `${path}.props`)
  const errors = validate(entry.props, props, `${path}.props`)
  if (errors.length) throw new TimelineError(path, `props invalid:\n  ${errors.join('\n  ')}`)
  const cues = arr(s.cues, `${path}.cues`).map((c, i) => parseCue(c, `${path}.cues[${i}]`, from, from + durationInFrames))
  return { id, from, durationInFrames, block, props, cues }
}

export function parseTimeline(raw: unknown): Timeline {
  const t = obj(raw, '$', ['version', 'fps', 'width', 'height', 'durationInFrames', 'audio', 'scenes', 'captions', 'ticker', 'chapters', 'credits', 'thumbnails'])
  if (t.version !== 1) throw new TimelineError('$.version', 'expected 1')
  if (t.fps !== FPS) throw new TimelineError('$.fps', `expected ${FPS} (the NERV motion is timed in frames at ${FPS} fps)`)
  const width = int(t.width, '$.width', 2)
  const height = int(t.height, '$.height', 2)
  if (width % 2 || height % 2) throw new TimelineError('$', `dimensions must be even, got ${width}x${height}`)
  // Contract C8 fixes the frame like the fps: every zone and layout constant is in 1080p pixels (layout/zones.ts).
  if (width !== FRAME.w || height !== FRAME.h) throw new TimelineError('$', `expected ${FRAME.w}x${FRAME.h}, got ${width}x${height}`)
  const durationInFrames = int(t.durationInFrames, '$.durationInFrames', 1)
  const inside = (frame: number, path: string) => {
    if (frame >= durationInFrames) throw new TimelineError(path, `frame ${frame} is past the end (${durationInFrames})`)
    return frame
  }

  const audio = obj(t.audio, '$.audio', ['narration', 'music'])
  const narration = arr(audio.narration, '$.audio.narration').map((n, i) => {
    const p = `$.audio.narration[${i}]`
    const clip = obj(n, p, ['src', 'from'])
    return { src: str(clip.src, `${p}.src`), from: inside(int(clip.from, `${p}.from`), `${p}.from`) }
  })
  let music: Music | null = null
  if (audio.music !== null) {
    const m = obj(audio.music, '$.audio.music', ['src', 'gainDb', 'duck'])
    const duck = obj(m.duck, '$.audio.music.duck', ['underNarrationDb', 'attackFrames', 'releaseFrames'])
    const gainDb = num(m.gainDb, '$.audio.music.gainDb')
    if (gainDb > 0) throw new TimelineError('$.audio.music.gainDb', 'must be <= 0')
    const underNarrationDb = num(duck.underNarrationDb, '$.audio.music.duck.underNarrationDb')
    if (underNarrationDb > 0) throw new TimelineError('$.audio.music.duck.underNarrationDb', 'must be <= 0')
    music = {
      src: str(m.src, '$.audio.music.src'),
      gainDb,
      duck: {
        underNarrationDb,
        attackFrames: int(duck.attackFrames, '$.audio.music.duck.attackFrames'),
        releaseFrames: int(duck.releaseFrames, '$.audio.music.duck.releaseFrames'),
      },
    }
  }

  const scenes = arr(t.scenes, '$.scenes').map((s, i) => parseScene(s, `$.scenes[${i}]`))
  if (scenes.length === 0) throw new TimelineError('$.scenes', 'no scenes')
  const ids = new Set<string>()
  let cursor = 0
  scenes.forEach((s, i) => {
    if (ids.has(s.id)) throw new TimelineError(`$.scenes[${i}].id`, `duplicate id "${s.id}"`)
    ids.add(s.id)
    if (s.from !== cursor) throw new TimelineError(`$.scenes[${i}].from`, `expected ${cursor}: scenes follow each other without gaps or overlaps`)
    cursor = s.from + s.durationInFrames
  })
  if (cursor !== durationInFrames) throw new TimelineError('$.scenes', `the scenes end at ${cursor}, the episode at ${durationInFrames}`)

  const captions = arr(t.captions, '$.captions').map((c, i) => {
    const p = `$.captions[${i}]`
    const cap = obj(c, p, ['text', 'from', 'to'])
    const from = inside(int(cap.from, `${p}.from`), `${p}.from`)
    const to = int(cap.to, `${p}.to`)
    if (to <= from || to > durationInFrames) throw new TimelineError(p, `bad span [${from}, ${to})`)
    return { text: str(cap.text, `${p}.text`), from, to }
  })
  captions.forEach((c, i) => {
    if (i > 0 && c.from < captions[i - 1].to) throw new TimelineError(`$.captions[${i}]`, 'overlaps the previous caption')
  })

  const tickerRaw = obj(t.ticker, '$.ticker', ['evidence'])
  const evidence = arr(tickerRaw.evidence, '$.ticker.evidence').map((e, i) => {
    const p = `$.ticker.evidence[${i}]`
    const step = obj(e, p, ['frame', 'n'])
    return { frame: inside(int(step.frame, `${p}.frame`), `${p}.frame`), n: int(step.n, `${p}.n`) }
  })
  evidence.forEach((e, i) => {
    if (i > 0 && (e.frame < evidence[i - 1].frame || e.n < evidence[i - 1].n)) {
      throw new TimelineError(`$.ticker.evidence[${i}]`, 'frames and counts must not decrease')
    }
  })

  const chapters = arr(t.chapters, '$.chapters').map((c, i) => {
    const p = `$.chapters[${i}]`
    const ch = obj(c, p, ['title', 'frame'])
    return { title: str(ch.title, `${p}.title`), frame: inside(int(ch.frame, `${p}.frame`), `${p}.frame`) }
  })
  if (chapters.length && chapters[0].frame !== 0) throw new TimelineError('$.chapters[0].frame', 'the first chapter must start at frame 0')
  chapters.forEach((c, i) => {
    if (i > 0 && c.frame <= chapters[i - 1].frame) throw new TimelineError(`$.chapters[${i}].frame`, 'chapters must be in increasing order')
  })

  const credits = arr(t.credits, '$.credits').map((c, i) => {
    const p = `$.credits[${i}]`
    const cr = obj(c, p, ['sceneId', 'text'])
    const sceneId = str(cr.sceneId, `${p}.sceneId`)
    if (!ids.has(sceneId)) throw new TimelineError(`${p}.sceneId`, `no scene "${sceneId}"`)
    return { sceneId, text: str(cr.text, `${p}.text`) }
  })

  const thumbnails = arr(t.thumbnails, '$.thumbnails').map((c, i) => {
    const p = `$.thumbnails[${i}]`
    const th = obj(c, p, ['frame', 'text'])
    const text = str(th.text, `${p}.text`)
    const words = text.trim().split(/\s+/).length
    if (words < 2 || words > 4) throw new TimelineError(`${p}.text`, `"${text}" has ${words} word(s); a thumbnail teaser has 2-4`)
    return { frame: inside(int(th.frame, `${p}.frame`), `${p}.frame`), text }
  })
  if (thumbnails.length !== THUMBNAIL_CANDIDATES) throw new TimelineError('$.thumbnails', `expected exactly ${THUMBNAIL_CANDIDATES} thumbnail candidates, got ${thumbnails.length}`)

  const timeline: Timeline = { version: 1, fps: FPS, width, height, durationInFrames, audio: { narration, music }, scenes, captions, ticker: { evidence }, chapters, credits, thumbnails }
  for (const src of collectSrcs([timeline.audio, timeline.scenes])) {
    const problem = assetProblem(src)
    if (problem) throw new TimelineError('src', problem)
  }
  return timeline
}

/** True when a hook caption is on screen during part of `scene` (its block then keeps above the captions). */
export function sceneHasCaptions(timeline: Pick<Timeline, 'captions'>, scene: Pick<Scene, 'from' | 'durationInFrames'>): boolean {
  const end = scene.from + scene.durationInFrames
  return timeline.captions.some((c) => c.from < end && c.to > scene.from)
}
