import { describe, expect, it } from 'vitest'

import { REGISTRY_BLOCKS } from '../src/blocks/schemas'
import { DEMO_TIMELINE } from '../src/fixtures/demo'
import { validate } from '../src/schema'
import { assetProblem, collectSrcs, parseTimeline, sceneHasCaptions } from '../src/timeline'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = Record<string, any>
const clone = (): Json => JSON.parse(JSON.stringify(DEMO_TIMELINE))

describe('parseTimeline (plan C contract C8)', () => {
  it('accepts the demo timeline unchanged', () => {
    expect(parseTimeline(clone())).toEqual(DEMO_TIMELINE)
  })
  it('validates every demo scene against its block schema', () => {
    for (const scene of DEMO_TIMELINE.scenes) expect(validate(REGISTRY_BLOCKS[scene.block].props, scene.props), scene.id).toEqual([])
  })
  it.each([
    ['odd dimensions', (t: Json) => { t.width = 1919 }, /dimensions must be even/],
    ['another frame size', (t: Json) => { t.width = 1280; t.height = 720 }, /expected 1920x1080, got 1280x720/],
    ['wrong version', (t: Json) => { t.version = 2 }, /\$\.version: expected 1/],
    ['another frame rate', (t: Json) => { t.fps = 30 }, /\$\.fps: expected 60/],
    ['an unknown top-level key', (t: Json) => { t.intro = true }, /unknown key\(s\) intro/],
    ['a gap between scenes', (t: Json) => { t.scenes[1].from = 190 }, /\$\.scenes\[1\]\.from: expected 180/],
    ['scenes ending early', (t: Json) => { t.durationInFrames = 2300 }, /the scenes end at 2220, the episode at 2300/],
    ['an unknown block', (t: Json) => { t.scenes[0].block = 'TitleCard' }, /unknown block "TitleCard"/],
    ['invalid props', (t: Json) => { t.scenes[0].props.claims[0].icon = 'robot' }, /icon: "robot" is not one of/],
    ['an unknown prop', (t: Json) => { t.scenes[0].props.colour = 'red' }, /\.colour: not allowed/],
    ['a cue outside its scene', (t: Json) => { t.scenes[0].cues[0].frame = 400 }, /outside the scene \[0, 180\)/],
    ['an unknown cue verb', (t: Json) => { t.scenes[0].cues[0].do = 'flash' }, /"flash" is not one of/],
    ['a status cue without a status', (t: Json) => { t.scenes[1].cues[2].value = 'maybe' }, /a status cue needs one of/],
    ['a meter cue not summing to 100', (t: Json) => { t.scenes[2].cues[0].value = [80, 30] }, /two integers summing to 100/],
    ['a value on a show cue', (t: Json) => { t.scenes[4].cues[0].value = 3 }, /a show cue takes no value/],
    ['a first chapter after 0', (t: Json) => { t.chapters[0].frame = 5 }, /first chapter must start at frame 0/],
    ['a credit for a missing scene', (t: Json) => { t.credits = [{ sceneId: 'b99', text: '© x' }] }, /no scene "b99"/],
    ['overlapping captions', (t: Json) => { t.captions[1].from = 15 }, /overlaps the previous caption/],
    ['a decreasing ticker', (t: Json) => { t.ticker.evidence = [{ frame: 10, n: 2 }, { frame: 20, n: 1 }] }, /must not decrease/],
    ['a positive music gain', (t: Json) => { t.audio.music = { src: 'music/bed.wav', gainDb: 3, duck: { underNarrationDb: -12, attackFrames: 6, releaseFrames: 24 } } }, /gainDb: must be <= 0/],
    ['an absolute narration path', (t: Json) => { t.audio.narration = [{ src: 'C:/voice/b01.mp3', from: 0 }] }, /must lie under voice\//],
    ['a parent-dir path', (t: Json) => { t.audio.narration = [{ src: 'voice/../b01.mp3', from: 0 }] }, /is not a clean relative path/],
    ['two thumbnail candidates', (t: Json) => { t.thumbnails.pop() }, /expected exactly 3 thumbnail candidates, got 2/],
    ['a thumbnail past the end', (t: Json) => { t.thumbnails[0].frame = 2220 }, /\$\.thumbnails\[0\]\.frame: frame 2220 is past the end \(2220\)/],
    ['a one-word teaser', (t: Json) => { t.thumbnails[1].text = 'Buses?' }, /\$\.thumbnails\[1\]\.text: "Buses\?" has 1 word\(s\); a thumbnail teaser has 2-4/],
  ])('rejects %s', (_name, mutate, message) => {
    const t = clone()
    mutate(t)
    expect(() => parseTimeline(t)).toThrow(message)
  })
})

describe('asset paths', () => {
  it('accepts only clean paths under the four public-dir folders', () => {
    expect(assetProblem('media/stone_person.jpg')).toBeNull()
    expect(assetProblem('captures/pf1.mp4')).toBeNull()
    expect(assetProblem('fonts/orbitron-700.woff2')).toMatch(/must lie under/)
    expect(assetProblem('media//a.jpg')).toMatch(/not a clean relative path/)
  })
  it('collects every src anywhere in the timeline', () => {
    expect(collectSrcs({ a: { src: 'media/a.jpg', b: [{ src: 'captures/c.mp4' }] }, src: 'voice/b01.mp3' })).toEqual(['voice/b01.mp3', 'media/a.jpg', 'captures/c.mp4'])
  })
})

describe('frames', () => {
  it('reads the three thumbnail candidates (owner decisions 24-25) as episode frames with their teasers', () => {
    expect(DEMO_TIMELINE.thumbnails).toEqual([
      { frame: 108, text: 'Who moved it?' },
      { frame: 200, text: 'Eighty buses heavy?' },
      { frame: 300, text: 'Heavier than Giza?' },
    ])
  })
  it('knows which scenes carry hook captions', () => {
    expect(sceneHasCaptions(DEMO_TIMELINE, DEMO_TIMELINE.scenes[0])).toBe(true)
    expect(sceneHasCaptions(DEMO_TIMELINE, DEMO_TIMELINE.scenes[1])).toBe(false)
  })
})
