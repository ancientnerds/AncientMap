/**
 * Props schemas of every scene block: the source of blocks/registry.json
 * (plan C contract C5, written by `npm run registry`; test/registry.test.ts
 * fails when the committed file differs). Props arrive resolved (contract C6):
 * a script's {"$ref": id} is the case-file entity, {"$capture": id} the capture
 * manifest with `path` renamed to `src`. Every src is relative to the
 * per-render public dir (media/, captures/, voice/, music/, fonts/).
 *
 * Only the keywords of src/schema.ts SUPPORTED appear here; the semantic rules a
 * schema cannot express (a box inside its image, meter values summing to 100,
 * the clip long enough for its scene) live in the blocks' check() functions.
 *
 * `drawn` lists the prop paths whose strings the block's component draws
 * (owner decision 32: the glyph rule covers only drawn text). Keys are
 * separated by '.', a key suffixed with '[]' means every element of that
 * array. Ids, src paths and URLs are not drawn (the cards draw only a URL's
 * ASCII hostname; ShareCard's url is its own drawn prop), nor is
 * SourceViewer's evidence quote: the original sits in the captured page
 * image. A capture prop (CAPTURE_PROPS) is never listed: blocks/index.ts
 * captureStrings() names the drawn strings of every capture. Plan C's
 * pipeline/studio reads `drawn` from registry.json and keeps no copy of it.
 */
import { CLAIM_STATUSES, TONES } from '../theme/colors'
import type { Schema } from '../schema'
import { ICONS } from './icons'

export type RegistryEntry = { map: boolean; platform: boolean; drawn: string[]; props: Schema }

/** The props that hold a resolved capture (C6: a script's {"$capture": id}). */
export const CAPTURE_PROPS = ['clip', 'map', 'page'] as const

const str = (minLength = 1, maxLength?: number): Schema =>
  maxLength === undefined ? { type: 'string', minLength } : { type: 'string', minLength, maxLength }
const num = (minimum?: number, maximum?: number): Schema => ({
  type: 'number',
  ...(minimum === undefined ? {} : { minimum }),
  ...(maximum === undefined ? {} : { maximum }),
})
const int = (minimum?: number, maximum?: number): Schema => ({ ...num(minimum, maximum), type: 'integer' })
const oneOf = (values: readonly string[]): Schema => ({ type: 'string', enum: values })
const arr = (items: Schema, minItems?: number, maxItems?: number): Schema => ({
  type: 'array',
  items,
  ...(minItems === undefined ? {} : { minItems }),
  ...(maxItems === undefined ? {} : { maxItems }),
})
const obj = (properties: Record<string, Schema>, required: string[] = Object.keys(properties), description?: string): Schema => ({
  type: 'object',
  additionalProperties: false,
  required,
  properties,
  ...(description === undefined ? {} : { description }),
})

const ID = str(1, 64)
const ASSET = str(1, 240)
const TONE = oneOf(TONES)
const TITLE = str(1, 48)
const BASIS: Schema = { ...str(3, 140), description: 'What the comparison is based on, always shown on screen (owner rule)' }

export const LABEL = obj({ title: str(1, 40), subtitle: str(1, 56) }, ['title'], 'Lower third over footage')

/** A case-file marker: box = [x, y, w, h] as fractions of the image, checked on a crop. */
export const MARKER = obj({ id: ID, box: arr(num(0, 1), 4, 4), label: str(1, 24) })

/** Case-file media, resolved (C6). */
export const MEDIA = obj({
  id: ID,
  src: ASSET,
  license: str(1),
  attribution: str(1),
  source_url: str(1),
  depicts: str(1),
  markers: arr(MARKER, 0, 6),
})

/** Case-file evidence, resolved (C6); length limits are per block, where the text must fit. */
export function evidenceSchema(limits: { statement?: number; quote?: number } = {}): Schema {
  return obj({
    id: ID,
    claim_id: ID,
    kind: oneOf(['fact', 'quote', 'quantity', 'date', 'image', 'place']),
    statement: str(1, limits.statement),
    source: obj({
      url: str(1),
      title: str(1),
      tier: int(0),
      license: str(0),
      quote: str(0, limits.quote),
      locator: str(0),
    }),
    paper_anchor: { type: ['string', 'null'] },
  })
}

/** Case-file claim, resolved (C6). */
export const CLAIM = obj({
  id: ID,
  label: str(1, 80),
  by: str(0, 40),
  icon: { ...oneOf(ICONS), description: 'ClaimBoard icon; the case file must use one of these names' },
  status: oneOf(CLAIM_STATUSES),
})

/** One capture manifest event (pipeline/studio/capture/manifest.py event()). */
export const EVENT: Schema = {
  type: 'object',
  additionalProperties: false,
  required: ['t', 'name'],
  properties: {
    t: num(0),
    name: str(1),
    x: num(),
    y: num(),
    box: arr(num(), 4, 4),
    target: str(1),
    label: str(1),
    url: str(1),
    title: str(0),
    lat: num(-90, 90),
    lng: num(-180, 180),
    track: {
      type: 'array',
      items: { type: ['array', 'null'], items: { type: 'number' }, minItems: 2, maxItems: 2 },
      description: 'Globe place events: the pixel [x, y] in every capture frame from the event on, null while hidden',
    },
  },
}

/** A capture, resolved (C6): manifest of pipeline/studio/capture with `path` as `src`. */
export function captureSchema(kind: 'platform' | 'globe' | 'source' | 'mapbox_topdown', still: boolean): Schema {
  return obj({
    id: ID,
    kind: oneOf([kind]),
    src: ASSET,
    fps: still ? { type: 'null' } : num(1),
    duration_s: still ? { type: 'null' } : num(0),
    width: int(2),
    height: int(2),
    events: arr(EVENT),
    credits: arr(str(1)),
  })
}

const CLIP_START: Schema = { ...num(0), description: 'Seconds into the clip where the scene starts (default 0)' }

/** One side of a ScaleZoom: a quantity drawn to the one linear scale of the frame. */
const ZOOM_QUANTITY = obj({ id: ID, label: str(1, 32), value: { ...num(0), description: 'Greater than 0, in the chart unit' } })

/** The drawn strings of a block whose only drawn prop is its lower third. */
const LABEL_DRAWN = ['label.title', 'label.subtitle']

export const REGISTRY_BLOCKS: Record<string, RegistryEntry> = {
  PhotoPlate: {
    map: false,
    platform: false,
    drawn: [...LABEL_DRAWN, 'caption', 'image.markers[].label'],
    props: obj(
      {
        image: MEDIA,
        kenBurns: { ...oneOf(['in', 'out', 'none']), description: 'Camera over the whole scene (default in)' },
        label: LABEL,
        caption: str(1, 90),
      },
      ['image'],
      'A checked photo with its markers in the same moving layer; cues show/hide/highlight <marker id>',
    ),
  },
  MapboxTopdown: {
    map: true,
    platform: false,
    drawn: LABEL_DRAWN,
    props: obj(
      {
        map: captureSchema('mapbox_topdown', true),
        lines: { ...arr(obj({ from: ID, to: ID }), 0, 4), description: 'Distance lines between two pins; the length is computed from their coordinates' },
        label: LABEL,
      },
      ['map'],
      'Exact top-down satellite frame with projected pins (orthographic, so distance lines are allowed); cues show/highlight <place id>',
    ),
  },
  PlatformClip: {
    map: true,
    platform: true,
    drawn: LABEL_DRAWN,
    props: obj(
      {
        clip: captureSchema('platform', false),
        start_s: CLIP_START,
        camera: {
          ...arr(obj({ t: num(0), cx: num(0), cy: num(0), zoom: num(1, 3) }), 1),
          description: 'Virtual camera keys on the capture clock (t in clip seconds, cx/cy in capture pixels)',
        },
        follow: { ...num(1, 2.5), description: 'Zoom the virtual camera onto each event with x/y (instead of camera)' },
        label: LABEL,
      },
      ['clip'],
      'A platform moment: the real ancientnerds.com recorded by the capture step',
    ),
  },
  GlobeShot: {
    map: false,
    platform: false,
    drawn: LABEL_DRAWN,
    props: obj(
      { clip: captureSchema('globe', false), start_s: CLIP_START, label: LABEL },
      ['clip'],
      'Our vector globe (no map credit); labelled places light up at their capture events and follow their per-frame track; cue show <place id>',
    ),
  },
  MapboxFlyover: {
    map: true,
    platform: false,
    drawn: LABEL_DRAWN,
    props: obj({ clip: captureSchema('globe', false), start_s: CLIP_START, label: LABEL }, ['clip'], 'A Mapbox fly-in or orbit take'),
  },
  SourceViewer: {
    map: false,
    platform: false,
    drawn: [],
    props: obj(
      { page: captureSchema('source', true), evidence: evidenceSchema({ statement: 160 }) },
      ['page', 'evidence'],
      'A captured source page with the quote highlighted; cue highlight <evidence id>',
    ),
  },
  EvidenceCard: {
    map: false,
    platform: false,
    drawn: ['evidence.kind', 'evidence.statement', 'evidence.source.quote', 'evidence.source.title', 'evidence.source.locator'],
    props: obj(
      { evidence: evidenceSchema({ statement: 160, quote: 260 }), image: MEDIA },
      ['evidence'],
      'One verified evidence item; cues highlight <evidence id> (quote types on), stamp <evidence id>',
    ),
  },
  QuoteCard: {
    map: false,
    platform: false,
    drawn: ['evidence.source.quote', 'evidence.source.title', 'evidence.source.locator', 'attribution'],
    props: obj(
      { evidence: evidenceSchema({ statement: 160, quote: 320 }), attribution: str(1, 60) },
      ['evidence'],
      'A verbatim passage (texts and traditions, or a page that cannot be captured); cue highlight <evidence id>',
    ),
  },
  ClaimBoard: {
    map: false,
    platform: false,
    drawn: ['title', 'claims[].label', 'claims[].by'],
    props: obj(
      { claims: arr(CLAIM, 1, 6), title: TITLE },
      ['claims'],
      'The claims under test; introduce/status cues (any scene) drive it; cue highlight <claim id>',
    ),
  },
  Meter: {
    map: false,
    platform: false,
    drawn: ['title', 'hypotheses[]', 'note'],
    props: obj(
      {
        hypotheses: arr(str(1, 40), 2, 2),
        start: { ...arr(int(0, 100), 2, 2), description: 'Split before the first meter cue; sums to 100' },
        title: TITLE,
        note: str(1, 110),
      },
      ['hypotheses', 'start'],
      'The probability meter; meter cues (any scene) move it',
    ),
  },
  ScaleDrawing: {
    map: false,
    platform: false,
    drawn: ['title', 'basis', 'objects[].label'],
    props: obj(
      {
        title: TITLE,
        unit: oneOf(['cm', 'm', 'km']),
        basis: BASIS,
        objects: arr(
          obj({
            id: ID,
            label: str(1, 24),
            shape: oneOf(['block', 'person', 'column', 'bus', 'pyramid', 'rect']),
            width: num(0),
            height: num(0),
            x: num(0),
          }),
          2,
          5,
        ),
      },
      ['title', 'unit', 'basis', 'objects'],
      'A to-scale side view on one ground line (no measuring on photos); cue show <object id>',
    ),
  },
  UnitGrid: {
    map: false,
    platform: false,
    drawn: ['title', 'unitLabel', 'basis', 'groups[].label'],
    props: obj(
      {
        title: TITLE,
        basis: BASIS,
        unitLabel: str(1, 40),
        columns: int(5, 40),
        groups: arr(obj({ id: ID, count: int(1, 400), label: str(1, 40), tone: TONE }), 1, 4),
      },
      ['title', 'basis', 'unitLabel', 'groups'],
      'Counts as lit unit squares (one block = 80 buses); cue show <group id>',
    ),
  },
  BarChart: {
    map: false,
    platform: false,
    drawn: ['title', 'unit', 'basis', 'bars[].label'],
    props: obj(
      {
        title: TITLE,
        unit: str(1, 16),
        basis: BASIS,
        bars: arr(
          obj(
            {
              id: ID,
              label: str(1, 32),
              value: {
                type: ['number', 'array'],
                minimum: 0,
                items: num(0),
                minItems: 2,
                maxItems: 2,
                description: 'a number, or [low, high] when sources differ (the bar shows the range)',
              },
              tone: TONE,
            },
            ['id', 'label', 'value'],
          ),
          2,
          8,
        ),
      },
      ['title', 'unit', 'basis', 'bars'],
      'Horizontal bars on a linear axis (frequencies, sizes); a [low, high] value is drawn as a range; cue show <bar id>',
    ),
  },
  Timeline: {
    map: false,
    platform: false,
    drawn: ['title', 'basis', 'events[].label'],
    props: obj(
      {
        title: TITLE,
        from: int(),
        to: int(),
        basis: BASIS,
        events: arr(obj({ id: ID, year: int(), label: str(1, 32), tone: TONE }), 1, 10),
      },
      ['title', 'from', 'to', 'events'],
      'A year axis (negative = BCE, no year 0); cue show <event id>',
    ),
  },
  Diagram: {
    map: false,
    platform: false,
    drawn: ['title', 'basis', 'elements[].label', 'elements[].text'],
    props: obj(
      {
        title: TITLE,
        width: num(1),
        height: num(1),
        basis: BASIS,
        elements: arr(
          obj(
            {
              id: ID,
              type: oneOf(['circle', 'line', 'arrow', 'curve', 'orbit', 'label']),
              tone: TONE,
              label: str(1, 32),
              cx: num(),
              cy: num(),
              r: num(0),
              rx: num(0),
              ry: num(0),
              period: num(0.5),
              x1: num(),
              y1: num(),
              x2: num(),
              y2: num(),
              dashed: { type: 'boolean' },
              points: arr(arr(num(), 2, 2), 2),
              x: num(),
              y: num(),
              text: str(1, 40),
            },
            ['id', 'type', 'tone'],
          ),
          1,
          16,
        ),
      },
      ['title', 'width', 'height', 'elements'],
      'NERV wireframe primitives in a width x height user space (type C topics); cue show <element id>',
    ),
  },
  ListCard: {
    map: false,
    platform: false,
    drawn: ['title', 'items[].text', 'note'],
    props: obj(
      { title: TITLE, items: arr(obj({ id: ID, text: str(1, 90) }), 1, 5), note: str(1, 110) },
      ['title', 'items'],
      'A short list, e.g. what would change our mind; cue show <item id>',
    ),
  },
  ShareCard: {
    map: false,
    platform: false,
    drawn: ['headline', 'url', 'lines[]'],
    props: obj(
      { headline: str(1, 60), url: str(1, 60), lines: arr(str(1, 80), 0, 3) },
      ['headline', 'url', 'lines'],
      'The end card: the one place the link appears in the picture',
    ),
  },
  ScaleZoom: {
    map: false,
    platform: false,
    drawn: ['title', 'unit', 'basis', 'small.label', 'large.label'],
    props: obj(
      { title: TITLE, unit: str(1, 16), basis: BASIS, small: ZOOM_QUANTITY, large: ZOOM_QUANTITY },
      ['title', 'unit', 'basis', 'small', 'large'],
      'A linear zoom-out for ratios beyond a UnitGrid (1:400), never a log axis: the small quantity drawn readable, then the camera pulls back linearly until the large one fits, the small one shrinking to a dot; cue show <small id> or show <large id> (the quantity appears)',
    ),
  },
}

/** registry.json as pipeline/studio/blocks.py reads it (contract C5). */
export function buildRegistry(): { blocks: Record<string, RegistryEntry> } {
  return { blocks: REGISTRY_BLOCKS }
}

/** The exact text of registry.json (2-space JSON and a final newline). */
export function registryJson(): string {
  return `${JSON.stringify(buildRegistry(), null, 2)}\n`
}
