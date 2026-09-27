import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { Episode, EpisodeVisuals } from '../src/Episode'
import { DEMO_TIMELINE } from '../src/fixtures/demo'
import { contains, overlapArea } from '../src/layout/geometry'
import { SAFE, ZONES } from '../src/layout/zones'
import { SceneView } from '../src/SceneView'
import { DURATION_BADGE, TEASER_ZONE, THUMBNAIL_CREDIT_ZONE, Thumbnail, creditsAt, teaserOf } from '../src/Thumbnail'

const SRC = fileURLToPath(new URL('../src', import.meta.url))

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) return sources(full)
    return /\.tsx?$/.test(name) ? [full] : []
  })
}

/** Remotion renders frames out of order in parallel tabs: every frame must be a pure function of its number. */
const RULES: [RegExp, string][] = [
  [/Math\.random/, 'randomness only through random(seed) from remotion'],
  [/Date\.now|new Date\(|performance\.now/, 'time comes from useCurrentFrame(), never the clock'],
  [/setTimeout|setInterval|requestAnimationFrame/, 'no timers inside a frame render'],
  [/\b(transition|animation|animationName)\s*:/, 'no CSS transitions or animations'],
  [/@keyframes/, 'no CSS keyframes'],
  [/<(OffthreadVideo|Html5Video|Html5Audio)\b/, '<Video> and <Audio> come from @remotion/media'],
  [/import\s*\{[^}]*\b(Audio|Video)\b[^}]*\}\s*from\s*'remotion'/, '<Video> and <Audio> come from @remotion/media'],
  [/<(video|audio|img)\b/, 'native media tags do not hold the frame until they loaded'],
  [/backgroundImage|background-image/, 'no CSS background images'],
]

describe('Remotion rules over every file in src/', () => {
  const files = sources(SRC)
  it('finds the renderer sources', () => {
    expect(files.length).toBeGreaterThan(40)
  })
  it.each(RULES)('%s', (pattern, rule) => {
    const offenders = files.filter((f) => pattern.test(readFileSync(f, 'utf-8'))).map((f) => path.relative(SRC, f))
    expect(offenders, rule).toEqual([])
  })
})

describe('compositions', () => {
  it('export the components Root registers', () => {
    for (const component of [Episode, EpisodeVisuals, SceneView, Thumbnail]) expect(typeof component).toBe('function')
  })
  it('register Episode and Thumbnail with their size and length from the timeline', () => {
    const root = readFileSync(path.join(SRC, 'Root.tsx'), 'utf-8')
    expect(root).toContain('id="Episode"')
    expect(root).toContain('id="Thumbnail"')
    expect(root.match(/calculateMetadata=\{/g)).toHaveLength(2)
    expect(root).toContain('gpu: webglRenderer()')
  })
})

describe('thumbnail teaser and credit line (owner decisions 24-25, spec 4.8)', () => {
  it('sit inside the title-safe area and clear of the duration badge YouTube lays over a thumbnail', () => {
    expect(contains(SAFE, TEASER_ZONE)).toBe(true)
    expect(overlapArea(TEASER_ZONE, DURATION_BADGE)).toBe(0)
    // the scene's credit line: bottom left, the size of the episode's credit zone, clear of teaser, badge and lower third
    expect(contains(SAFE, THUMBNAIL_CREDIT_ZONE)).toBe(true)
    for (const other of [TEASER_ZONE, DURATION_BADGE, ZONES.lowerThird]) expect(overlapArea(THUMBNAIL_CREDIT_ZONE, other)).toBe(0)
    expect([THUMBNAIL_CREDIT_ZONE.w, THUMBNAIL_CREDIT_ZONE.h]).toEqual([ZONES.credit.w, ZONES.credit.h])
  })
  it('draws the teaser of the chosen candidate and refuses one the timeline does not have', () => {
    expect(teaserOf(DEMO_TIMELINE, 2)).toBe('Eighty buses heavy?')
    expect(() => teaserOf(DEMO_TIMELINE, 4)).toThrow(/thumbnail candidate 4 does not exist \(1\.\.3\)/)
  })
  it('takes the credit line of the scene that shows the frame, and none from a scene without credits', () => {
    const scene = DEMO_TIMELINE.scenes[1]
    const credits = [
      { sceneId: scene.id, text: 'Photo: Jane Doe (CC BY-SA 4.0)' },
      { sceneId: scene.id, text: '© Mapbox © Maxar' },
    ]
    const timeline = { ...DEMO_TIMELINE, credits }
    expect(creditsAt(timeline, scene.from)).toEqual(['Photo: Jane Doe (CC BY-SA 4.0)', '© Mapbox © Maxar'])
    expect(creditsAt(timeline, scene.from + scene.durationInFrames - 1)).toEqual(['Photo: Jane Doe (CC BY-SA 4.0)', '© Mapbox © Maxar'])
    expect(creditsAt(timeline, scene.from - 1)).toEqual([])
    expect(creditsAt(timeline, scene.from + scene.durationInFrames)).toEqual([])
  })
})
