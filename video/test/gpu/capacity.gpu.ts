/**
 * Every block fits its own limits (workstation only, not CI: it needs the RTX
 * 3080, spec 4.11). Run from video/: `npm run test:gpu`.
 *
 * blocks/schemas.ts promises that "length limits are per block, where the text
 * must fit", and `episode check` accepts exactly what the schemas accept. A limit
 * above what the layout can draw therefore fails only at `episode render`, after
 * the voice and the captures. test/capacity.ts builds an episode with every
 * block on both stages and every drawn string at its maxLength (on the hook stage,
 * which is 140 px shorter, at the hookMaxLength / hookMaxItems the registry records
 * and `episode check` applies to a hook beat); this runs the real scripts/lint.ts on
 * it (the NVIDIA proved by the script, the brand fonts in) and requires that nothing
 * overflows, overlaps or leaves the safe area. When it fails, lower the limit in
 * schemas.ts (or give the text more room), run `npm run registry`, and mirror the
 * registry in tests/pipeline/studio/script_fixtures.py.
 *
 * The filler is a proxy for real text, so a second test lints the real thing where a limit
 * was once wrong: the widest real site names in every lower third (test/fixtures/
 * lower-third-names.json). The names above the limit cannot be linted: `episode check` and
 * parseTimeline refuse them before any browser starts, which is the point.
 */
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { COMPOSED } from '../../src/blocks/composed'
import { capacityTimeline, metaLineEdits, quotesOfLength, sceneVariants, sourceLineEdits } from '../capacity'
import { lintEpisode as lint } from './lint'

const VIDEO_ROOT = fileURLToPath(new URL('../..', import.meta.url))
const SLOW = 900_000
const NVIDIA = /^gpu: ANGLE \(NVIDIA, NVIDIA GeForce RTX 3080/m

type Json = Record<string, any>

let work = ''

beforeAll(() => {
  work = mkdtempSync(path.join(os.tmpdir(), 'studio-capacity-'))
})

afterAll(() => {
  rmSync(work, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 })
})

const lintEpisode = (episode: ReturnType<typeof capacityTimeline>) => lint(work, episode)

describe('the capacity episode in a real browser', () => {
  it('draws every block, on the full and on the hook stage, with every drawn string at its maxLength (hook capacity on the hook stage), without one layout violation', () => {
    const { status, output, byScene } = lintEpisode(capacityTimeline())
    expect(output).toMatch(NVIDIA)
    expect(Object.fromEntries(byScene)).toEqual({})
    expect(status, output).toBe(0)
  }, SLOW)

  it('draws the widest real site names of every length up to the limit in a lower third without one layout violation', () => {
    const { fit } = JSON.parse(readFileSync(path.join(VIDEO_ROOT, 'test/fixtures/lower-third-names.json'), 'utf-8')) as { fit: string[] }
    const names = sceneVariants(
      'PhotoPlate.full',
      fit.map((name, i) => ({ id: `name${i}`, edit: (props) => ((props.label as { title: string }).title = name) })),
    )
    const { status, output, byScene } = lintEpisode(names)
    expect(output).toMatch(NVIDIA)
    expect(Object.fromEntries(byScene)).toEqual({})
    expect(status, output).toBe(0)
  }, SLOW)
})

/** A variants run: every variant must lint clean, on the NVIDIA, naming the variant that does not. */
function expectClean(episode: ReturnType<typeof capacityTimeline>): void {
  const { status, output, byScene } = lintEpisode(episode)
  expect(output).toMatch(NVIDIA)
  expect(Object.fromEntries(byScene)).toEqual({})
  expect(status, output).toBe(0)
}

describe('text composed of several fields, at exactly its limit, in a real browser', () => {
  /*
   * A filler proves one word-wrap phase and one glyph mix; these are real words and real hosts. The reviewer's
   * hook quotes of 133 and 134 characters needed a fourth line in the 3-line box (2026-10-02), the limit is now 120.
   */
  const quote = (text: string) => (props: Json) => (props.evidence.source.quote = text)

  it.each(['EvidenceCard.withimage.hook', 'EvidenceCard.noimage.hook'])('draws real quotes of exactly the hook limit on the hook stage, %s', (scene) => {
    const limit = (JSON.parse(readFileSync(path.join(VIDEO_ROOT, 'src/blocks/registry.json'), 'utf-8')).blocks.EvidenceCard.props.properties.evidence.properties.source.properties.quote as { hookMaxLength: number }).hookMaxLength
    expectClean(sceneVariants(scene, quotesOfLength(limit, 12).map((text, i) => ({ id: `quote${i}`, edit: quote(text) }))))
  }, SLOW)

  it('draws every value text that fills the BarChart value box: single values of 14 characters, ranges of 16, on both stages', () => {
    const { single, range } = COMPOSED['BarChart.valueText']
    // [unit, single value, range]: "125,000 tonnes" 14, "123.456 metres" 14; "1,000–1,650 tons" 16, "19.6–20.5 metres" 16, "8,888–8,889 tons" 16
    const cases: [string, number, [number, number]][] = [
      ['tonnes', 125000, [100, 165]],
      ['metres', 123.456, [19.6, 20.5]],
      ['tons', 1250, [1000, 1650]],
      ['tons', 8888, [8888, 8889]],
      ['t', 123456789, [10000, 16500]],
    ]
    for (const scene of ['BarChart.3bars.full', 'BarChart.3bars.hook']) {
      const variants = cases.map(([unit, one, two], i) => ({
        id: `bars${i}`,
        edit: (props: Json) => {
          props.unit = unit
          props.bars[0].value = one
          props.bars[1].value = two
          expect(`${one.toLocaleString('en-US', { maximumFractionDigits: 3 })} ${unit}`.length).toBeLessThanOrEqual(single)
          expect(`${two[0].toLocaleString('en-US', { maximumFractionDigits: 3 })}–${two[1].toLocaleString('en-US', { maximumFractionDigits: 3 })} ${unit}`.length).toBeLessThanOrEqual(range)
        },
      }))
      expectClean(sceneVariants(scene, variants))
    }
  }, SLOW)

  it('draws the longest accepted unit with the project range: 1,000-1,650 tonnes is refused, 1,000-1,650 tons is the widest that fits', () => {
    // 'tonnes' with [1000, 1650] is 18 characters and overflowed the value box (the lint reported value:q4: overflow);
    // checkBarChart now refuses it before any browser starts, so the longest accepted unit is drawn with the range it fits
    expectClean(
      sceneVariants('BarChart.3bars.full', [
        { id: 'tons', edit: (p: Json) => ((p.unit = 'tons'), (p.bars[1].value = [1000, 1650])) },
        { id: 'tonnes', edit: (p: Json) => ((p.unit = 'tonnes'), (p.bars[1].value = [100, 165])) },
      ]),
    )
  }, SLOW)

  it.each([
    ['EvidenceCard.withimage.full', COMPOSED['EvidenceCard.sourceLine'].image],
    ['EvidenceCard.noimage.full', COMPOSED['EvidenceCard.sourceLine'].plain],
    ['EvidenceCard.withimage.hook', COMPOSED['EvidenceCard.sourceLine'].image],
  ] as const)('draws source lines of exactly the limit (%s: %i characters) with real hosts, and a host alone', (scene, limit) => {
    const edits = [...sourceLineEdits(limit), ...sourceLineEdits(limit, true)]
    expectClean(
      sceneVariants(
        scene,
        edits.map((e) => ({
          id: e.id,
          edit: (props: Json) => {
            Object.assign(props.evidence.source, { url: e.url, locator: e.locator })
            props.evidence.paper_anchor = e.anchor
          },
        })),
      ),
    )
  }, SLOW)

  it('draws QuoteCard meta lines of exactly the limit, with the longest locator and with none', () => {
    expectClean(
      sceneVariants(
        'QuoteCard.full',
        metaLineEdits(COMPOSED['QuoteCard.metaLine']).map((e) => ({ id: e.id, edit: (props: Json) => Object.assign(props.evidence.source, { url: e.url, locator: e.locator }) })),
      ),
    )
  }, SLOW)
})

