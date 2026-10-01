/**
 * Remotion entry of the real-browser lint check (guard.gpu.ts): compositions
 * with planted layout violations, drawn through the real LayoutProvider,
 * LayoutBox and LayoutGuard in Remotion's Chrome.
 *
 * The brand font files arrive SLOW_FONTS_MS late (fetch is held back here, as
 * a slow disk or a cold cache would), so every composition mounts, and every
 * render tab reaches its first frame, while Orbitron is still missing and the
 * text is laid out in a fallback font. OVERFLOWING_TEASER takes two lines in
 * that fallback and three in Orbitron (measured 2026-09-27 in Remotion's
 * chrome-headless-shell), so a lint that measured before the fonts arrived
 * would pass it.
 */
import React, { useMemo } from 'react'
import type { CSSProperties } from 'react'
import { AbsoluteFill, Composition, registerRoot, useCurrentFrame } from 'remotion'

import { EvidenceCard } from '../../src/blocks/EvidenceCard'
import { QuoteCard } from '../../src/blocks/QuoteCard'
import type { Evidence } from '../../src/blocks/types'
import { webglRenderer } from '../../src/gpu'
import type { Rect } from '../../src/layout/geometry'
import { LayoutBox, LayoutProvider, Registry } from '../../src/layout/LayoutBox'
import { LayoutGuard } from '../../src/layout/LayoutGuard'
import { ZONES } from '../../src/layout/zones'
import { loadBrandFonts } from '../../src/theme/fonts'
import { body, heading } from '../../src/theme/type'

const SLOW_FONTS_MS = 2500

/** Four words: two lines in the fallback font, three in Orbitron 700 at 104 px (the teaser box holds two). */
const OVERFLOWING_TEASER = 'WHO ENGINEERED BAALBEK MONOLITHS?'
/** Two lines in both fonts: fits. */
const FITTING_TEASER = 'WHICH CIVILISATION QUARRIED THESE?'

const fetchNow = window.fetch.bind(window)
window.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
  String(input).includes('/fonts/') ? new Promise<void>((resolve) => setTimeout(resolve, SLOW_FONTS_MS)).then(() => fetchNow(input, init)) : fetchNow(input, init)
loadBrandFonts()

type LintProps = { lint: boolean; gpu: string }

const place = (r: Rect): CSSProperties => ({ position: 'absolute', left: r.x, top: r.y, width: r.w, height: r.h, overflow: 'hidden', ...body(30) })

/** The Thumbnail's teaser (plan D Task 18): TEASER_ZONE {96, 72, 1440, 380}, upper-case Orbitron 104 px, two lines at most. */
const Teaser: React.FC<{ id: string; text: string }> = ({ id, text }) => (
  <LayoutBox id={id} kind="text" style={{ position: 'absolute', left: 140, top: 96, width: 1368, height: 332, overflow: 'hidden', display: 'flex', alignItems: 'center', ...heading(104) }}>
    {text}
  </LayoutBox>
)

/**
 * Six frames. Every frame: the teaser overflows, `edge` leaves the title-safe
 * area, `lt` covers `captions`. From frame 3 on `drop` sits in the YouTube
 * controls. `fits` never breaks a rule. Rendered at scale 0.5, so a box
 * measured in device pixels instead of composition pixels would move `edge`
 * back inside the safe area and `drop` out of the controls.
 */
const Planted: React.FC<LintProps> = ({ lint }) => {
  const frame = useCurrentFrame()
  const registry = useMemo(() => new Registry(lint), [lint])
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <LayoutProvider registry={registry}>
        <Teaser id="teaser" text={OVERFLOWING_TEASER} />
        <LayoutBox id="captions" kind="text" style={place(ZONES.caption)}>
          A HOOK CAPTION
        </LayoutBox>
        <LayoutBox id="lt" kind="text" style={place({ x: 96, y: 780, w: 760, h: 96 })}>
          A LOWER THIRD
        </LayoutBox>
        <LayoutBox id="edge" kind="text" style={place({ x: 1800, y: 500, w: 100, h: 48 })}>
          EDGE
        </LayoutBox>
        <LayoutBox id="drop" kind="text" style={place({ x: 1200, y: frame < 3 ? 846 : 970, w: 300, h: 48 })}>
          DROP
        </LayoutBox>
        <LayoutBox id="fits" kind="text" style={place({ x: 1560, y: 300, w: 240, h: 64 })}>
          3 / 7
        </LayoutBox>
        {lint ? <LayoutGuard /> : null}
      </LayoutProvider>
    </AbsoluteFill>
  )
}

/**
 * One frame, built like the Thumbnail: the scene under a registry that never
 * measures (its overlapping pair must not be reported), the teaser under the
 * lint registry. `candidate` 1 carries the overflowing teaser, 2 the fitting one.
 */
const TeaserOnly: React.FC<LintProps & { candidate: number }> = ({ lint, candidate }) => {
  const scenes = useMemo(() => new Registry(false), [])
  const teaser = useMemo(() => new Registry(lint), [lint])
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <LayoutProvider registry={scenes}>
        <LayoutBox id="scene:a" kind="text" style={place(ZONES.caption)}>
          SCENE TEXT
        </LayoutBox>
        <LayoutBox id="scene:b" kind="text" style={place({ x: 96, y: 780, w: 760, h: 96 })}>
          SCENE TEXT
        </LayoutBox>
      </LayoutProvider>
      <LayoutProvider registry={teaser}>
        <Teaser id={`thumbnail${candidate}:teaser`} text={candidate === 1 ? OVERFLOWING_TEASER : FITTING_TEASER} />
        {lint ? <LayoutGuard /> : null}
      </LayoutProvider>
    </AbsoluteFill>
  )
}

/**
 * The source line of an evidence card, drawn by the real EvidenceCard and
 * QuoteCard (bypassing the schema, which refuses a title this long) with the
 * title of a real dossier source. The line must be measured, not clipped: the
 * inner title div once had its own overflow: hidden, so the outer LayoutBox never
 * saw the text that did not fit and the lint reported "clean" on a cut-off title.
 */
const evidenceOf = (title: string): Evidence => ({
  id: 'e1',
  claim_id: 'c1',
  kind: 'quantity',
  statement: 'The Stone of the Pregnant Woman weighs about 1,000 tonnes.',
  source: { url: 'https://www.researchgate.net/publication/1', title, tier: 1, license: '', quote: 'estimated to weigh 1,650 tonnes', locator: 'section 2' },
  paper_anchor: 'ev-01',
})

type SourceLineProps = LintProps & { title: string }

const sourceLine =
  (Card: typeof EvidenceCard | typeof QuoteCard): React.FC<SourceLineProps> =>
  ({ lint, title }) => {
    const registry = useMemo(() => new Registry(lint), [lint])
    return (
      <AbsoluteFill style={{ backgroundColor: '#000' }}>
        <LayoutProvider registry={registry}>
          <Card props={{ evidence: evidenceOf(title) }} cues={[]} durationInFrames={1} sceneId="b02" sceneFrom={0} stage={ZONES.stage} />
          {lint ? <LayoutGuard /> : null}
        </LayoutProvider>
      </AbsoluteFill>
    )
  }

const EvidenceSource = sourceLine(EvidenceCard)
const QuoteSource = sourceLine(QuoteCard)

const withGpu = async <P extends LintProps>({ props }: { props: P }) => ({ props: { ...props, gpu: webglRenderer() } })

const Root: React.FC = () => (
  <>
    <Composition id="Planted" component={Planted} defaultProps={{ lint: false, gpu: '' }} calculateMetadata={withGpu} durationInFrames={6} fps={60} width={1920} height={1080} />
    <Composition
      id="TeaserOnly"
      component={TeaserOnly}
      defaultProps={{ lint: false, gpu: '', candidate: 1 }}
      calculateMetadata={withGpu}
      durationInFrames={1}
      fps={60}
      width={1920}
      height={1080}
    />
    <Composition id="EvidenceSource" component={EvidenceSource} defaultProps={{ lint: false, gpu: '', title: 'x' }} calculateMetadata={withGpu} durationInFrames={1} fps={60} width={1920} height={1080} />
    <Composition id="QuoteSource" component={QuoteSource} defaultProps={{ lint: false, gpu: '', title: 'x' }} calculateMetadata={withGpu} durationInFrames={1} fps={60} width={1920} height={1080} />
  </>
)

registerRoot(Root)
