import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { checkBlocks, imagesToMeasure } from '../src/blocks'
import { collectSrcs, parseTimeline } from '../src/timeline'

const FIXTURE = fileURLToPath(new URL('./fixtures/smoke-timeline.json', import.meta.url))

describe('the smoke-render fixture (plan D local smoke task)', () => {
  const timeline = parseTimeline(JSON.parse(readFileSync(FIXTURE, 'utf-8')))
  it('is a valid 10-second timeline with every footage block', () => {
    expect(() => checkBlocks(timeline)).not.toThrow()
    expect(timeline.durationInFrames).toBe(600)
    expect(timeline.scenes.map((s) => s.block)).toEqual(['PhotoPlate', 'PlatformClip', 'GlobeShot', 'MapboxTopdown', 'SourceViewer', 'EvidenceCard'])
  })
  it('references exactly the assets the smoke task generates', () => {
    expect([...new Set(collectSrcs([timeline.audio, timeline.scenes]))].sort()).toEqual([
      'captures/globe.mp4',
      'captures/page.png',
      'captures/platform.mp4',
      'captures/topdown.jpg',
      'media/plate.jpg',
      'music/bed.wav',
      'voice/b01.mp3',
      'voice/b02.mp3',
    ])
    expect(imagesToMeasure(timeline)).toEqual(['media/plate.jpg'])
  })
})
