import { describe, expect, it } from 'vitest'

import { BLOCKS, checkBlocks, imagesToMeasure } from '../src/blocks'
import { REGISTRY_BLOCKS } from '../src/blocks/schemas'
import type { Capture } from '../src/blocks/types'
import { DEMO_TIMELINE } from '../src/fixtures/demo'
import { type Timeline, parseTimeline } from '../src/timeline'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = Record<string, any>

const clip: Capture = {
  id: 'pf1',
  kind: 'platform',
  src: 'captures/pf1.mp4',
  fps: 60,
  duration_s: 2.5,
  width: 2880,
  height: 1620,
  events: [],
  credits: ['© Mapbox © OpenStreetMap © Maxar'],
}

/** The demo timeline with its last scene, b12, replaced by `block`/`props` (180 frames = 3 s). */
function withScene(block: string, props: Json, cues: Json[] = []): Timeline {
  const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
  t.scenes[11] = { id: 'b12', from: 2040, durationInFrames: 180, block, props, cues }
  return parseTimeline(t)
}

/**
 * A source-page capture of the real Greek Wikipedia page: its URL path and its own
 * <title> are Greek; SourceViewer and the credit draw only the ASCII hostname.
 */
const page: Capture = {
  id: 'src1',
  kind: 'source',
  src: 'captures/src1.png',
  fps: null,
  duration_s: null,
  width: 2560,
  height: 3000,
  events: [
    { t: 0, name: 'gpu', label: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU)' },
    { t: 0, name: 'page', url: 'https://el.wikipedia.org/wiki/Κνωσός', title: 'Κνωσός - Βικιπαίδεια' },
    { t: 0, name: 'highlight', box: [200, 1500, 1800, 120], target: 'quote' },
  ],
  credits: ['Source page: el.wikipedia.org'],
}
/** Evidence whose verbatim quote is the Greek original: it sits in the page image, SourceViewer never draws it. */
const greekQuote: Json = {
  ...JSON.parse(JSON.stringify(DEMO_TIMELINE.scenes[1].props.evidence)),
  source: { url: 'https://el.wikipedia.org/wiki/Κνωσός', title: 'Knossos', tier: 2, license: '', quote: 'ἐν δὲ Κνωσός, μεγάλη πόλις', locator: 'lead' },
}

describe('the block library', () => {
  it('implements exactly the blocks of registry.json', () => {
    expect(Object.keys(BLOCKS).sort()).toEqual(Object.keys(REGISTRY_BLOCKS).sort())
  })
  it('measures the PhotoPlate images before the first frame', () => {
    const image = { id: 'm1', src: 'media/a.jpg', license: 'CC0', attribution: 'x', source_url: 'https://x.org', depicts: 'y', markers: [] }
    expect(imagesToMeasure(withScene('PhotoPlate', { image }))).toEqual(['media/a.jpg'])
  })
})

describe('checkBlocks', () => {
  it('passes the demo timeline', () => {
    expect(() => checkBlocks(parseTimeline(DEMO_TIMELINE))).not.toThrow()
  })
  it('refuses a local cue at a target the block does not show', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[4].cues[0].target = 'q9'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b05 \(ScaleDrawing\): show q9: not a target of this block \(q1, o2, o3\)/)
  })
  it('refuses a verb the block does not take', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[2].cues.push({ frame: 400, do: 'hide', target: 'x' })
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b03 \(Meter\): the block does not take hide cues/)
  })
  it('refuses an introduce cue for a claim no ClaimBoard lists', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[1].cues.push({ frame: 190, do: 'introduce', target: 'c9' })
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/introduce c9: no ClaimBoard of the episode lists this claim/)
  })
  it('refuses a meter cue in an episode without a Meter', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[2] = {
      id: 'b03',
      from: 360,
      durationInFrames: 180,
      block: 'ListCard',
      props: { title: 'x', items: [{ id: 'i9', text: 'y' }] },
      cues: [{ frame: 400, do: 'meter', target: 'meter', value: [70, 30] }],
    }
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/a meter cue needs a Meter scene/)
  })
  it('runs the block checks: meter start, clip length, map credits, marker boxes, diagram geometry', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[2].props.start = [60, 30]
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/meter start \[60,30\] must sum to 100/)
    expect(() => checkBlocks(withScene('PlatformClip', { clip }))).toThrow(/capture pf1 is 2.5 s long; the scene needs 3.000 s from 0 s/)
    const take = { ...clip, id: 'm1', kind: 'globe', width: 1920, height: 1080, duration_s: 5 }
    expect(() => checkBlocks(withScene('GlobeShot', { clip: take }))).toThrow(/carries map credits: a Mapbox take belongs in MapboxFlyover/)
    const image = { id: 'm1', src: 'media/a.jpg', license: 'CC0', attribution: 'x', source_url: 'https://x.org', depicts: 'y', markers: [{ id: 'mk1', box: [0.9, 0.5, 0.2, 0.1], label: '1 PERSON' }] }
    expect(() => checkBlocks(withScene('PhotoPlate', { image }))).toThrow(/marker mk1 box \[0.9,0.5,0.2,0.1\] is not a box inside the image/)
    const d: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    delete d.scenes[8].props.elements[1].r
    expect(() => checkBlocks(parseTimeline(d))).toThrow(/element d2 \(circle\) needs "r"/)
  })
  it('refuses text the brand fonts cannot draw, naming the scene, the path and the character', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[4].props.objects[1].label = 'Vinča figure'
    expect(() => checkBlocks(parseTimeline(t))).not.toThrow()
    t.scenes[4].props.objects[1].label = 'Κνωσός'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b05 \(ScaleDrawing\): props\.objects\[1\]\.label: "Κ" \(U\+039A\) has no glyph in the brand fonts/)
    // inside the declared latin-ext range, but the loaded JetBrains Mono file has no Ḫ
    t.scenes[4].props.objects[1].label = 'Ḫattuša'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b05 \(ScaleDrawing\): props\.objects\[1\]\.label: "Ḫ" \(U\+1E2A\) has no glyph in the brand fonts/)
    t.scenes[4].props.objects[1].label = 'Person'
    t.credits = [{ sceneId: 'b01', text: 'Photo → Commons' }]
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/timeline: credits\[0\]\.text \(scene b01\): "→" \(U\+2192\)/)
    t.credits = []
    t.thumbnails[0].text = 'Who → it?'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/timeline: thumbnails\[0\]\.text: "→" \(U\+2192\)/)
  })
  it('refuses a character whose upper case the brand fonts cannot draw (heading and hud draw upper case)', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.thumbnails[0].text = 'Set ƒ/8?'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(
      /timeline: thumbnails\[0\]\.text: "ƒ" \(U\+0192\) draws as "Ƒ" \(U\+0191\) in upper case, which has no glyph in the brand fonts/,
    )
  })
  it('refuses a ShareCard before the last scene: the link appears only on the end card', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[9] = { ...t.scenes[11], id: 'b10', from: 1620 }
    // the only error, so the last scene's ShareCard (b12) passes
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/:\n {2}scene b10 \(ShareCard\): ShareCard is the end card; only the last scene may use it$/)
  })
  it('keeps the registry hook limits on a scene a hook caption is on screen in (its stage is 140 px shorter) and on no other', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    // b01 is a ClaimBoard under the demo's hook captions: six claims fit the full stage, five the hook stage
    const claims = t.scenes[0].props.claims
    t.scenes[0].props.claims = [...claims, ...Array.from({ length: 6 - claims.length }, (_, i) => ({ ...claims[0], id: `c-extra-${i}` }))]
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b01 \(ClaimBoard\): props\.claims: more than 5 items on a hook beat/)
    t.captions = []
    expect(() => checkBlocks(parseTimeline(t))).not.toThrow()
  })
  it('checks only the strings the video draws: a page title, an original quote in a page image and a URL path pass (owner decision 32)', () => {
    expect(() => checkBlocks(withScene('SourceViewer', { page, evidence: greekQuote }))).not.toThrow()
  })
  it('refuses a drawn string outside the brand fonts: a claim label, a capture credit', () => {
    const t: Json = JSON.parse(JSON.stringify(DEMO_TIMELINE))
    t.scenes[0].props.claims[0].label = 'Κνωσός'
    expect(() => checkBlocks(parseTimeline(t))).toThrow(/scene b01 \(ClaimBoard\): props\.claims\[0\]\.label: "Κ" \(U\+039A\)/)
    const greekCredit = { ...page, credits: ['Source page: Βικιπαίδεια'] }
    expect(() => checkBlocks(withScene('SourceViewer', { page: greekCredit, evidence: greekQuote }))).toThrow(
      /scene b12 \(SourceViewer\): props\.page\.credits\[0\]: "Β" \(U\+0392\)/,
    )
  })
})
