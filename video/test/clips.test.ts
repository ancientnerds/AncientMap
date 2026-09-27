import { describe, expect, it } from 'vitest'

import { chapterTagIndex } from '../src/blocks/ChapterTag'
import { clipProblems, clipTime, trimFrames } from '../src/blocks/clips'
import type { Capture } from '../src/blocks/types'

const clip: Capture = {
  id: 'pf1',
  kind: 'platform',
  src: 'captures/pf1.mp4',
  fps: 60,
  duration_s: 4,
  width: 2880,
  height: 1620,
  events: [],
  credits: [],
}

describe('clip rules', () => {
  it('accepts a clip that covers its scene from the start offset', () => {
    expect(clipProblems(clip, 0.5, { fps: 60, durationInFrames: 210 })).toEqual([])
  })
  it('refuses a clip that would end before its scene (black frames)', () => {
    expect(clipProblems(clip, 1, { fps: 60, durationInFrames: 240 })).toEqual([
      'capture pf1 is 4 s long; the scene needs 5.000 s from 1 s (record a longer take or shorten the beat)',
    ])
  })
  it('refuses a still where a clip belongs', () => {
    expect(clipProblems({ ...clip, fps: null, duration_s: null }, 0, { fps: 60, durationInFrames: 60 })).toEqual(['capture pf1 is a still, not a clip'])
  })
  it('converts between clip seconds and scene frames', () => {
    expect(trimFrames(0.5, 60)).toBe(30)
    expect(clipTime(0.5, 90, 60)).toBe(2)
  })
})

describe('chapter tag (owner rule: no title card)', () => {
  const chapters = [
    { title: 'The stone', frame: 0 },
    { title: 'On the globe', frame: 600 },
  ]
  it('shows no tag during the first chapter and the second chapter tag for three seconds', () => {
    for (let frame = 0; frame < 600; frame++) expect(chapterTagIndex(chapters, frame, 60)).toBeNull()
    for (let frame = 600; frame < 780; frame++) expect(chapterTagIndex(chapters, frame, 60)).toBe(1)
    expect(chapterTagIndex(chapters, 780, 60)).toBeNull()
  })
})
