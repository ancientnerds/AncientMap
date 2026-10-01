/**
 * The worst-case episode of the layout lint. blocks/schemas.ts says "length
 * limits are per block, where the text must fit": this builds the timeline that
 * proves it. Every scene block of the registry appears on both stages (the full
 * one and the shorter one under hook captions), with every drawn string at its
 * schema maxLength, in the widest layout the block has (the most claims, the most
 * list items, an evidence card with its image). test/capacity.test.ts checks the
 * timeline against the schemas without a browser; test/gpu/capacity.gpu.ts lints
 * it in a real one and requires that nothing overflows.
 *
 * The skeleton of each block is a scene of the committed fixtures (the demo
 * timeline for the graphics blocks, the smoke timeline for the footage blocks):
 * valid props, with the geometry the block needs. Only the drawn strings are
 * replaced. Proportional fonts make the width of a string depend on its letters,
 * so the strings are not ordinary prose but a deliberately wide filler (FILLER:
 * per character 4-5 % wider than an English sample in Orbitron 700, upper case
 * 0.727 em against 0.697 and lower case 0.595 against 0.567, and in Cormorant
 * Garamond, 0.420 against 0.400; the monospace fonts do not care): a limit that
 * fits the filler leaves room for real text.
 *
 * Under hook captions the stage is 140 px shorter (540 px) and some boxes hold less:
 * the registry records that capacity (hookMaxLength, hookMaxItems; src/schema.ts), and
 * `episode check` refuses a hook beat above it. The hook scenes of this episode are
 * drawn at those numbers instead of the schema's, and the lint must still be clean.
 *
 * One kind of layout limit is not a string length and is not proved here: free-standing
 * labels (a scale object, a diagram element, a timeline event, a map pin) take the room
 * the script gives them. The skeletons space them out (COMPLETE); a crowded scene is
 * the layout lint's to refuse at render time.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { crc32, deflateSync } from 'node:zlib'

import { drawnStrings } from '../src/blocks'
import { REGISTRY_BLOCKS } from '../src/blocks/schemas'
import { LOCAL_VERBS } from '../src/timeline'
import { schemaAt, schemaNodes } from './registryHelpers'

/** The hostname of the evidence sources: longer than most (jstor.org, dainst.org), shorter than journals.sagepub.com. */
const HOST = 'researchgate.net'

const FILLER = 'limestone tool evidence mammoth excavation Roman weight quarrying report tonnes'

/** Exactly `n` characters of filler, never ending in a space. */
export function fill(n: number): string {
  const text = FILLER.repeat(Math.ceil(n / FILLER.length) + 1).slice(0, n)
  return text.endsWith(' ') ? `${text.slice(0, -1)}m` : text
}

type Json = Record<string, unknown>
type SceneJson = { id: string; from: number; durationInFrames: number; block: string; props: Json; cues: { frame: number; do: string; target: string }[] }

const read = (rel: string): { scenes: SceneJson[] } => JSON.parse(readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8'))
const FIXTURE_SCENES = [...read('../src/fixtures/demo-timeline.json').scenes, ...read('./fixtures/smoke-timeline.json').scenes]

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T

/** The first fixture scene of `block`; a MapboxFlyover is a GlobeShot's capture under another block. */
function skeletonScene(block: string): SceneJson {
  const own = FIXTURE_SCENES.find((s) => s.block === block)
  if (own) return clone(own)
  if (block === 'MapboxFlyover') {
    const scene = { ...clone(skeletonScene('GlobeShot')), block }
    ;(scene.props.clip as { credits: string[] }).credits = ['© Mapbox']
    return scene
  }
  throw new Error(`no fixture scene of block ${block}`)
}

/** Keys of a path as blocks/index.ts drawnStrings() writes it: "props.claims[0].label". */
function pathKeys(path: string): (string | number)[] {
  return [...path.replace(/^props\./, '').matchAll(/([^.[\]]+)|\[(\d+)\]/g)].map((m) => (m[2] !== undefined ? Number(m[2]) : m[1]))
}

function setAt(root: Json, path: string, value: string): void {
  const keys = pathKeys(path)
  let at = root as unknown as Record<string | number, unknown>
  for (const key of keys.slice(0, -1)) at = at[key] as Record<string | number, unknown>
  at[keys[keys.length - 1]] = value
}

/** Create the optional objects and strings a drawn pattern leads to, up to the first array (its elements must exist). */
function ensurePath(props: Json, pattern: string): void {
  const keys = pattern.split('.')
  let at = props
  for (const [i, part] of keys.entries()) {
    if (part.endsWith('[]')) return
    if (i === keys.length - 1) at[part] ??= 'x'
    else {
      at[part] ??= {}
      at = at[part] as Json
    }
  }
}

/** Resize the array at `key` of `props` to `n` elements, copies of the first with ids made unique. */
function resize(props: Json, key: string, n: number): void {
  const items = props[key] as Json[]
  props[key] = Array.from({ length: n }, (_, i) => (i < items.length ? items[i] : { ...clone(items[0]), id: `${items[0].id}-${i}` }))
}

/** The pattern of a drawn path with its array indexes as `[]`: "props.claims[2].label" -> "claims[].label". */
const patternOf = (path: string): string => path.replace(/^props\./, '').replace(/\[\d+\]/g, '[]')

/** How many items the array at `path` of `block`'s props holds: the schema's maxItems, on the hook stage its hookMaxItems. */
function itemsOf(block: string, path: string, hook: boolean): number {
  const schema = schemaAt(REGISTRY_BLOCKS[block].props, path)
  const n = (hook ? schema?.hookMaxItems : undefined) ?? schema?.maxItems
  if (n === undefined) throw new Error(`${block}: ${path} has no maxItems: its widest layout cannot be built`)
  return n
}

/** Remove the optional string at `path` of `root`. */
function removeAt(root: Json, path: string): void {
  const keys = pathKeys(path)
  let at = root as unknown as Record<string | number, unknown>
  for (const key of keys.slice(0, -1)) at = at[key] as Record<string | number, unknown>
  delete at[keys[keys.length - 1]]
}

/**
 * Every drawn string of `props` set to its schema maxLength of filler (on the hook stage to
 * its hookMaxLength, and a string with a hookMaxLength of 0 removed: it cannot be shown
 * there), an enum string to its longest value. A drawn string with none of these is an
 * error: its text cannot be proved to fit.
 */
export function fillDrawn(block: string, props: Json, hook: boolean): void {
  const entry = REGISTRY_BLOCKS[block]
  for (const pattern of entry.drawn) ensurePath(props, pattern)
  const absent: string[] = []
  for (const [path] of drawnStrings(props, entry.drawn, 'props')) {
    const schema = schemaAt(entry.props, patternOf(path))
    if (!schema) throw new Error(`${block}: no schema for ${path}`)
    const limit = hook ? schema.hookMaxLength : undefined
    if (limit === 0) absent.push(path)
    else if (limit !== undefined) setAt(props, path, fill(limit))
    else if (schema.enum) setAt(props, path, [...schema.enum].map(String).sort((a, b) => b.length - a.length)[0])
    else if (schema.maxLength !== undefined) setAt(props, path, fill(schema.maxLength))
    else throw new Error(`${block}: ${path} is drawn but has no maxLength: its text cannot be proved to fit`)
  }
  for (const path of absent) removeAt(props, path)
}

/** The hostname every evidence source of the capacity episode has. */
function evidenceWithHost(props: Json): void {
  const evidence = props.evidence as { source: { url: string } }
  evidence.source.url = `https://www.${HOST}/publication/1`
}

const MEDIA = (skeletonScene('PhotoPlate').props as { image: Json }).image

/** A layout of a block that differs in capacity; `props` shapes the skeleton, on the hook stage or not. */
type Variant = { name: string; props: (p: Json, hook: boolean) => void }
const plain: Variant[] = [{ name: '', props: () => undefined }]

/** The layouts of a block that differ in capacity: the widest is the one that can overflow. */
const VARIANTS: Record<string, Variant[]> = {
  EvidenceCard: [
    { name: 'no image', props: () => undefined },
    { name: 'with image', props: (p) => (p.image = clone(MEDIA)) },
  ],
  // the most rows: the row height, so the label font and the lines of a label, shrink with every claim
  ClaimBoard: [
    { name: '1 claim', props: () => undefined },
    { name: 'most claims', props: (p, hook) => resize(p, 'claims', itemsOf('ClaimBoard', 'claims', hook)) },
  ],
  ListCard: [
    { name: '1 item', props: () => undefined },
    { name: 'most items', props: (p, hook) => resize(p, 'items', itemsOf('ListCard', 'items', hook)) },
  ],
  BarChart: [
    { name: '3 bars', props: () => undefined },
    { name: 'most bars', props: (p, hook) => resize(p, 'bars', itemsOf('BarChart', 'bars', hook)) },
  ],
  UnitGrid: [
    { name: '1 group', props: () => undefined },
    {
      name: 'most groups',
      props: (p, hook) => {
        resize(p, 'groups', itemsOf('UnitGrid', 'groups', hook))
        for (const g of p.groups as Json[]) g.count = 20
      },
    },
  ],
}

/**
 * What a fixture lacks of a block's drawn strings or leaves too crowded for them:
 * - a Diagram's free `label` element is the only one that draws `text`;
 * - ScaleDrawing labels (24 characters, 426 px) are centred over their objects, which the
 *   fixture puts 2 m apart: the bus moves 4.5 m on, so every label has room;
 * - a BarChart value box holds 14 characters (a range 16): a 6-character unit leaves room for a
 *   4-digit value or a 3-digit range, so the range is [100, 165];
 * - the pins of the MapboxTopdown fixture sit at the bottom of the frame, under the lower third
 *   and under the hook captions: they move up.
 */
const COMPLETE: Record<string, (p: Json) => void> = {
  Diagram: (p) => (p.elements as Json[]).push({ id: 'd4', type: 'label', tone: 'info', x: 5, y: 5, text: 'x' }),
  ScaleDrawing: (p) => ((p.objects as Json[])[2].x = 28),
  BarChart: (p) => ((p.bars as Json[])[1].value = [100, 165]),
  MapboxTopdown: (p) => {
    const pins = ((p.map as Json).events as Json[]).filter((e) => e.name === 'pin')
    ;[
      [1000, 420],
      [1500, 380],
    ].forEach(([x, y], i) => Object.assign(pins[i], { x, y }))
  },
}

/*
 * What the hook stage holds, as the lint measured it on the RTX 3080 (2026-10-01): under hook
 * captions the stage is 540 px high (680 on the full stage), and blocks/schemas.ts records the
 * result as hookMaxLength / hookMaxItems, which this episode draws (VARIANTS, fillDrawn):
 * - ClaimBoard rows are floor(450 / n) px: at 6 rows a claim's `by` line and one label line need
 *   62 px of the 49 the label box has, so five claims are the most;
 * - ListCard rows are floor(242 / n) px with a note: five rows leave a 36 px box for a 40 px
 *   line, so four items are the most;
 * - a BarChart row needs a 53 px pitch for its 37 px line (the content height of JetBrains Mono
 *   at 28 px): 354 px hold six bars, not seven or eight;
 * - a UnitGrid legend entry is 127 px (a 72 px number, one 30 px label line) plus a 32 px gap, and
 *   the legend ends where the basis line starts, 394 px below its top under hook captions: two
 *   groups, where the full stage holds three;
 * - the Meter's stack of labels, numbers, words, bar and note is 514 px, the stage under it 450:
 *   the note runs into the captions, so a Meter under hook captions has none (hookMaxLength 0);
 * - the cards whose text wraps hold less: an EvidenceCard 88 characters of statement and 165 of
 *   quote beside no image and 68 and 134 beside one, a QuoteCard 230 of quote.
 * A block has one number per box, the strictest of its layouts (68 and 134 for an EvidenceCard),
 * so a hook card without an image, a board without `by` lines or a list without a note is held
 * to the capacity of its widest layout: `episode check` cannot see which layout a scene gets.
 */

/** The key of a block's layout variant in the scene ids: "EvidenceCard.noimage". */
export const variantKey = (block: string, variant: string): string => [block, variant.replace(/\W/g, '')].filter(Boolean).join('.')

/** Frames per scene: long enough for the typed quotes and the groups of a UnitGrid, short enough for the clips of the fixtures. */
const DURATION: Record<string, number> = { EvidenceCard: 240, QuoteCard: 240, UnitGrid: 240, BarChart: 240 }

const END_CARD = 'ShareCard'

/** The limit of every drawn string of every block: block -> pattern -> maxLength ("enum" for a string with a fixed set of values). */
export function drawnLimits(): Record<string, Record<string, number | 'enum'>> {
  return Object.fromEntries(
    Object.entries(REGISTRY_BLOCKS).map(([block, entry]) => [
      block,
      Object.fromEntries(
        entry.drawn.map((pattern) => {
          const schema = schemaAt(entry.props, pattern)
          return [pattern, schema?.enum ? 'enum' : (schema?.maxLength as number)]
        }),
      ),
    ]),
  )
}

/**
 * The hook-stage capacity of every box that has one: block -> path -> characters (hookMaxLength)
 * or, as `<path> (items)`, items (hookMaxItems). A path is a drawn pattern's ("evidence.statement")
 * or, for an array, its property ("claims").
 */
export function hookLimits(): Record<string, Record<string, number>> {
  const byBlock = Object.entries(REGISTRY_BLOCKS).map(([block, entry]): [string, Record<string, number>] => {
    const limits: [string, number][] = schemaNodes(entry.props).flatMap(([path, schema]): [string, number][] => [
      ...(schema.hookMaxLength === undefined ? [] : [[path, schema.hookMaxLength] as [string, number]]),
      ...(schema.hookMaxItems === undefined ? [] : [[`${path} (items)`, schema.hookMaxItems] as [string, number]]),
    ])
    return [block, Object.fromEntries(limits)]
  })
  return Object.fromEntries(byBlock.filter(([, limits]) => Object.keys(limits).length > 0))
}

export type CapacityCase = { id: string; block: string; variant: string; hook: boolean }

/** A scene id is "<block>[.<variant>].<full|hook>": the lint's violation ids name it ("PhotoPlate.hook:lt"). */
export type CapacityTimeline = { timeline: Json; cases: CapacityCase[]; assets: string[] }

export function capacityTimeline(): CapacityTimeline {
  const scenes: Json[] = []
  const cases: CapacityCase[] = []
  const captions: { text: string; from: number; to: number }[] = []
  let from = 0
  // the end card is the last scene, and never under hook captions (hook beats come first)
  const blocks = [...Object.keys(REGISTRY_BLOCKS).filter((b) => b !== END_CARD), END_CARD]
  for (const block of blocks) {
    const skeleton = skeletonScene(block)
    for (const variant of VARIANTS[block] ?? plain) {
      const key = variantKey(block, variant.name)
      for (const hook of block === END_CARD ? [false] : [false, true]) {
        const props = clone(skeleton.props)
        COMPLETE[block]?.(props)
        variant.props(props, hook)
        fillDrawn(block, props, hook)
        if ('evidence' in props) evidenceWithHost(props)
        const durationInFrames = DURATION[block] ?? skeleton.durationInFrames
        const id = `${key}.${hook ? 'hook' : 'full'}`
        const cues = skeleton.cues.filter((c) => (LOCAL_VERBS as readonly string[]).includes(c.do)).map((c) => ({ ...c, frame: c.frame - skeleton.from + from }))
        scenes.push({ id, from, durationInFrames, block, props, cues })
        cases.push({ id, block, variant: variant.name, hook })
        if (hook) captions.push({ text: 'HOOK', from: from + 6, to: from + 54 })
        from += durationInFrames
      }
    }
  }
  const timeline = {
    version: 1,
    fps: 60,
    width: 1920,
    height: 1080,
    durationInFrames: from,
    audio: { narration: [], music: null },
    scenes,
    captions,
    ticker: { evidence: [] },
    chapters: [{ title: 'Capacity', frame: 0 }],
    credits: [],
    thumbnails: [
      { frame: 30, text: 'Who moved it?' },
      { frame: 330, text: 'Where is Baalbek?' },
      { frame: 630, text: 'How far apart?' },
    ],
  }
  // every image of the episode is a generated PNG, whatever the fixtures call it
  const json = JSON.stringify(timeline).replace(/\.jpg"/g, '.png"')
  const assets = [...new Set((json.match(/"(?:media|captures)\/[^"]+"/g) ?? []).map((s) => s.slice(1, -1)))]
  return { timeline: JSON.parse(json), cases, assets }
}

/** A solid-colour PNG of w x h pixels (stands in for every image of the capacity episode). */
export function solidPng(w: number, h: number): Buffer {
  const chunk = (type: string, data: Buffer): Buffer => {
    const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
    const out = Buffer.alloc(body.length + 8)
    out.writeUInt32BE(data.length, 0)
    body.copy(out, 4)
    out.writeUInt32BE(crc32(body), body.length + 4)
    return out
  }
  const header = Buffer.alloc(13)
  header.writeUInt32BE(w, 0)
  header.writeUInt32BE(h, 4)
  header.set([8, 2, 0, 0, 0], 8)
  const row = Buffer.alloc(1 + w * 3, 0x30)
  row[0] = 0
  const raw = Buffer.concat(Array.from({ length: h }, () => row))
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
}
