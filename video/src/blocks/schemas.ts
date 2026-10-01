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

/** `hookMaxLength`: what the box holds under hook captions, where the stage is 140 px shorter (src/schema.ts). */
const str = (minLength = 1, maxLength?: number, hookMaxLength?: number): Schema => ({
  type: 'string',
  minLength,
  ...(maxLength === undefined ? {} : { maxLength }),
  ...(hookMaxLength === undefined ? {} : { hookMaxLength }),
})
const num = (minimum?: number, maximum?: number): Schema => ({
  type: 'number',
  ...(minimum === undefined ? {} : { minimum }),
  ...(maximum === undefined ? {} : { maximum }),
})
const int = (minimum?: number, maximum?: number): Schema => ({ ...num(minimum, maximum), type: 'integer' })
const oneOf = (values: readonly string[]): Schema => ({ type: 'string', enum: values })
/** `hookMaxItems`: how many items the layout holds under hook captions (src/schema.ts). */
const arr = (items: Schema, minItems?: number, maxItems?: number, hookMaxItems?: number): Schema => ({
  type: 'array',
  items,
  ...(minItems === undefined ? {} : { minItems }),
  ...(maxItems === undefined ? {} : { maxItems }),
  ...(hookMaxItems === undefined ? {} : { hookMaxItems }),
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

/*
 * Length limits: the text must fit where the block draws it, because `episode check`
 * accepts exactly what these schemas accept, and a limit above what the layout can
 * draw fails only at `episode render`, after the voice and the captures. Each limit
 * below is the measured capacity of its box (1920x1080, the brand fonts), proven by
 * test/gpu/capacity.gpu.ts, which lints every block with every drawn string at its
 * maxLength and a filler about 5 % wider per character than ordinary prose
 * (test/capacity.ts). Change a limit, and that test must stay green.
 * Free-standing labels (a scale object, a diagram element, a timeline event, a map
 * pin) have no box: how many characters they take depends on where the script puts
 * them, and the layout lint at render time judges that.
 *
 * Under hook captions the stage is 140 px shorter (540 px, not 680) and some boxes
 * hold less: hookMaxLength and hookMaxItems (src/schema.ts) are that capacity, and
 * `episode check` applies them to a beat flagged hook (the renderer, to a scene a
 * hook caption is on screen in). A block has one number per box, the strictest of
 * its layouts: an EvidenceCard holds 88 / 165 characters of statement / quote beside
 * no image and 68 / 134 beside one, so 68 / 134; a claim board of five claims holds
 * a `by` line, six do not, and so on. test/gpu/capacity.gpu.ts proves every one on
 * the stage it is for, test/fixtures/capacity-hook-limits.json pins them.
 */
/** One line of a heading(48) title across the stage (1728 px of Orbitron, upper case). */
const TITLE = str(1, 44)
/** One line of a heading(44) title across a card panel (ListCard, 1496 px). */
const LIST_TITLE = str(1, 42)
/** The basis line is one 24 px line of 120 characters, its prefix included; the longest prefix, ScaleZoom's "To scale, linear. Basis: ", takes 25. */
const BASIS: Schema = { ...str(3, 95), description: 'What the comparison is based on, always shown on screen (owner rule)' }

/** The UnitGrid basis line is "1 square = <unitLabel>. Basis: <basis>" on one 120-character line: 20 + 36 + 60 fit. */
const UNIT_GRID_BASIS: Schema = { ...str(3, 60), description: BASIS.description }

/** The lower third: a 716 px box, the title in Orbitron 38 px upper case, the subtitle in 24 px mono. */
export const LABEL = obj({ title: str(1, 24), subtitle: str(1, 49) }, ['title'], 'Lower third over footage')

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
export function evidenceSchema(
  limits: { statement?: number; quote?: number; title?: number; locator?: number; hookStatement?: number; hookQuote?: number } = {},
): Schema {
  return obj({
    id: ID,
    claim_id: ID,
    kind: oneOf(['fact', 'quote', 'quantity', 'date', 'image', 'place']),
    statement: str(1, limits.statement, limits.hookStatement),
    source: obj({
      url: str(1),
      title: str(1, limits.title),
      tier: int(0),
      license: str(0),
      quote: str(0, limits.quote, limits.hookQuote),
      locator: str(0, limits.locator),
    }),
    paper_anchor: { type: ['string', 'null'] },
  })
}

/** Case-file claim, resolved (C6). The label is one 30 px mono line of the 1188 px box of a six-claim board (a board of up to four claims gives the label a second line). */
export const CLAIM = obj({
  id: ID,
  label: str(1, 66),
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
        caption: str(1, 51), // one 26 px mono line in 800 px
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
    // Beside the image the text column is 964 px: the statement is three lines of Orbitron 40 px,
    // the quote five lines of mono 32 px, the title one mono 24 px line (80 characters without
    // the image), and the source line, 72 characters of 18 px caps, holds a 16-character
    // hostname, "tier 1", "paper #ev-01" and three separators beside a locator of 26. Under
    // hook captions the stage is 140 px shorter: the statement holds 88 characters beside no image
    // and 68 beside one, the quote 165 and 134 (the hook limits are the smaller).
    props: obj(
      { evidence: evidenceSchema({ statement: 100, quote: 220, title: 66, locator: 24, hookStatement: 68, hookQuote: 134 }), image: MEDIA },
      ['evidence'],
      'One verified evidence item; cues highlight <evidence id> (quote types on), stamp <evidence id>',
    ),
  },
  QuoteCard: {
    map: false,
    platform: false,
    drawn: ['evidence.source.quote', 'evidence.source.title', 'evidence.source.locator', 'attribution'],
    // The quote is six lines of Cormorant Garamond 52 px (four under hook captions: 230). The
    // work line, "<attribution>, <title>", is one 30 px mono line of 77 characters: 32 + 2 + 43.
    // The meta line (locator, hostname, tier) holds 94 characters of 20 px caps.
    props: obj(
      { evidence: evidenceSchema({ statement: 160, quote: 320, title: 43, locator: 24, hookQuote: 230 }), attribution: str(1, 32) },
      ['evidence'],
      'A verbatim passage (texts and traditions, or a page that cannot be captured); cue highlight <evidence id>',
    ),
  },
  ClaimBoard: {
    map: false,
    platform: false,
    drawn: ['title', 'claims[].label', 'claims[].by'],
    props: obj(
      // rows are floor(450 / n) px under hook captions: a `by` line and a label line fit five rows, not six
      { claims: arr(CLAIM, 1, 6, 5), title: TITLE },
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
        // under hook captions the stack of labels, numbers, words and bar leaves no room for a note
        note: str(1, 110, 0),
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
        basis: UNIT_GRID_BASIS,
        unitLabel: str(1, 36),
        // the legend column is 480 px: one 30 px mono label line (26 characters), and three entries end above the basis line
        columns: int(5, 40),
        // under hook captions the legend ends 394 px below its top: two entries
        groups: arr(obj({ id: ID, count: int(1, 400), label: str(1, 26), tone: TONE }), 1, 3, 2),
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
        unit: str(1, 6), // the value box holds 14 characters (a range 16): a 6-character unit leaves room for a 4-digit value or a 3-digit range
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
          6, // under hook captions 354 px hold six rows of a 53 px pitch
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
      // an item is one 32 px mono line of 1386 px when five rows share the card (fewer rows take two lines)
      // under hook captions a note leaves four rows (floor(242 / n) px) a 40 px line
      { title: LIST_TITLE, items: arr(obj({ id: ID, text: str(1, 72) }), 1, 5, 4), note: str(1, 110) },
      ['title', 'items'],
      'A short list, e.g. what would change our mind; cue show <item id>',
    ),
  },
  ShareCard: {
    map: false,
    platform: false,
    drawn: ['headline', 'url', 'lines[]'],
    props: obj(
      // headline: two Orbitron 54 px lines; url: one 44 px mono line of 1200 px; lines: one 30 px mono line each
      { headline: str(1, 50), url: str(1, 43), lines: arr(str(1, 66), 0, 3) },
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
