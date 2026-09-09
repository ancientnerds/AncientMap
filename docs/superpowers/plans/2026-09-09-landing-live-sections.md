# Landing Live Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The homepage keeps its hero and screenshot sections but gains three server-rendered, data-fresh sections directly under the hero (Stories with client-side filters, Weekly Journal, Research Papers), a keyword H1, an intro paragraph and correct site counts.

**Architecture:** The homepage becomes the tenth SSR page type: nginx proxies `/` to a new API route `GET /home`, which builds a `{type: "landing"}` payload from the DB, renders it through the existing React SSR sidecar into a `<div id="root">` inside the built `index.html`, substitutes live counts into the hero, caches the document for 300 s and falls back to the static file when the API or sidecar is down. Only `#root` hydrates in the browser (`landingMain.tsx`); the hero and the screenshot sections stay static HTML.

**Tech Stack:** FastAPI + SQLAlchemy (payload), Node SSR sidecar (`ssr/server.mjs`, `entry-server.tsx`), React 18 `hydrateRoot`, Vite MPA entry `index.html`, vitest, pytest, nginx.

**Spec:** `docs/superpowers/specs/2026-09-09-landing-live-sections-design.md`

---

## File structure

**Frontend (`ancient-nerds-map/`)**

| File | Responsibility |
|---|---|
| `src/types/anRoute.ts` (modify) | `LandingRoute` and the teaser types; union extended |
| `src/seo/meta.ts` (modify) | `sitesShort()` and `landingMeta()` |
| `src/seo/registry.tsx` (modify) | `landing` entry |
| `src/seo/__tests__/pyref/landing.route.json` (create) | Fixture payload for render/entry-server tests |
| `src/seo/__tests__/fixtures.ts`, `registry.test.tsx` (modify) | Cover the tenth type |
| `src/pages/LandingLive.tsx` (create) | Composes the three sections from the payload |
| `src/landing/SectionHead.tsx` (create) | `>_ [ fig. N — name ]` header with status |
| `src/landing/RelativeTime.tsx` (create) | Absolute date on the server, relative after mount |
| `src/landing/feedClient.ts` (create) | `/api/news/feed` fetch + row→`StoryTeaser` mapping for chips and load-more |
| `src/landing/LandingStories.tsx` (create) | Lead + rail, chips, load more |
| `src/landing/LandingJournals.tsx` (create) | Lead + rail, no client logic |
| `src/landing/LandingPapers.tsx` (create) | Lead + rail, evidence strip, Theo line |
| `src/landing/__tests__/landingLive.test.tsx` (create) | renderToString assertions |
| `src/landing/__tests__/feedClient.test.ts` (create) | Mapping tests |
| `src/styles/landing-live.css` (create) | Section styling |
| `src/landingMain.tsx` (create) | Hydration entry for `#root` |
| `index.html` (modify) | H1 swap, intro paragraph, `#root`, `data-stat` spans, counts, sections removed, entry script |
| `vite.config.ts` (modify) | Manifest description, SW `navigateFallbackDenylist` |
| `.size-limit.json`, `package.json` (modify) | Bundle budget |

**Backend**

| File | Responsibility |
|---|---|
| `api/services/site_stats.py` (create) | `get_site_stats()` moved out of `main.py`, shared by `/api/stats` and the landing route |
| `api/seo_shell.py` (modify) | Optional `postprocess` hook on `ssr_shell_response` |
| `api/routes/landing_html.py` (create) | Pure payload builders + `GET /home` |
| `api/main.py` (modify) | Router registration, `/api/stats` delegates to the service |
| `tests/api/test_landing_html.py` (create) | DB-less builder and route tests |
| `ancientnerds-nginx-config` (modify) | `location = /` proxy + `@home_static` |
| `.github/workflows/ci.yml` (modify) | size-limit step |

Commands run from the repo root unless a task says `cd ancient-nerds-map`. Python tests: `python -m pytest`. Frontend tests: `npx vitest run <file>`.

---

### Task 1: Route type and `landingMeta`

**Files:**
- Modify: `ancient-nerds-map/src/types/anRoute.ts` (append before `export type AnRoute`, extend union)
- Modify: `ancient-nerds-map/src/seo/meta.ts` (import + two exports)
- Create: `ancient-nerds-map/src/landing/__tests__/landingMeta.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// ancient-nerds-map/src/landing/__tests__/landingMeta.test.ts
import { describe, expect, it } from 'vitest'

import { landingMeta, renderHead, sitesShort } from '../../seo/meta'
import type { LandingRoute } from '../../types/anRoute'

const route: LandingRoute = {
  type: 'landing',
  stats: { sites: 1_759_673, stories: 3189, journals: 23, papers: 24 },
  stories: null,
  journals: null,
  papers: null,
}

describe('sitesShort', () => {
  it('floors to one decimal so the count never overstates the database', () => {
    expect(sitesShort(1_759_673)).toBe('1.7M')
    expect(sitesShort(2_000_000)).toBe('2M')
    expect(sitesShort(999_999)).toBe('0.9M')
  })
})

describe('landingMeta', () => {
  const m = landingMeta(route)

  it('carries the site count in title and description', () => {
    expect(m.title).toBe('Interactive Archaeological Map | Explore 1.7M+ Ancient Sites')
    expect(m.description).toContain('1.7 million archaeological sites')
    expect(m.canonical).toBe('https://ancientnerds.com/')
  })

  it('renders exactly one title with the brand suffix and one canonical', () => {
    const head = renderHead(m)
    expect(head.match(/<title>/g)).toHaveLength(1)
    expect(head).toContain('Explore 1.7M+ Ancient Sites | Ancient Nerds</title>')
    expect(head.match(/<link rel="canonical"/g)).toHaveLength(1)
    expect(head).toContain('/landing/og-image.png')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ancient-nerds-map && npx vitest run src/landing/__tests__/landingMeta.test.ts`
Expected: FAIL — `landingMeta`/`sitesShort` are not exported, `LandingRoute` does not exist.

- [ ] **Step 3: Add the route types**

Append to `ancient-nerds-map/src/types/anRoute.ts` directly above `export type AnRoute =`:

```ts
/**
 * Homepage teasers (landing-live sections, 2026-09-09). Every teaser
 * carries its final href as `path` — the API builds it with the same
 * slug helpers the target pages use (story_slug, slugify, site_path), so
 * the client never re-derives a URL.
 */
export interface StoryTeaser {
  id: number
  headline: string
  /** First sentence of post_text, trailing source links removed. */
  summary: string
  screenshot_url: string | null
  category: string | null
  significance: number | null
  /** Raw ISO timestamp; RelativeTime turns it into "2h ago" after mount. */
  created_at: string
  channel: string
  /** Number of web_sources on the story. */
  sources: number
  path: string
  site: { name: string; country: string | null; path: string } | null
}

export interface JournalTeaser {
  id: number
  title: string
  summary: string | null
  week_start: string | null
  week_end: string | null
  published_at: string | null
  words: number
  minutes: number
  /** "##" headings of the issue without the Sources/Videos appendix. */
  sections: string[]
  sources: number
  image_url: string | null
  path: string
}

export interface PaperTeaser {
  slug: string
  title: string
  summary: string | null
  published_at: string | null
  words: number | null
  minutes: number | null
  sources_analyzed: number
  quality_score: number | null
  hero_image_url: string | null
  path: string
}

export interface TheoStatus {
  question: string
  started_at: string | null
  sites_found: number
}

export interface LandingRoute {
  type: 'landing'
  stats: { sites: number; stories: number; journals: number; papers: number }
  /** null when the source has no rows — the section is then not rendered. */
  stories: { lead: StoryTeaser; rail: StoryTeaser[]; categories: string[] } | null
  journals: { lead: JournalTeaser; rail: JournalTeaser[]; total: number } | null
  papers: { lead: PaperTeaser; rail: PaperTeaser[]; total: number; theo: TheoStatus | null } | null
}
```

Extend the union:

```ts
export type AnRoute =
  | StoryRoute
  | StoryArchiveRoute
  | SiteRoute
  | SitesIndexRoute
  | CountryRoute
  | ResearchRoute
  | ResearchIndexRoute
  | ArticleRoute
  | ArticleIndexRoute
  | LandingRoute
```

- [ ] **Step 4: Add `sitesShort` and `landingMeta` to `meta.ts`**

Add `LandingRoute` to the type import from `'../types/anRoute'` (the import block ends at line 29). Append at the end of the file:

```ts
/** "1.7M" — floors to one decimal so the number never overstates the database. */
export function sitesShort(sites: number): string {
  return `${Math.floor(sites / 100_000) / 10}M`
}

export function landingMeta(route: LandingRoute): PageMeta {
  const short = sitesShort(route.stats.sites)
  return {
    title: `Interactive Archaeological Map | Explore ${short}+ Ancient Sites`,
    description:
      `Explore over ${short.replace('M', ' million')} archaeological sites worldwide on an ` +
      'interactive 3D globe. Discover ancient civilizations, historical empires, AI-curated ' +
      'stories, weekly journals and open research papers. Free platform for archaeology enthusiasts.',
    canonical: `${BASE_URL}/`,
    ogType: 'website',
    image: `${BASE_URL}/landing/og-image.png`,
  }
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ancient-nerds-map && npx vitest run src/landing/__tests__/landingMeta.test.ts`
Expected: PASS (5 tests). Then `npx tsc --noEmit` — expected: errors only in `registry.tsx` (`satisfies Record<AnRoute['type'], Entry>` now misses `landing`). Task 2 fixes that.

- [ ] **Step 6: Commit**

```bash
git add ancient-nerds-map/src/types/anRoute.ts ancient-nerds-map/src/seo/meta.ts ancient-nerds-map/src/landing/__tests__/landingMeta.test.ts
git commit -m "feat(landing): LandingRoute payload type and landingMeta"
```

---

### Task 2: `LandingLive` page, section components, registry and render tests

**Files:**
- Create: `ancient-nerds-map/src/landing/SectionHead.tsx`, `RelativeTime.tsx`, `LandingStories.tsx`, `LandingJournals.tsx`, `LandingPapers.tsx`
- Create: `ancient-nerds-map/src/pages/LandingLive.tsx`
- Create: `ancient-nerds-map/src/styles/landing-live.css`
- Create: `ancient-nerds-map/src/seo/__tests__/pyref/landing.route.json`
- Modify: `ancient-nerds-map/src/seo/__tests__/fixtures.ts`, `registry.test.tsx`, `src/seo/registry.tsx`
- Create: `ancient-nerds-map/src/landing/__tests__/landingLive.test.tsx`

This task builds the static render. Chips and load-more come in Task 3; `LandingStories` already accepts the props it will need.

- [ ] **Step 1: Write the fixture payload**

`ancient-nerds-map/src/seo/__tests__/pyref/landing.route.json` (there is no Python reference for this type — the `.route.json` is only a fixture; the parity test only enumerates `.html` files):

```json
{
  "type": "landing",
  "stats": { "sites": 1759673, "stories": 3189, "journals": 23, "papers": 24 },
  "stories": {
    "lead": {
      "id": 8207,
      "headline": "Vienna Roman mass grave dated to late 1st-early 2nd century CE; 85% of injuries perimortem",
      "summary": "Beneath a Vienna soccer field, the first known Roman mass war grave yielded 129 male skeletons.",
      "screenshot_url": "/data/news/screenshots/YGUoJy_SRr0_1038.webp",
      "category": "bioarchaeology",
      "significance": 9,
      "created_at": "2026-09-07T04:23:33",
      "channel": "Inside Archaeology",
      "sources": 5,
      "path": "/news-archive/vienna-roman-mass-grave-dated-to-late-1st-early-2nd-century-ce-85-of-injuries-perimortem-8207",
      "site": { "name": "Roman grave", "country": "Austria", "path": "/sites/austria/roman-grave-16147718" }
    },
    "rail": [
      {
        "id": 8245,
        "headline": "1-million-year-old stone tools on Sulawesi suggest earliest known seafaring",
        "summary": "Seven stone flakes found in a Sulawesi cornfield may date to 1.04 to 1.48 million years old.",
        "screenshot_url": "/data/news/screenshots/TKnMsjxSzTQ_292.webp",
        "category": "artifact",
        "significance": 8,
        "created_at": "2026-09-08T19:33:29",
        "channel": "Michael Button",
        "sources": 9,
        "path": "/news-archive/1-million-year-old-stone-tools-on-sulawesi-suggest-earliest-known-seafaring-8245",
        "site": null
      },
      {
        "id": 8208,
        "headline": "DNA confirms Mississippian cacao consumption at Etowah, Georgia, around 1000 years ago",
        "summary": "Genetic sequencing confirmed cacao DNA on 11th to 12th century pottery shards from Etowah.",
        "screenshot_url": null,
        "category": "artifact",
        "significance": 7,
        "created_at": "2026-09-07T04:23:33",
        "channel": "Inside Archaeology",
        "sources": 5,
        "path": "/news-archive/dna-confirms-mississippian-cacao-consumption-at-etowah-georgia-around-1000-years-ago-8208",
        "site": { "name": "Etowah", "country": null, "path": "/sites/unknown/etowah-259326a1" }
      }
    ],
    "categories": ["artifact", "bioarchaeology", "underwater", "theory", "architecture"]
  },
  "journals": {
    "lead": {
      "id": 74,
      "title": "Week of August 31: 476,000-Year-Old Wooden Structure Found, Dire Wolf Pups Born, and More",
      "summary": "Archaeologists at Kalambo Falls uncovered the oldest known wooden structure.",
      "week_start": "2026-08-31T00:00:00",
      "week_end": "2026-09-06T23:59:59",
      "published_at": "2026-09-07T04:20:43",
      "words": 2762,
      "minutes": 12,
      "sections": ["Artifact Discoveries", "Remote Sensing & Technology", "Bioarchaeology & Ancient DNA", "In Brief"],
      "sources": 35,
      "image_url": "/data/news/screenshots/nMxEoIrMwX8_367.webp",
      "path": "/articles/week-of-august-31-476000-year-old-wooden-structure-found-dire-wolf-pups-born-and-more"
    },
    "rail": [
      {
        "id": 73,
        "title": "Week of August 24: 25 Turtle Figurines in Turkish Cave, World's First Brand, and More",
        "summary": null,
        "week_start": "2026-08-24T00:00:00",
        "week_end": "2026-08-30T23:59:59",
        "published_at": "2026-08-30T23:28:56",
        "words": 2510,
        "minutes": 11,
        "sections": [],
        "sources": 30,
        "image_url": null,
        "path": "/articles/week-of-august-24-25-turtle-figurines-in-turkish-cave-worlds-first-brand-and-more"
      }
    ],
    "total": 23
  },
  "papers": {
    "lead": {
      "slug": "the-egyptian-hard-stone-precision-debate",
      "title": "The Egyptian Hard-Stone Precision Debate",
      "summary": "Mainstream explanations of Egyptian hard-stone working are tested against the Serapeum boxes.",
      "published_at": "2026-08-31T22:07:06",
      "words": 6466,
      "minutes": 28,
      "sources_analyzed": 2748,
      "quality_score": 98,
      "hero_image_url": "https://ancientnerds.com/data/research-images/4bf89556/p7.jpg",
      "path": "/research/the-egyptian-hard-stone-precision-debate"
    },
    "rail": [
      {
        "slug": "submerged-sites-between-geology-and-pseudoarchaeology",
        "title": "Submerged Sites Between Geology and Pseudoarchaeology",
        "summary": null,
        "published_at": "2026-08-31T22:07:05",
        "words": 7057,
        "minutes": 30,
        "sources_analyzed": 3169,
        "quality_score": 98,
        "hero_image_url": null,
        "path": "/research/submerged-sites-between-geology-and-pseudoarchaeology"
      }
    ],
    "total": 24,
    "theo": { "question": "Water erosion evidence in the Osiris Shaft", "started_at": "2026-09-09T06:00:00Z", "sites_found": 1340 }
  }
}
```

- [ ] **Step 2: Write the failing render test**

```tsx
// ancient-nerds-map/src/landing/__tests__/landingLive.test.tsx
/**
 * The landing sections render under Node without browser APIs — exactly
 * what the SSR sidecar does. Effects (relative time, feed refetch) do not
 * run in renderToString, so the server output carries absolute dates.
 */
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { AuthProvider } from '../../contexts/AuthContext'
import { SeoRoute } from '../../seo/registry'
import { RouteProvider } from '../../seo/RouteContext'
import { FIXTURES } from '../../seo/__tests__/fixtures'
import type { LandingRoute } from '../../types/anRoute'

function render(route: LandingRoute): string {
  return renderToString(
    <RouteProvider value={route}>
      <AuthProvider>
        <SeoRoute />
      </AuthProvider>
    </RouteProvider>,
  )
}

describe('LandingLive', () => {
  const html = render(FIXTURES.landing)

  it('renders three h2 section labels in spec order', () => {
    const labels = [...html.matchAll(/<h2[^>]*class="ll-fig"[^>]*>(.*?)<\/h2>/g)].map(m => m[1])
    expect(labels).toHaveLength(3)
    expect(labels[0]).toContain('stories, live')
    expect(labels[1]).toContain('weekly journal')
    expect(labels[2]).toContain('research papers')
    expect(html).not.toContain('<h1')
  })

  it('links every teaser to its page', () => {
    for (const href of [
      FIXTURES.landing.stories!.lead.path,
      ...FIXTURES.landing.stories!.rail.map(s => s.path),
      FIXTURES.landing.journals!.lead.path,
      ...FIXTURES.landing.journals!.rail.map(j => j.path),
      FIXTURES.landing.papers!.lead.path,
      ...FIXTURES.landing.papers!.rail.map(p => p.path),
    ]) {
      expect(html).toContain(`href="${href}"`)
    }
    expect(html).toContain('href="/news.html"')
    expect(html).toContain('href="/articles.html"')
    expect(html).toContain('href="/research/"')
  })

  it('renders absolute dates on the server, never "ago"', () => {
    expect(html).toContain('Sep 7')
    expect(html).not.toContain(' ago')
  })

  it('shows the evidence strip and the Theo line', () => {
    expect(html).toContain('2,748')
    expect(html).toContain('Theo is researching')
    expect(html).toContain('Water erosion evidence in the Osiris Shaft')
  })

  it('never prints undefined or null', () => {
    expect(html).not.toMatch(/undefined|null/)
  })

  it('drops the Theo line and whole sections when their data is null', () => {
    const bare: LandingRoute = {
      ...FIXTURES.landing,
      journals: null,
      papers: { ...FIXTURES.landing.papers!, theo: null },
    }
    const out = render(bare)
    expect(out).not.toContain('weekly journal')
    expect(out).not.toContain('Theo is researching')
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd ancient-nerds-map && npx vitest run src/landing/__tests__/landingLive.test.tsx`
Expected: FAIL — `FIXTURES.landing` is undefined.

- [ ] **Step 4: Register the fixture and extend the registry test**

In `ancient-nerds-map/src/seo/__tests__/fixtures.ts` add `LandingRoute` to the type import and one line to `FIXTURES`:

```ts
  articleIndex: pyrefRoute('articleIndex') as ArticleIndexRoute,
  landing: pyrefRoute('landing') as LandingRoute,
```

In `ancient-nerds-map/src/seo/__tests__/registry.test.tsx` change the test name and list:

```ts
  it('kennt genau die 10 indexierten Seitentypen', () => {
    expect([...ROUTE_TYPES].sort()).toEqual(
      [
        'article',
        'articleIndex',
        'country',
        'landing',
        'research',
        'researchIndex',
        'site',
        'sitesIndex',
        'story',
        'storyArchive',
      ].sort(),
    )
  })
```

- [ ] **Step 5: Create `SectionHead.tsx` and `RelativeTime.tsx`**

```tsx
// ancient-nerds-map/src/landing/SectionHead.tsx
interface SectionHeadProps {
  fig: number
  name: string
  status: string
}

/** `>_ [ fig. N — name ]` — the section label of the live homepage blocks. */
export default function SectionHead({ fig, name, status }: SectionHeadProps) {
  return (
    <div className="ll-head">
      <h2 className="ll-fig">
        &gt;_ [ fig. {fig} — <b>{name}</b> ]
      </h2>
      <span className="ll-status">{status}</span>
    </div>
  )
}
```

```tsx
// ancient-nerds-map/src/landing/RelativeTime.tsx
import { useEffect, useState } from 'react'

import { formatRelativeDate } from '../utils/formatters'
import { shortDate } from './dates'

/**
 * Server and first client render show the absolute date ("Sep 7"); after
 * hydration the text becomes relative ("2h ago"). Rendering the relative
 * form on the server would differ from the client by the request/response
 * gap and trip React's hydration check.
 */
export default function RelativeTime({ iso }: { iso: string }) {
  const [text, setText] = useState(() => shortDate(iso))
  useEffect(() => {
    setText(formatRelativeDate(iso))
  }, [iso])
  return <time dateTime={iso}>{text}</time>
}
```

```ts
// ancient-nerds-map/src/landing/dates.ts
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "Sep 7" — locale-free so server and client agree byte for byte. */
export function shortDate(iso: string): string {
  const d = new Date(iso)
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`
}

/** "Aug 31 – Sep 6" for a journal week. */
export function dateRange(startIso: string | null, endIso: string | null): string {
  if (!startIso || !endIso) return ''
  return `${shortDate(startIso)} – ${shortDate(endIso)}`
}
```

- [ ] **Step 6: Create `LandingStories.tsx` (static render; interaction comes in Task 3)**

```tsx
// ancient-nerds-map/src/landing/LandingStories.tsx
import type { StoryTeaser } from '../types/anRoute'
import LazyImage from '../components/LazyImage'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

export interface StoriesBlock {
  lead: StoryTeaser
  rail: StoryTeaser[]
  categories: string[]
}

interface Props {
  initial: StoriesBlock
  total: number
}

const PLACEHOLDER =
  'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><rect fill="%230a1a14" width="16" height="9"/></svg>'

function Badge({ category }: { category: string | null }) {
  if (!category) return null
  return <span className={`ll-badge ll-cat-${category}`}>{category}</span>
}

function Meter({ value }: { value: number | null }) {
  if (value == null) return null
  return (
    <span className="ll-sig" aria-label={`significance ${value} of 10`}>
      SIG <b>{value}</b>
      <span className="ll-meter">
        <i style={{ width: `${value * 10}%` }} />
      </span>
    </span>
  )
}

export function StoryLead({ story }: { story: StoryTeaser }) {
  return (
    <a className="ll-lead" href={story.path}>
      <span className="ll-img ll-img-16x9">
        <LazyImage src={story.screenshot_url ?? PLACEHOLDER} alt="" width={1280} height={720} fallbackSrc={PLACEHOLDER} />
      </span>
      <span className="ll-body">
        <span className="ll-meta-row">
          <Badge category={story.category} /> <Meter value={story.significance} />
        </span>
        <span className="ll-title">{story.headline}</span>
        <span className="ll-p">{story.summary}</span>
        <span className="ll-meta">
          <b>{story.channel}</b> · {story.sources} sources · <RelativeTime iso={story.created_at} />
          {story.site && (
            <>
              {' · '}
              <span className="ll-site">{story.site.name}{story.site.country ? ` · ${story.site.country}` : ''}</span>
            </>
          )}
        </span>
      </span>
    </a>
  )
}

export function StoryRow({ story }: { story: StoryTeaser }) {
  return (
    <a className="ll-row ll-row-thumb" href={story.path}>
      <span className="ll-img ll-img-16x9">
        <LazyImage src={story.screenshot_url ?? PLACEHOLDER} alt="" width={192} height={108} fallbackSrc={PLACEHOLDER} />
      </span>
      <span>
        <span className="ll-row-title">{story.headline}</span>
        <span className="ll-meta">
          <Badge category={story.category} /> · SIG {story.significance ?? '–'} · {story.site ? story.site.name : story.channel} ·{' '}
          <RelativeTime iso={story.created_at} />
        </span>
      </span>
    </a>
  )
}

export default function LandingStories({ initial, total }: Props) {
  const { lead, rail } = initial
  return (
    <section className="ll-section" id="stories-live" aria-labelledby="ll-stories">
      <SectionHead fig={1} name="stories, live" status={`${total.toLocaleString('en-US')} stories · newest first`} />
      <div className="ll-two">
        <StoryLead story={lead} />
        <div className="ll-rail">
          {rail.map(s => (
            <StoryRow key={s.id} story={s} />
          ))}
        </div>
      </div>
      <div className="ll-foot">
        <span>lead = highest significance of the last 48h · rail = newest</span>
        <a href="/news.html">all stories →</a>
      </div>
    </section>
  )
}
```

- [ ] **Step 7: Create `LandingJournals.tsx` and `LandingPapers.tsx`**

```tsx
// ancient-nerds-map/src/landing/LandingJournals.tsx
import type { JournalTeaser } from '../types/anRoute'
import LazyImage from '../components/LazyImage'
import { dateRange, shortDate } from './dates'
import SectionHead from './SectionHead'

interface Props {
  data: { lead: JournalTeaser; rail: JournalTeaser[]; total: number }
}

export default function LandingJournals({ data }: Props) {
  const { lead, rail, total } = data
  return (
    <section className="ll-section" id="journal-live">
      <SectionHead
        fig={2}
        name="weekly journal"
        status={`No. ${lead.id}${lead.published_at ? ` · published ${shortDate(lead.published_at)}` : ''} · ${total} issues`}
      />
      <div className="ll-two">
        <a className="ll-lead" href={lead.path}>
          {lead.image_url && (
            <span className="ll-img ll-img-21x9">
              <LazyImage src={lead.image_url} alt="" width={1280} height={549} />
            </span>
          )}
          <span className="ll-body">
            <span className="ll-meta-row">
              <span className="ll-badge ll-cat-journal">journal</span>{' '}
              <span className="ll-meta">
                {dateRange(lead.week_start, lead.week_end)} · {lead.words.toLocaleString('en-US')} words · {lead.minutes} min read · {lead.sources} sources
              </span>
            </span>
            <span className="ll-title">{lead.title}</span>
            {lead.summary && <span className="ll-p">{lead.summary}</span>}
            {lead.sections.length > 0 && (
              <span className="ll-toc">
                {lead.sections.map(s => (
                  <span key={s}>{s}</span>
                ))}
              </span>
            )}
          </span>
        </a>
        <div className="ll-rail">
          {rail.map(j => (
            <a key={j.id} className="ll-row" href={j.path}>
              <span>
                <span className="ll-row-title">{j.title}</span>
                <span className="ll-meta">No. {j.id} · {dateRange(j.week_start, j.week_end)} · {j.minutes} min</span>
              </span>
              <span className="ll-arrow">→</span>
            </a>
          ))}
        </div>
      </div>
      <div className="ll-foot">
        <span>every Sunday · sourced, cited, illustrated</span>
        <a href="/articles.html">all {total} journals →</a>
      </div>
    </section>
  )
}
```

```tsx
// ancient-nerds-map/src/landing/LandingPapers.tsx
import type { PaperTeaser, TheoStatus } from '../types/anRoute'
import LazyImage from '../components/LazyImage'
import { shortDate } from './dates'
import SectionHead from './SectionHead'

interface Props {
  data: { lead: PaperTeaser; rail: PaperTeaser[]; total: number; theo: TheoStatus | null }
}

function Evidence({ paper }: { paper: PaperTeaser }) {
  return (
    <span className="ll-evidence">
      <span><i>sources analyzed</i><b>{paper.sources_analyzed.toLocaleString('en-US')}</b></span>
      {paper.quality_score != null && <span><i>quality</i><b>{paper.quality_score}</b></span>}
      {paper.words != null && <span><i>length</i><b>{paper.words.toLocaleString('en-US')} words</b></span>}
      <span><i>license</i><b>CC BY 4.0</b></span>
    </span>
  )
}

export default function LandingPapers({ data }: Props) {
  const { lead, rail, total, theo } = data
  return (
    <section className="ll-section" id="papers-live">
      <SectionHead fig={3} name="research papers" status={`${total} public · CC BY 4.0 · by Theo`} />
      <div className="ll-two">
        <a className="ll-lead" href={lead.path}>
          {lead.hero_image_url && (
            <span className="ll-img ll-img-16x9">
              <LazyImage src={lead.hero_image_url} alt="" width={1280} height={720} />
            </span>
          )}
          <span className="ll-body">
            <span className="ll-meta-row">
              <span className="ll-badge ll-cat-paper">paper</span>{' '}
              <span className="ll-meta">
                {lead.published_at ? `published ${shortDate(lead.published_at)}` : ''}
                {lead.minutes != null ? ` · ${lead.minutes} min read` : ''}
              </span>
            </span>
            <span className="ll-title">{lead.title}</span>
            {lead.summary && <span className="ll-p">{lead.summary}</span>}
            <Evidence paper={lead} />
          </span>
        </a>
        <div className="ll-rail">
          {rail.map(p => (
            <a key={p.slug} className="ll-row" href={p.path}>
              <span>
                <span className="ll-row-title">{p.title}</span>
                <span className="ll-meta">
                  {p.words != null ? `${p.words.toLocaleString('en-US')} words · ` : ''}
                  {p.sources_analyzed.toLocaleString('en-US')} sources
                  {p.published_at ? ` · ${shortDate(p.published_at)}` : ''}
                </span>
              </span>
              <span className="ll-badge ll-cat-paper">paper</span>
            </a>
          ))}
        </div>
      </div>
      {theo && (
        <a className="ll-theo" href="/theo.html">
          <span>
            <i className="ll-pulse" /> Theo is researching: <b>{theo.question}</b>
            {theo.started_at ? <> · since {shortDate(theo.started_at)}</> : null} · {theo.sites_found.toLocaleString('en-US')} sites found
          </span>
          <span>watch live →</span>
        </a>
      )}
      <div className="ll-foot">
        <span>papers publish when the citation gate passes · all titles are listed below</span>
        <a href="/research/">research library →</a>
      </div>
    </section>
  )
}
```

- [ ] **Step 8: Create `LandingLive.tsx`, register it, add the CSS**

```tsx
// ancient-nerds-map/src/pages/LandingLive.tsx
/**
 * LandingLive — the three data-fresh homepage sections rendered into
 * index.html's #root by the SSR sidecar (api/routes/landing_html.py).
 * Hero and screenshot sections around #root stay static HTML; this tree
 * is the only React on the page.
 */
import LandingJournals from '../landing/LandingJournals'
import LandingPapers from '../landing/LandingPapers'
import LandingStories from '../landing/LandingStories'
import { useRoute } from '../seo/RouteContext'

import '../styles/landing-live.css'

export default function LandingLive() {
  const route = useRoute()
  if (route?.type !== 'landing') return null
  return (
    <div className="landing-live">
      {route.stories && <LandingStories initial={route.stories} total={route.stats.stories} />}
      {route.journals && <LandingJournals data={route.journals} />}
      {route.papers && <LandingPapers data={route.papers} />}
    </div>
  )
}
```

In `ancient-nerds-map/src/seo/registry.tsx` add the import and the entry:

```ts
import LandingLive from '../pages/LandingLive'
```

```ts
  articleIndex: { Component: ArticlesPage, meta: meta.articleIndexMeta },
  landing: { Component: LandingLive, meta: meta.landingMeta },
```

`ancient-nerds-map/src/styles/landing-live.css`:

```css
/* Landing live sections (Stories / Journal / Papers) — lead + rail language.
   Tokens from tokens.css; section widths match .landing-section. */
.landing-live { max-width: 1200px; margin: 0 auto; padding: 0 24px; font-family: var(--font-mono, 'JetBrains Mono', monospace); }
.ll-section { padding: 56px 0 24px; border-top: 1px solid var(--border-accent); }
.ll-section:first-child { border-top: 0; }

.ll-head { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
.ll-fig { margin: 0; font-family: var(--font-mono, monospace); font-size: 14px; font-weight: 600; letter-spacing: 0.04em; color: var(--accent-primary); }
.ll-fig b { color: var(--text-primary); font-weight: 600; }
.ll-status { font-size: 12px; color: var(--text-muted); }

.ll-two { display: grid; grid-template-columns: 1.25fr 1fr; gap: 16px; }
.ll-lead, .ll-row { color: inherit; text-decoration: none; }
.ll-lead { display: flex; flex-direction: column; border: 1px solid var(--border-accent); background: rgba(0, 15, 20, 0.6); }
.ll-lead:hover .ll-title, .ll-row:hover .ll-row-title { color: var(--accent-primary); }
.ll-img { display: block; position: relative; overflow: hidden; background: #0a1a14; }
.ll-img-16x9 { aspect-ratio: 16 / 9; }
.ll-img-21x9 { aspect-ratio: 21 / 9; }
.ll-img img { width: 100%; height: 100%; object-fit: cover; display: block; filter: saturate(0.75) contrast(1.05); transition: transform 0.4s ease; }
.ll-img::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0, 40, 25, 0.15), rgba(0, 10, 6, 0.55)); pointer-events: none; }
@media (prefers-reduced-motion: no-preference) { .ll-lead:hover .ll-img img { transform: scale(1.03); } }
.ll-body { display: flex; flex-direction: column; gap: 6px; padding: 14px 16px 16px; }
.ll-meta-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ll-title { font-family: var(--font-heading); font-size: 17px; letter-spacing: 0.02em; line-height: 1.3; color: var(--text-primary); }
.ll-p { font-size: 13px; line-height: 1.5; color: var(--text-secondary); }
.ll-meta { font-size: 11px; color: var(--text-muted); }
.ll-meta b { color: var(--text-secondary); font-weight: 400; }
.ll-site { color: var(--accent-secondary); }

.ll-badge { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; padding: 1px 6px; border: 1px solid currentColor; border-radius: 3px; color: var(--text-muted); }
.ll-cat-artifact { color: #ff9830; }
.ll-cat-bioarchaeology { color: #ff6b7a; }
.ll-cat-underwater, .ll-cat-journal { color: var(--accent-secondary); }
.ll-cat-theory { color: #c9a3ff; }
.ll-cat-architecture, .ll-cat-paper { color: var(--accent-primary); }
.ll-sig { font-size: 10px; letter-spacing: 0.05em; color: var(--text-muted); display: inline-flex; align-items: center; gap: 4px; }
.ll-sig b { color: var(--accent-primary); }
.ll-meter { display: inline-block; width: 46px; height: 5px; background: rgba(255, 255, 255, 0.08); }
.ll-meter i { display: block; height: 100%; background: var(--accent-primary); box-shadow: 0 0 4px var(--accent-glow-20); }

.ll-rail { display: flex; flex-direction: column; border: 1px solid var(--border-accent); background: rgba(0, 15, 20, 0.6); }
.ll-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--border-accent); }
.ll-row:last-child { border-bottom: 0; }
.ll-row-thumb { grid-template-columns: 96px 1fr; }
.ll-row-title { display: block; font-size: 13px; font-weight: 600; line-height: 1.35; color: var(--text-primary); }
.ll-row .ll-meta { display: block; margin-top: 3px; }
.ll-arrow { color: var(--text-muted); }

.ll-toc { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 4px; }
.ll-toc span { font-size: 11px; color: var(--text-secondary); border: 1px solid var(--border-accent); padding: 1px 7px; border-radius: 3px; }
.ll-toc span::before { content: '§ '; color: var(--text-muted); }
.ll-evidence { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 6px; }
.ll-evidence span { border: 1px solid var(--border-accent); padding: 6px 8px; display: flex; flex-direction: column; }
.ll-evidence i { font-style: normal; font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; }
.ll-evidence b { font-size: 14px; color: var(--text-primary); }

.ll-theo { display: flex; justify-content: space-between; gap: 12px; margin-top: 12px; padding: 8px 12px; font-size: 12px; color: #ff9830; border: 1px dashed rgba(255, 152, 48, 0.45); text-decoration: none; }
.ll-theo b { color: var(--text-primary); }
.ll-pulse { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #ff9830; box-shadow: 0 0 6px #ff9830; margin-right: 6px; }
@media (prefers-reduced-motion: no-preference) { .ll-pulse { animation: ll-pulse 1.6s infinite; } }
@keyframes ll-pulse { 50% { opacity: 0.35; } }

.ll-foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 12px; font-size: 12px; color: var(--text-muted); }
.ll-foot a { color: var(--accent-secondary); text-decoration: none; }
.ll-foot a:hover { text-decoration: underline; }

.ll-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.ll-chip { border: 1px solid var(--border-accent); background: transparent; color: var(--text-muted); font: inherit; font-size: 12px; padding: 3px 10px; border-radius: 99px; cursor: pointer; }
.ll-chip[aria-pressed='true'] { color: #031; background: var(--accent-primary); border-color: var(--accent-primary); font-weight: 600; }
.ll-more { margin-top: 10px; width: 100%; border: 1px solid var(--border-accent); background: transparent; color: var(--accent-secondary); font: inherit; font-size: 12px; padding: 8px; cursor: pointer; }
.ll-more:disabled { opacity: 0.5; cursor: default; }
.ll-error { color: #ff6b7a; }

@media (max-width: 900px) {
  .ll-two { grid-template-columns: 1fr; }
  .ll-evidence { grid-template-columns: repeat(2, 1fr); }
  .ll-chips { flex-wrap: nowrap; overflow-x: auto; padding-bottom: 4px; }
}
```

- [ ] **Step 9: Run the tests**

Run: `cd ancient-nerds-map && npx vitest run src/landing src/seo && npx tsc --noEmit`
Expected: all PASS — including `render.test.tsx` ("rendert landing ohne Browser-APIs") and `entryServer.test.tsx` (one title, one canonical) which iterate `FIXTURES`; `tsc` clean.

- [ ] **Step 10: Commit**

```bash
git add ancient-nerds-map/src/landing ancient-nerds-map/src/pages/LandingLive.tsx ancient-nerds-map/src/styles/landing-live.css ancient-nerds-map/src/seo
git commit -m "feat(landing): LandingLive sections render from the payload"
```

---

### Task 3: Stories interaction — chips, load more, feed client

**Files:**
- Create: `ancient-nerds-map/src/landing/feedClient.ts`
- Create: `ancient-nerds-map/src/landing/__tests__/feedClient.test.ts`
- Modify: `ancient-nerds-map/src/landing/LandingStories.tsx`

- [ ] **Step 1: Write the failing mapping tests**

```ts
// ancient-nerds-map/src/landing/__tests__/feedClient.test.ts
import { describe, expect, it } from 'vitest'

import { feedItemToTeaser, firstSentence, pickLeadAndRail, type FeedItem } from '../feedClient'

const item = (over: Partial<FeedItem>): FeedItem => ({
  id: 1,
  headline: 'Headline',
  post_text: 'First sentence here. Second sentence. https://example.org/src',
  screenshot_url: '/data/news/screenshots/x.webp',
  news_category: 'artifact',
  significance: 5,
  created_at: '2026-09-08T19:33:29',
  site_id: null,
  site_name: null,
  site_country: null,
  web_sources: [{ url: 'a' }, { url: 'b' }],
  video: { channel_name: 'Michael Button' },
  ...over,
})

describe('firstSentence', () => {
  it('takes the first sentence and drops trailing links', () => {
    expect(firstSentence('One. Two. https://x.y')).toBe('One.')
    expect(firstSentence('No period at all https://x.y')).toBe('No period at all')
  })
  it('cuts overlong sentences at 180 characters on a word boundary', () => {
    const long = `${'word '.repeat(50)}end.`
    const out = firstSentence(long)
    expect(out.length).toBeLessThanOrEqual(181)
    expect(out.endsWith('…')).toBe(true)
  })
})

describe('feedItemToTeaser', () => {
  it('maps the feed row to the payload shape', () => {
    const t = feedItemToTeaser(item({}))
    expect(t).toEqual({
      id: 1,
      headline: 'Headline',
      summary: 'First sentence here.',
      screenshot_url: '/data/news/screenshots/x.webp',
      category: 'artifact',
      significance: 5,
      created_at: '2026-09-08T19:33:29',
      channel: 'Michael Button',
      sources: 2,
      path: '/news-archive/headline-1',
      site: null,
    })
  })
  it('builds the site chip only with id, name and country', () => {
    const t = feedItemToTeaser(item({ site_id: 'da3ff939-2402-4bf8-a476-e7725c81c8d5', site_name: 'Stirling Castle', site_country: 'United Kingdom' }))
    expect(t.site).toEqual({ name: 'Stirling Castle', country: 'United Kingdom', path: '/sites/united-kingdom/stirling-castle-da3ff939' })
    expect(feedItemToTeaser(item({ site_id: 'x', site_name: 'Y', site_country: null })).site).toBeNull()
  })
})

describe('pickLeadAndRail', () => {
  it('lead = highest significance, ties to the newer, rail keeps feed order without the lead', () => {
    const rows = [
      feedItemToTeaser(item({ id: 3, significance: 4, created_at: '2026-09-08T10:00:00' })),
      feedItemToTeaser(item({ id: 2, significance: 9, created_at: '2026-09-07T10:00:00' })),
      feedItemToTeaser(item({ id: 1, significance: 9, created_at: '2026-09-06T10:00:00' })),
    ]
    const { lead, rail } = pickLeadAndRail(rows)
    expect(lead.id).toBe(2)
    expect(rail.map(r => r.id)).toEqual([3, 1])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ancient-nerds-map && npx vitest run src/landing/__tests__/feedClient.test.ts`
Expected: FAIL — module `../feedClient` not found.

- [ ] **Step 3: Write `feedClient.ts`**

```ts
// ancient-nerds-map/src/landing/feedClient.ts
/**
 * Client side of the Stories section: fetches /api/news/feed for the
 * category chips and "load more" and maps feed rows to the StoryTeaser
 * shape the server already used for the first paint. The mapping mirrors
 * api/routes/landing_html.py::story_teaser — same slug helpers, same
 * first-sentence rule — so a refetched card looks exactly like an SSR one.
 */
import { splitPostText } from '../components/news/postText'
import { sitePath, storyPath } from '../seo/meta'
import type { StoryTeaser } from '../types/anRoute'

export interface FeedItem {
  id: number
  headline: string
  post_text: string | null
  screenshot_url: string | null
  news_category: string | null
  significance: number | null
  created_at: string
  site_id: string | null
  site_name: string | null
  site_country: string | null
  web_sources: unknown[] | null
  video: { channel_name: string }
}

interface FeedResponse {
  items: FeedItem[]
  has_more: boolean
}

const MAX_SUMMARY = 180

export function firstSentence(postText: string | null): string {
  if (!postText) return ''
  const body = splitPostText(postText).paragraphs[0] ?? ''
  const match = body.match(/^.*?[.!?](?=\s|$)/)
  const sentence = (match ? match[0] : body).trim()
  if (sentence.length <= MAX_SUMMARY) return sentence
  const cut = sentence.slice(0, MAX_SUMMARY)
  return `${cut.slice(0, cut.lastIndexOf(' '))}…`
}

export function feedItemToTeaser(it: FeedItem): StoryTeaser {
  const site =
    it.site_id && it.site_name && it.site_country
      ? { name: it.site_name, country: it.site_country, path: sitePath(it.site_country, it.site_name, it.site_id) }
      : null
  return {
    id: it.id,
    headline: it.headline,
    summary: firstSentence(it.post_text),
    screenshot_url: it.screenshot_url,
    category: it.news_category,
    significance: it.significance,
    created_at: it.created_at,
    channel: it.video.channel_name,
    sources: it.web_sources?.length ?? 0,
    path: storyPath(it.headline, it.id),
    site,
  }
}

/** Lead = highest significance (ties: newer); rail = the rest in feed order. */
export function pickLeadAndRail(rows: StoryTeaser[]): { lead: StoryTeaser; rail: StoryTeaser[] } {
  const lead = rows.reduce((best, r) => {
    const s = r.significance ?? 0
    const b = best.significance ?? 0
    if (s > b) return r
    if (s === b && r.created_at > best.created_at) return r
    return best
  })
  return { lead, rail: rows.filter(r => r.id !== lead.id) }
}

export async function fetchFeed(params: { category: string | null; page: number; pageSize: number }): Promise<{ items: StoryTeaser[]; hasMore: boolean }> {
  const q = new URLSearchParams({ page: String(params.page), page_size: String(params.pageSize) })
  if (params.category) q.set('news_category', params.category)
  const res = await fetch(`/api/news/feed?${q}`)
  if (!res.ok) throw new Error(`feed ${res.status}`)
  const data = (await res.json()) as FeedResponse
  return { items: data.items.map(feedItemToTeaser), hasMore: data.has_more }
}
```

- [ ] **Step 4: Run the mapping tests**

Run: `cd ancient-nerds-map && npx vitest run src/landing/__tests__/feedClient.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Wire chips and load-more into `LandingStories.tsx`**

Replace the `LandingStories` default export (keep `StoryLead`, `StoryRow`, `Badge`, `Meter`, `PLACEHOLDER` from Task 2) and add the imports:

```tsx
import { useState } from 'react'

import { fetchFeed, pickLeadAndRail } from './feedClient'
```

```tsx
const PAGE = 7
const RAIL = 6
const MAX_LOADS = 2

export default function LandingStories({ initial, total }: Props) {
  const [category, setCategory] = useState<string | null>(null)
  const [lead, setLead] = useState(initial.lead)
  const [rail, setRail] = useState(initial.rail)
  const [loads, setLoads] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function applyChip(next: string | null) {
    if (next === category || busy) return
    setError(null)
    if (next === null) {
      setCategory(null)
      setLead(initial.lead)
      setRail(initial.rail)
      setLoads(0)
      return
    }
    setBusy(true)
    try {
      const { items } = await fetchFeed({ category: next, page: 1, pageSize: PAGE })
      if (items.length === 0) {
        setError(`no ${next} stories yet`)
        return
      }
      const picked = pickLeadAndRail(items)
      setCategory(next)
      setLead(picked.lead)
      setRail(picked.rail.slice(0, RAIL))
      setLoads(0)
    } catch {
      setError('feed unavailable')
    } finally {
      setBusy(false)
    }
  }

  async function loadMore() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const shown = new Set([lead.id, ...rail.map(r => r.id)])
      const { items } = await fetchFeed({ category, page: loads + 2, pageSize: RAIL })
      setRail(prev => [...prev, ...items.filter(i => !shown.has(i.id))])
      setLoads(n => n + 1)
    } catch {
      setError('feed unavailable')
    } finally {
      setBusy(false)
    }
  }

  const chips: (string | null)[] = [null, ...initial.categories]
  return (
    <section className="ll-section" id="stories-live">
      <SectionHead fig={1} name="stories, live" status={`${total.toLocaleString('en-US')} stories · newest first`} />
      <div className="ll-chips" role="group" aria-label="story categories">
        {chips.map(c => (
          <button key={c ?? 'all'} type="button" className="ll-chip" aria-pressed={c === category} onClick={() => applyChip(c)}>
            {c ?? 'all'}
          </button>
        ))}
        {error && <span className="ll-error ll-meta">{error}</span>}
      </div>
      <div className="ll-two">
        <StoryLead story={lead} />
        <div className="ll-rail">
          {rail.map(s => (
            <StoryRow key={s.id} story={s} />
          ))}
        </div>
      </div>
      {loads < MAX_LOADS ? (
        <button type="button" className="ll-more" onClick={loadMore} disabled={busy}>
          {busy ? 'loading…' : 'load more'}
        </button>
      ) : null}
      <div className="ll-foot">
        <span>lead = highest significance of the last 48h · rail = newest</span>
        <a href="/news.html">all stories →</a>
      </div>
    </section>
  )
}
```

Why the chips are `<button aria-pressed>`: they are real controls, not links, and the server renders them identically (no `onClick` attribute lands in HTML), so hydration matches.

- [ ] **Step 6: Run all landing tests and the type check**

Run: `cd ancient-nerds-map && npx vitest run src/landing src/seo && npx tsc --noEmit`
Expected: PASS; the `landingLive.test.tsx` assertions still hold (chips render as buttons, no ` ago`).

- [ ] **Step 7: Commit**

```bash
git add ancient-nerds-map/src/landing
git commit -m "feat(landing): stories chips and load-more through the feed API"
```

---

### Task 4: Client entry, `index.html` and Vite config

**Files:**
- Create: `ancient-nerds-map/src/landingMain.tsx`
- Modify: `ancient-nerds-map/index.html`
- Modify: `ancient-nerds-map/vite.config.ts:178` (manifest) and the `navigateFallbackDenylist` block (~line 196)

- [ ] **Step 1: Create the hydration entry**

```tsx
// ancient-nerds-map/src/landingMain.tsx
/**
 * Entry for the homepage live sections. The API (GET /home) renders
 * LandingLive into #root through the SSR sidecar and injects the payload;
 * this entry adopts that markup. Without a payload — the static index.html
 * nginx serves while the API restarts — there is nothing to hydrate and
 * nothing to do. The hero and the screenshot sections never touch React.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import { SeoRoute } from './seo/registry'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'

const route = readInjectedRoute()
const root = document.getElementById('root')
if (route?.type === 'landing' && root) {
  ReactDOM.hydrateRoot(
    root,
    <React.StrictMode>
      <RouteProvider value={route}>
        <AuthProvider>
          <SeoRoute />
        </AuthProvider>
      </RouteProvider>
    </React.StrictMode>,
  )
}
```

`AuthProvider` matches `entry-server.tsx`'s tree, so the client and server trees are identical. `landing.css` and `index.css` are already loaded by `index.html`'s existing `<link>`/module tags; `LandingLive` imports its own `landing-live.css`.

- [ ] **Step 2: Edit `index.html` — head counts**

Replace every stale count (lines 8, 9, 10, 27, 38, 48, 73, 89, 155):

| Line | Old | New |
|---|---|---|
| 8, 9 | `Explore 750K+ Ancient Sites` | `Explore 1.7M+ Ancient Sites` |
| 10, 155 | `Explore over 750,000 archaeological sites` | `Explore over 1.7 million archaeological sites` |
| 27, 38 | `Explore 750K+ archaeological sites` | `Explore 1.7M+ archaeological sites` |
| 48 | `featuring over 750,000 ancient sites` | `featuring over 1.7 million ancient sites` |
| 73 | `mapping 750,000+ ancient sites` | `mapping 1.7 million+ ancient sites` |
| 89 | `Aggregated database of 750,000+ archaeological sites` | `Aggregated database of 1.7 million+ archaeological sites` |
| 218 | `FILTER 750,000+ SITES` | `FILTER 1.7 MILLION+ SITES` |

Run afterwards: `grep -n "750" ancient-nerds-map/index.html` — expected: no output.

- [ ] **Step 3: Edit `index.html` — hero H1, stats, intro paragraph, `#root`**

Replace the block from the `<h1 class="hero-title">` line through the closing `</div>` of `.hero-stats` (currently lines 170–192; keep the logo `<img>` above it and the `cta-primary` link below it) with:

```html
        <p class="hero-title">ANCIENT NERDS</p>
        <p class="hero-subtitle hero-bg-fade">RESEARCH PLATFORM</p>
        <h1 class="hero-tagline hero-bg-fade">The interactive map of <span data-stat="sites-long">1.7 million</span> archaeological sites, explored through data, maps and&nbsp;AI</h1>

        <div class="hero-stats">
          <div class="hero-stat">
            <div class="hero-stat-value" data-stat="sites">1.7M+</div>
            <div class="hero-stat-label">Sites</div>
          </div>
          <div class="hero-stat">
            <div class="hero-stat-value" data-stat="countries">90+</div>
            <div class="hero-stat-label">Countries</div>
          </div>
          <div class="hero-stat">
            <div class="hero-stat-value">30+</div>
            <div class="hero-stat-label">Empires</div>
          </div>
          <div class="hero-stat">
            <div class="hero-stat-value">20+</div>
            <div class="hero-stat-label">Sources</div>
          </div>
        </div>
```

`.hero-title` and `.hero-tagline` are class selectors in `landing.css` (lines 154, 183), so swapping the elements keeps the look. Check `landing.css` for `h1.hero-title` or `p.hero-tagline` element-qualified selectors: `grep -n "h1\|p\.hero" ancient-nerds-map/src/styles/landing.css` — if any match, change them to the class-only form.

Directly after the closing `</section>` of the hero (line 197, before the `<!-- ═══════════ THE GLOBE ═══════════ -->` comment) insert:

```html
    <!-- ═══════════ INTRO + LIVE SECTIONS ═══════════ -->
    <section class="landing-section landing-intro">
      <p class="landing-intro-text">Ancient Nerds is a free research platform for archaeology and ancient history. A <a href="/globe.html">3D globe</a> maps 1.7 million sites from more than 20 open databases, 5,000 of them curated in depth. <a href="/lyra.html">Lyra</a> reads the latest archaeology videos and turns them into sourced <a href="/news.html">stories</a>, which become a <a href="/articles.html">journal</a> every week. <a href="/theo.html">Theo</a>, our research agent, writes long-form <a href="/research/">papers</a> with thousands of citations, published under CC BY 4.0.</p>
    </section>
    <div id="root"></div>
```

`render_app_shell` requires the exact string `<div id="root"></div>` — no attributes, no whitespace inside.

Add to `ancient-nerds-map/src/styles/landing.css` (after `.section-desc`):

```css
.landing-intro { padding-top: 48px; padding-bottom: 8px; }
.landing-intro-text { max-width: 70ch; margin: 0 auto; font-size: 1.05rem; line-height: 1.75; color: var(--text-secondary); text-wrap: pretty; }
.landing-intro-text a { color: var(--accent-secondary); text-decoration: none; }
.landing-intro-text a:hover { text-decoration: underline; }
```

- [ ] **Step 4: Edit `index.html` — remove the replaced sections, widen Radar, add the entry script**

Delete the `split-card` block for "ARCHAEOLOGY STORIES" (the first `<div class="split-card">…</div>` inside the section starting at line 283) and turn the remaining Radar card into a feature row:

```html
    <section class="landing-section" id="radar-section">
      <div class="feature-row">
        <div class="animate-in">
          <h2 class="section-label">DISCOVERY RADAR</h2>
          <p class="section-desc">Track newly mentioned sites from video content. 1.7 million known sites cross-referenced in&nbsp;real-time.</p>
          <a href="/radar.html" class="cta-secondary">OPEN RADAR</a>
        </div>
        <div class="animate-in delay-2">
          <img src="/landing/radar-map.webp" alt="Radar discovery map" class="feature-image-main" data-lightbox loading="lazy" decoding="async" width="1276" height="967" />
          <div class="thumbnail-strip">
            <img src="/landing/radar-cards.webp" alt="Radar site cards" data-lightbox loading="lazy" decoding="async" width="1280" height="594" />
          </div>
        </div>
      </div>
    </section>
```

Delete the whole `<section class="landing-section" id="articles-section">…</section>` (lines 340–352) and the `#articles-section .feature-image-main` selector in `landing.css` line 361 (leave the other two selectors of that rule).

Add the entry script next to the existing inline module script (line 672):

```html
    <script type="module" src="/src/landingMain.tsx"></script>
```

- [ ] **Step 5: Vite config**

`vite.config.ts` line 178: `description: 'Interactive 3D globe of 1.7M+ archaeological sites worldwide',`

In `navigateFallbackDenylist` add as the first entry, with the comment:

```ts
        navigateFallbackDenylist: [
          // The homepage is server-rendered (GET /home via nginx) — the
          // precached index.html must never answer a navigation to "/".
          /^\/$/,
          /^\/api\//,
```

- [ ] **Step 6: Build and inspect**

Run: `cd ancient-nerds-map && npm run build 2>&1 | tail -15 && ls -l dist/assets/landing-*.js && grep -c 'id="root"' dist/index.html && grep -c "landing-live" dist/assets/*.css`
Expected: build OK; a `landing-*.js` chunk of roughly 15–40 kB; exactly one `id="root"`; the live CSS present. Then `npm run build:ssr` — expected OK (the sidecar bundle now contains `LandingLive`).

Run: `npx vitest run && npx knip --no-progress --include files,dependencies,devDependencies`
Expected: PASS, knip clean (`landingMain.tsx` is referenced from `index.html`, `LandingLive` from the registry).

- [ ] **Step 7: Commit**

```bash
git add ancient-nerds-map/index.html ancient-nerds-map/src/landingMain.tsx ancient-nerds-map/src/styles/landing.css ancient-nerds-map/vite.config.ts
git commit -m "feat(landing): keyword h1, intro paragraph, #root and hydration entry in index.html"
```

---

### Task 5: `site_stats` service (shared by `/api/stats` and the landing route)

**Files:**
- Create: `api/services/site_stats.py`
- Modify: `api/main.py:824-855` (`stats()` delegates)
- Create: `tests/api/test_site_stats.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_site_stats.py
"""get_site_stats() is the one place that counts unified_sites; /api/stats and
the landing route both read it. DB-less: the session is a fake."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from api.services.site_stats import get_site_stats


class FakeResult:
    """scalar() for COUNT queries, iteration for the GROUP BY query."""

    def __init__(self, rows):
        self.rows = rows

    def scalar(self):
        return self.rows[0][0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    def __init__(self, results):
        self._results = list(results)

    def execute(self, *_args, **_kwargs):
        return FakeResult(self._results.pop(0))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_get_site_stats_counts_total_by_source_and_curated_countries():
    total = [(1_759_673,)]
    by_source = [SimpleNamespace(source_id="list_inscriptions", count=509_181), SimpleNamespace(source_id="ancient_nerds", count=5_004)]
    countries = [(98,)]
    with (
        patch("api.services.site_stats.cache_get", return_value=None),
        patch("api.services.site_stats.cache_set") as cache_set,
        patch("api.services.site_stats.get_session", return_value=FakeSession([total, by_source, countries])),
    ):
        stats = get_site_stats()

    assert stats == {
        "total_sites": 1_759_673,
        "by_source": {"list_inscriptions": 509_181, "ancient_nerds": 5_004},
        "curated_countries": 98,
    }
    assert cache_set.call_args.kwargs["ttl"] == 300


def test_get_site_stats_returns_the_cached_dict_untouched():
    with patch("api.services.site_stats.cache_get", return_value={"total_sites": 1}):
        assert get_site_stats() == {"total_sites": 1}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/api/test_site_stats.py -v`
Expected: FAIL — `api.services.site_stats` does not exist.

- [ ] **Step 3: Create the service**

```python
# api/services/site_stats.py
# SPDX-License-Identifier: AGPL-3.0-only
"""Site counts shared by /api/stats and the homepage (api/routes/landing_html.py).

One query set, one 5-minute cache. `curated_countries` is the number of
countries with ancient_nerds sites — the same set the /sites/{country}
hubs are built from, so the hero counter and the hub list agree.
"""

from __future__ import annotations

from sqlalchemy import text

from api.cache import cache_get, cache_set
from pipeline.database import get_session

CACHE_KEY = "api:stats"


def get_site_stats() -> dict:
    cached = cache_get(CACHE_KEY)
    if cached:
        return cached
    with get_session() as session:
        total_sites = session.execute(text("SELECT COUNT(*) FROM unified_sites")).scalar()
        by_source = {
            row.source_id: row.count
            for row in session.execute(
                text(
                    """
                    SELECT source_id, COUNT(*) AS count
                    FROM unified_sites
                    GROUP BY source_id
                    ORDER BY count DESC
                    """
                )
            )
        }
        curated_countries = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT country) FROM unified_sites
                WHERE source_id = 'ancient_nerds' AND country IS NOT NULL AND country <> ''
                """
            )
        ).scalar()
    response = {
        "total_sites": total_sites,
        "by_source": by_source,
        "curated_countries": curated_countries or 0,
    }
    cache_set(CACHE_KEY, response, ttl=300)
    return response
```

- [ ] **Step 4: Make `/api/stats` delegate**

In `api/main.py` replace the body of `stats()` (lines 824–855) with:

```python
@app.get("/api/stats")
async def stats():
    """Get database statistics (cached for 5 minutes)."""
    return get_site_stats()
```

and add near the other `api.` imports: `from api.services.site_stats import get_site_stats`. Remove the now-unused local imports inside the old body (`text`, `get_session`) — they were function-local, so nothing else changes.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/api/test_site_stats.py -v && ruff check api/services/site_stats.py api/main.py && vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80 | grep -i stats`
Expected: 2 PASS, ruff clean, vulture silent about `stats`.

- [ ] **Step 6: Commit**

```bash
git add api/services/site_stats.py api/main.py tests/api/test_site_stats.py
git commit -m "refactor(api): site stats service shared by /api/stats and the homepage"
```

---

### Task 6: Landing payload builders (pure functions) with tests

**Files:**
- Create: `api/routes/landing_html.py` (builders only in this task; the route comes in Task 7)
- Create: `tests/api/test_landing_html.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_landing_html.py
"""Payload builders for GET /home (landing-live sections, 2026-09-09).

DB-less: rows are SimpleNamespaces. The field names asserted here are the
contract anRoute.ts::LandingRoute declares.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from api.routes.landing_html import (
    apply_stats,
    first_sentence,
    journal_teaser,
    paper_teaser,
    pick_lead_and_rail,
    reading_minutes,
    sites_compact,
    sites_long,
    story_teaser,
)

NOW = datetime(2026, 9, 9, 12, 0, 0)


def item(id_, *, sig, hours_ago, category="artifact", site=None, post="One sentence. Two. https://x.y"):
    video = SimpleNamespace(channel=SimpleNamespace(name="Inside Archaeology"))
    return SimpleNamespace(
        id=id_,
        headline=f"Headline {id_}",
        post_text=post,
        screenshot_url=f"/data/news/screenshots/{id_}.webp",
        news_category=category,
        significance=sig,
        created_at=NOW - timedelta(hours=hours_ago),
        web_sources=[{"url": "a"}, {"url": "b"}],
        video=video,
        site=site,
    )


def test_first_sentence_drops_trailing_links_and_caps_length():
    assert first_sentence("One sentence. Two. https://x.y") == "One sentence."
    assert first_sentence("No period https://x.y") == "No period"
    assert first_sentence(None) == ""
    long = "word " * 50 + "end."
    out = first_sentence(long)
    assert len(out) <= 181 and out.endswith("…")


def test_story_teaser_maps_row_and_site():
    site = SimpleNamespace(id="da3ff939-2402-4bf8-a476-e7725c81c8d5", name="Stirling Castle", country="United Kingdom")
    t = story_teaser(item(7, sig=6, hours_ago=3, site=site))
    assert t == {
        "id": 7,
        "headline": "Headline 7",
        "summary": "One sentence.",
        "screenshot_url": "/data/news/screenshots/7.webp",
        "category": "artifact",
        "significance": 6,
        "created_at": (NOW - timedelta(hours=3)).isoformat(),
        "channel": "Inside Archaeology",
        "sources": 2,
        "path": "/news-archive/headline-7-7",
        "site": {"name": "Stirling Castle", "country": "United Kingdom", "path": "/sites/united-kingdom/stirling-castle-da3ff939"},
    }
    assert story_teaser(item(8, sig=None, hours_ago=1))["site"] is None


def test_pick_lead_prefers_the_48h_window_and_never_duplicates():
    recent = [item(i, sig=3, hours_ago=i) for i in range(1, 8)]  # ids 1..7, newest first
    lead_48h = item(5, sig=9, hours_ago=5)
    lead, rail = pick_lead_and_rail(recent, lead_48h)
    assert lead.id == 5
    assert [r.id for r in rail] == [1, 2, 3, 4, 6, 7]


def test_pick_lead_falls_back_to_the_best_of_the_recent_seven():
    recent = [item(1, sig=2, hours_ago=60), item(2, sig=8, hours_ago=61), item(3, sig=8, hours_ago=62)]
    lead, rail = pick_lead_and_rail(recent, None)
    assert lead.id == 2  # tie on 8 → the newer one
    assert [r.id for r in rail] == [1, 3]


def test_pick_lead_keeps_six_rows_when_the_lead_is_outside_the_seven():
    recent = [item(i, sig=3, hours_ago=i) for i in range(1, 8)]
    lead, rail = pick_lead_and_rail(recent, item(99, sig=9, hours_ago=40))
    assert lead.id == 99
    assert len(rail) == 6 and [r.id for r in rail] == [1, 2, 3, 4, 5, 6]


def test_reading_minutes_rounds_up_at_238_wpm():
    assert reading_minutes(2762) == 12
    assert reading_minutes(238) == 1
    assert reading_minutes(0) == 0


def test_journal_teaser_counts_words_sections_sources_and_first_image():
    content = (
        "# Title\n\nIntro text here.\n\n## Artifact Discoveries\n\nText with a [link](https://a.b) "
        "and ![img](/data/news/screenshots/nMxEoIrMwX8_367.webp).\n\n## In Brief\n\nmore\n\n"
        "## Sources\n\n1. https://c.d\n\n## Videos\n\nV1. https://youtu.be/x\n"
    )
    row = SimpleNamespace(
        id=74,
        title="Week of August 31: Wooden Structure, and More",
        summary="Summary.",
        content=content,
        week_start=datetime(2026, 8, 31),
        week_end=datetime(2026, 9, 6, 23, 59, 59),
        published_at=datetime(2026, 9, 7, 4, 20, 43),
    )
    t = journal_teaser(row)
    assert t["sections"] == ["Artifact Discoveries", "In Brief"]
    assert t["sources"] == 3
    assert t["image_url"] == "/data/news/screenshots/nMxEoIrMwX8_367.webp"
    assert t["path"] == "/articles/week-of-august-31-wooden-structure-and-more"
    assert t["words"] == len(content.split()) and t["minutes"] == reading_minutes(t["words"])
    assert t["week_start"] == "2026-08-31T00:00:00" and t["published_at"] == "2026-09-07T04:20:43"


def test_paper_teaser_uses_the_public_api_mapping():
    row = SimpleNamespace(
        id="4bf8", slug="the-egyptian-hard-stone-precision-debate", question="Q?", published_by=None,
        published_at=datetime(2026, 8, 31, 22, 7, 6), sites_found=2748,
        title="The Egyptian Hard-Stone Precision Debate", card_description="Summary.",
        score="98", badge="Unverified", word_count="6466", hero_src="/data/research-images/x.jpg",
    )
    t = paper_teaser(row)
    assert t == {
        "slug": "the-egyptian-hard-stone-precision-debate",
        "title": "The Egyptian Hard-Stone Precision Debate",
        "summary": "Summary.",
        "published_at": "2026-08-31T22:07:06",
        "words": 6466,
        "minutes": 28,
        "sources_analyzed": 2748,
        "quality_score": 98,
        "hero_image_url": "https://ancientnerds.com/data/research-images/x.jpg",
        "path": "/research/the-egyptian-hard-stone-precision-debate",
    }


def test_number_formats():
    assert sites_compact(1_759_673) == "1.76M"
    assert sites_compact(999_999) == "999K"
    assert sites_long(1_759_673) == "1.7 million"


def test_apply_stats_replaces_only_marked_values():
    html = (
        '<div class="hero-stat-value" data-stat="sites">1.7M+</div>'
        '<span data-stat="sites-long">1.7 million</span>'
        '<div class="hero-stat-value" data-stat="countries">90+</div>'
        '<div class="hero-stat-value">30+</div>'
    )
    out = apply_stats(html, {"total_sites": 1_759_673, "curated_countries": 98})
    assert 'data-stat="sites">1.76M<' in out
    assert 'data-stat="sites-long">1.7 million<' in out
    assert 'data-stat="countries">98<' in out
    assert "<div class=\"hero-stat-value\">30+</div>" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/api/test_landing_html.py -v`
Expected: FAIL — `api.routes.landing_html` does not exist.

- [ ] **Step 3: Write the builders**

```python
# api/routes/landing_html.py
# SPDX-License-Identifier: AGPL-3.0-only
"""
GET /home — the homepage with live Stories / Journal / Papers sections.

nginx proxies "/" here (ancientnerds-nginx-config, location = /). The route
builds a {type: "landing"} payload from the DB, renders it through the SSR
sidecar into index.html's #root (api/seo_shell.py, same path as every other
indexed page), substitutes the live counts into the hero and caches the
document for 300 s. When the API or the sidecar is down nginx serves the
static index.html instead — the page stays up, the three sections are empty.

Everything above `fetch_landing_data` is a pure function of rows and is
what tests/api/test_landing_html.py covers. Spec:
docs/superpowers/specs/2026-09-09-landing-live-sections-design.md
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta

from api.routes.public_v1 import paper_summary_kwargs
from pipeline.article_html_renderer import slugify, story_slug
from pipeline.sites_html_renderer import site_path

MAX_SUMMARY = 180
WORDS_PER_MINUTE = 238
LEAD_WINDOW = timedelta(hours=48)
RAIL_ROWS = 6
RECENT_ROWS = 7
APPENDIX_SECTIONS = {"sources", "videos"}

_TRAILING_URL = re.compile(r"\s*https?://\S+\s*$")
_SENTENCE = re.compile(r"^.*?[.!?](?=\s|$)")
_HEADING = re.compile(r"^##+\s+(.+?)\s*$", re.MULTILINE)
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
_LINK = re.compile(r"https?://")


def first_sentence(post_text: str | None) -> str:
    """First sentence of the story post, trailing source links removed, ≤180 chars."""
    if not post_text:
        return ""
    body = post_text.strip().split("\n", 1)[0]
    while _TRAILING_URL.search(body):
        body = _TRAILING_URL.sub("", body)
    match = _SENTENCE.match(body)
    sentence = (match.group(0) if match else body).strip()
    if len(sentence) <= MAX_SUMMARY:
        return sentence
    cut = sentence[:MAX_SUMMARY]
    return cut[: cut.rfind(" ")] + "…"


def reading_minutes(words: int) -> int:
    return math.ceil(words / WORDS_PER_MINUTE) if words else 0


def story_teaser(row) -> dict:
    """NewsItem row (video+channel and site joined) → StoryTeaser."""
    site = None
    if row.site is not None and row.site.country:
        site = {
            "name": row.site.name,
            "country": row.site.country,
            "path": site_path(row.site.country, row.site.name, str(row.site.id)),
        }
    return {
        "id": row.id,
        "headline": row.headline,
        "summary": first_sentence(row.post_text),
        "screenshot_url": row.screenshot_url,
        "category": row.news_category,
        "significance": row.significance,
        "created_at": row.created_at.isoformat(),
        "channel": row.video.channel.name,
        "sources": len(row.web_sources or []),
        "path": f"/news-archive/{story_slug(row.headline, row.id)}",
        "site": site,
    }


def pick_lead_and_rail(recent: list, lead_48h) -> tuple:
    """Lead = best of the last 48 h, else best of the recent rows (ties → newer).
    Rail = recent rows without the lead, cut to RAIL_ROWS."""
    lead = lead_48h or max(recent, key=lambda r: (r.significance or 0, r.created_at))
    rail = [r for r in recent if r.id != lead.id][:RAIL_ROWS]
    return lead, rail


def journal_teaser(row) -> dict:
    """NewsArticle row → JournalTeaser."""
    content = row.content or ""
    words = len(content.split())
    sections = [h for h in _HEADING.findall(content) if h.strip().lower() not in APPENDIX_SECTIONS]
    image = _IMAGE.search(content)
    return {
        "id": row.id,
        "title": row.title,
        "summary": row.summary,
        "week_start": row.week_start.isoformat() if row.week_start else None,
        "week_end": row.week_end.isoformat() if row.week_end else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "words": words,
        "minutes": reading_minutes(words),
        "sections": sections,
        "sources": len(_LINK.findall(content)),
        "image_url": image.group(1) if image else None,
        "path": f"/articles/{slugify(row.title)}",
    }


def paper_teaser(row) -> dict:
    """PAPER_SUMMARY_COLUMNS row → PaperTeaser, via the public API's mapping."""
    p = paper_summary_kwargs(row)
    words = p["word_count"]
    return {
        "slug": p["slug"],
        "title": p["title"],
        "summary": p["summary"],
        "published_at": p["published_at"],
        "words": words,
        "minutes": reading_minutes(words) if words else None,
        "sources_analyzed": p["sources_analyzed"],
        "quality_score": p["quality_score"],
        "hero_image_url": p["hero_image_url"],
        "path": f"/research/{p['slug']}",
    }


def sites_compact(n: int) -> str:
    """1759673 → "1.76M", 999999 → "999K" (hero counter)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    return f"{n // 1_000}K"


def sites_long(n: int) -> str:
    """1759673 → "1.7 million" (floored, for the h1)."""
    return f"{math.floor(n / 100_000) / 10:.1f} million"


def apply_stats(html: str, stats: dict) -> str:
    """Replace the text of every element carrying data-stat="…" in the shell."""
    values = {
        "sites": sites_compact(stats["total_sites"]),
        "sites-long": sites_long(stats["total_sites"]),
        "countries": str(stats["curated_countries"]),
    }
    for key, value in values.items():
        html = re.sub(rf'(data-stat="{key}"[^>]*>)[^<]*(<)', rf"\g<1>{value}\g<2>", html, count=1)
    return html


def lead_window_start(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC).replace(tzinfo=None)) - LEAD_WINDOW
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/api/test_landing_html.py -v && ruff check api/routes/landing_html.py`
Expected: 10 PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add api/routes/landing_html.py tests/api/test_landing_html.py
git commit -m "feat(api): landing payload builders (stories, journal, papers, hero counts)"
```

---

### Task 7: `GET /home` route, shell post-processing, registration

**Files:**
- Modify: `api/seo_shell.py` (optional `postprocess`)
- Modify: `api/routes/landing_html.py` (append data access + route)
- Modify: `api/main.py:763-766` (include router)
- Modify: `tests/api/test_landing_html.py` (route test)

- [ ] **Step 1: Write the failing route test**

Append to `tests/api/test_landing_html.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch

from api.routes import landing_html


def _landing_data():
    site = SimpleNamespace(id="16147718-a70b-486e-aaba-9cf71316602c", name="Roman grave", country="Austria")
    recent = [item(i, sig=3, hours_ago=i) for i in range(1, 8)]
    return {
        "recent": recent,
        "lead_48h": item(9, sig=9, hours_ago=2, category="bioarchaeology", site=site),
        "categories": ["artifact", "bioarchaeology"],
        "journals": [
            SimpleNamespace(id=74, title="Week of August 31", summary="S", content="## A\n\ntext", week_start=None, week_end=None, published_at=None),
            SimpleNamespace(id=73, title="Week of August 24", summary=None, content="text", week_start=None, week_end=None, published_at=None),
        ],
        "journal_total": 23,
        "papers": [
            SimpleNamespace(id="a", slug="paper-a", question="Q", published_by=None, published_at=None, sites_found=10, title="Paper A", card_description=None, score=None, badge=None, word_count=None, hero_src=None),
            SimpleNamespace(id="b", slug="paper-b", question="Q", published_by=None, published_at=None, sites_found=20, title="Paper B", card_description=None, score=None, badge=None, word_count=None, hero_src=None),
        ],
        "paper_total": 24,
        "news_stats": {"total_items": 3189, "total_articles": 23},
    }


def test_home_route_hands_the_landing_payload_and_substitutes_hero_counts():
    landing_html._cache.clear()
    # render_app_shell is mocked, so the "injected" body is part of the fake shell
    shell = '<html><div class="hero-stat-value" data-stat="sites">1.7M+</div><div id="root"><p>live</p></div></html>'
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=_landing_data()),
        patch.object(landing_html, "get_site_stats", return_value={"total_sites": 1_759_673, "curated_countries": 98}),
        patch.object(landing_html, "get_current_research", new=AsyncMock(return_value={"running": {"question": "Osiris", "started_at": "2026-09-09T06:00:00", "sites_found": 12}})),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>live</p>")) as render,
        patch("api.seo_shell.render_app_shell", return_value=shell),
    ):
        resp = asyncio.run(landing_html.home(db=object()))

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=300"
    body = resp.body.decode()
    assert 'data-stat="sites">1.76M<' in body and "<p>live</p>" in body

    route = render.call_args[0][0]
    assert route["type"] == "landing"
    assert route["stats"] == {"sites": 1_759_673, "stories": 3189, "journals": 23, "papers": 24}
    assert route["stories"]["lead"]["id"] == 9 and len(route["stories"]["rail"]) == 6
    assert route["stories"]["categories"] == ["artifact", "bioarchaeology"]
    assert route["journals"]["lead"]["id"] == 74 and route["journals"]["total"] == 23
    assert route["papers"]["lead"]["slug"] == "paper-a" and route["papers"]["total"] == 24
    assert route["papers"]["theo"] == {"question": "Osiris", "started_at": "2026-09-09T06:00:00", "sites_found": 12}


def test_home_route_omits_sections_without_rows_and_serves_from_cache():
    landing_html._cache.clear()
    data = _landing_data()
    data.update(recent=[], lead_48h=None, journals=[], papers=[])
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=data) as fetch,
        patch.object(landing_html, "get_site_stats", return_value={"total_sites": 5, "curated_countries": 1}),
        patch.object(landing_html, "get_current_research", new=AsyncMock(return_value={"running": None})),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "")) as render,
        patch("api.seo_shell.render_app_shell", return_value='<div id="root"></div>'),
    ):
        asyncio.run(landing_html.home(db=object()))
        asyncio.run(landing_html.home(db=object()))

    route = render.call_args[0][0]
    assert route["stories"] is None and route["journals"] is None and route["papers"] is None
    assert fetch.call_count == 1  # second call came from the 300 s cache
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/api/test_landing_html.py -v -k home_route`
Expected: FAIL — `landing_html.home` / `fetch_landing_data` do not exist.

- [ ] **Step 3: Add `postprocess` to `ssr_shell_response`**

In `api/seo_shell.py`:

```python
from collections.abc import Callable
```

```python
def ssr_shell_response(
    entry: str,
    route: dict[str, Any],
    headers: dict[str, str],
    postprocess: Callable[[str], str] | None = None,
) -> Response:
    """Render the route payload through the SSR sidecar and serve the document.

    ... (existing docstring) ...

    postprocess, when given, runs on the finished document — the homepage
    uses it to substitute live counts into the static hero (landing_html.py).
    """
    head, body = render_page(route)
    html = render_app_shell(
        entry,
        head_html=head,
        root_html=body,
        route=json.dumps(route, ensure_ascii=False).replace("<", "\\u003c"),
    )
    if postprocess is not None:
        html = postprocess(html)
    return Response(content=html, media_type="text/html", headers=headers)
```

- [ ] **Step 4: Append data access, caching and the route to `landing_html.py`**

Add these imports at the top (keep the existing ones):

```python
import threading
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from api.routes.news import get_news_stats
from api.routes.public_v1 import PAPER_SUMMARY_COLUMNS
from api.routes.theo import get_current_research
from api.seo_shell import ssr_shell_response
from api.services.site_stats import get_site_stats
from pipeline.database import NewsArticle, NewsItem, NewsVideo, get_db
from pipeline.research_html_renderer import PUBLIC_PAPER_WHERE
```

Append at the end of the file:

```python
router = APIRouter()
_HTML_HEADERS = {"Cache-Control": "public, max-age=300"}
_CACHE_TTL = 300.0
# (expires_at, response) — one document per process; ~200 hits/day need no more.
_cache: dict[str, tuple[float, Response]] = {}
_cache_lock = threading.Lock()


def _story_query(db: Session):
    """Same base filter as /api/news/feed, minus speculative stories (they are noindex)."""
    return (
        db.query(NewsItem)
        .join(NewsVideo)
        .options(joinedload(NewsItem.video).joinedload(NewsVideo.channel), joinedload(NewsItem.site))
        .filter(
            NewsItem.post_text.isnot(None),
            (NewsItem.significance.is_(None)) | (NewsItem.significance >= 2),
            (NewsItem.news_category != "speculative") | (NewsItem.news_category.is_(None)),
        )
    )


def fetch_landing_data(db: Session) -> dict:
    """Every DB read of the route, in one place, so the route itself stays testable."""
    recent = _story_query(db).order_by(NewsItem.created_at.desc()).limit(RECENT_ROWS).all()
    lead_48h = (
        _story_query(db)
        .filter(NewsItem.created_at >= lead_window_start())
        .order_by(NewsItem.significance.desc().nulls_last(), NewsItem.created_at.desc())
        .first()
    )
    categories = [
        row[0]
        for row in db.execute(
            text(
                """
                SELECT DISTINCT news_category FROM news_items
                WHERE post_text IS NOT NULL AND news_category IS NOT NULL
                  AND news_category <> 'speculative'
                  AND created_at >= NOW() - INTERVAL '30 days'
                ORDER BY news_category
                """
            )
        )
    ]
    journals = (
        db.query(NewsArticle).filter(NewsArticle.active.is_(True)).order_by(NewsArticle.week_start.desc()).limit(4).all()
    )
    papers = db.execute(
        text(
            f"""
            SELECT {PAPER_SUMMARY_COLUMNS}
            FROM research_requests r
            WHERE {PUBLIC_PAPER_WHERE}
            ORDER BY r.published_at DESC NULLS LAST
            LIMIT 6
            """
        )
    ).fetchall()
    paper_total = db.execute(text(f"SELECT COUNT(*) FROM research_requests r WHERE {PUBLIC_PAPER_WHERE}")).scalar() or 0
    news_stats = get_news_stats(db)
    if not isinstance(news_stats, dict):  # cache_get returns the dict, a cold call the model
        news_stats = news_stats.model_dump()
    return {
        "recent": recent,
        "lead_48h": lead_48h,
        "categories": categories,
        "journals": journals,
        "journal_total": news_stats["total_articles"],
        "papers": papers,
        "paper_total": paper_total,
        "news_stats": news_stats,
    }


def build_route(data: dict, site_stats: dict, theo_running: dict | None) -> dict:
    stories = None
    if data["recent"]:
        lead, rail = pick_lead_and_rail(data["recent"], data["lead_48h"])
        stories = {
            "lead": story_teaser(lead),
            "rail": [story_teaser(r) for r in rail],
            "categories": data["categories"],
        }
    journals = None
    if data["journals"]:
        teasers = [journal_teaser(j) for j in data["journals"]]
        journals = {"lead": teasers[0], "rail": teasers[1:], "total": data["journal_total"]}
    papers = None
    if data["papers"]:
        teasers = [paper_teaser(p) for p in data["papers"]]
        theo = None
        if theo_running:
            theo = {
                "question": theo_running["question"],
                "started_at": theo_running["started_at"],
                "sites_found": theo_running["sites_found"],
            }
        papers = {"lead": teasers[0], "rail": teasers[1:], "total": data["paper_total"], "theo": theo}
    return {
        "type": "landing",
        "stats": {
            "sites": site_stats["total_sites"],
            "stories": data["news_stats"]["total_items"],
            "journals": data["journal_total"],
            "papers": data["paper_total"],
        },
        "stories": stories,
        "journals": journals,
        "papers": papers,
    }


@router.get("/home")
async def home(db: Session = Depends(get_db)):
    """The homepage document. nginx maps "/" here; see the module docstring."""
    with _cache_lock:
        hit = _cache.get("home")
        if hit and hit[0] > time.monotonic():
            return hit[1]
    site_stats = get_site_stats()
    current = await get_current_research()
    route = build_route(fetch_landing_data(db), site_stats, current.get("running"))
    response = ssr_shell_response(
        "index.html", route, _HTML_HEADERS, postprocess=lambda html: apply_stats(html, site_stats)
    )
    with _cache_lock:
        _cache["home"] = (time.monotonic() + _CACHE_TTL, response)
    return response
```

`get_current_research` is the existing public `/api/theo/research/current` handler — an async function with its own 30 s cache — called directly rather than re-implemented.

- [ ] **Step 5: Register the router**

In `api/main.py` next to the other HTML routers (line 763–766):

```python
from api.routes import landing_html
...
app.include_router(landing_html.router, tags=["landing-html"])
```

`GET /` stays the health check; `/home` is only reached through nginx.

- [ ] **Step 6: Run the backend gates**

Run: `python -m pytest tests/api/test_landing_html.py tests/api/test_site_stats.py tests/api/test_sites_html_ssr.py -v && ruff check api && lint-imports && vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80`
Expected: all PASS, ruff/lint-imports/vulture clean. If `lint-imports` flags `api.routes.landing_html → api.routes.theo`, that is the same layer (routes → routes) other modules already use (`research_html` imports `public_v1`), so it should pass; if it does not, the contract in `.importlinter` names the allowed edge — add it there rather than copying the query.

Then the full DB-less subset CI runs: `python -m pytest -m "not integration and not live_llm" -q` — expected: all green.

- [ ] **Step 7: Commit**

```bash
git add api/seo_shell.py api/routes/landing_html.py api/main.py tests/api/test_landing_html.py
git commit -m "feat(api): GET /home renders the landing live sections through the SSR sidecar"
```

---

### Task 8: nginx, bundle budget, CI step — needs the user's go before pushing

**Files:**
- Modify: `ancientnerds-nginx-config:205-210`
- Create: `ancient-nerds-map/.size-limit.json`
- Modify: `ancient-nerds-map/package.json` (devDependencies, script)
- Modify: `.github/workflows/ci.yml` (lint-frontend, after `Build`)

These three files are deploy/CI configuration. Per the project rule they need explicit approval before the push, even though the deploy applies the nginx file automatically.

- [ ] **Step 1: nginx**

Replace the `location = /` block (lines 205–210) with:

```nginx
    # Homepage: server-rendered by the API (GET /home — live Stories/Journal/
    # Papers sections, api/routes/landing_html.py). While the API or the SSR
    # sidecar restarts, the static build is served instead: the page stays up
    # with the three live sections empty. proxy_intercept_errors is needed
    # because the API answers 502 itself when the sidecar is down.
    location = / {
        if ($arg_site ~ "^[0-9a-fA-F-]{36}$") {
            return 301 /site.html?id=$arg_site;
        }
        proxy_pass http://an_api/home;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_intercept_errors on;
        error_page 502 504 = @home_static;
    }

    location @home_static {
        add_header Cache-Control "no-cache" always;
        try_files /index.html =404;
    }
```

- [ ] **Step 2: size-limit**

`ancient-nerds-map/.size-limit.json`:

```json
[
  {
    "name": "landing page-specific JS (react-dom is a shared chunk)",
    "path": ["dist/assets/landing-*.js"],
    "limit": "40 kB",
    "brotli": true
  }
]
```

Run: `cd ancient-nerds-map && npm install --save-dev size-limit @size-limit/file` and add the script `"size": "size-limit"` to `package.json`. Then `npm run build && npx size-limit` — expected: the landing chunk under 40 kB brotli (Task 4 measured it). If it is over, the culprit is an import pulling in a large module (check with `npx vite-bundle-visualizer` or `npx size-limit --why`), not the limit.

- [ ] **Step 3: CI step**

In `.github/workflows/ci.yml`, `lint-frontend` job, after the `Build` step and before `Build SSR bundle`:

```yaml
      - name: Bundle budget (size-limit)
        run: npx size-limit
```

- [ ] **Step 4: knip**

Run: `cd ancient-nerds-map && npx knip --no-progress --include files,dependencies,devDependencies`
Expected: clean. If knip reports `size-limit`/`@size-limit/file` as unused devDependencies, add to `knip.json` (or the `knip` key in `package.json`): `"ignoreDependencies": ["@size-limit/file"]` — size-limit loads its plugin by name, knip cannot see that.

- [ ] **Step 5: Commit (do not push yet)**

```bash
git add ancientnerds-nginx-config ancient-nerds-map/.size-limit.json ancient-nerds-map/package.json ancient-nerds-map/package-lock.json .github/workflows/ci.yml
git commit -m "ops(landing): nginx serves / from the API with static fallback; size-limit gate"
```

Ask the user for the go on the nginx and CI changes, then push all commits of this plan together.

---

### Task 9: Deploy verification

**Files:** none (verification only). Run after the deploy has finished (`gh run list --limit 3` shows `completed/success` for the pushed commit; note `--commit` filtering does not work, list without it).

- [ ] **Step 1: SSR document check**

```bash
curl -s -A "Mozilla/5.0" https://ancientnerds.com/ -o /tmp/home.html
grep -c 'href="/news-archive/' /tmp/home.html      # expected: 7
grep -c '<h1' /tmp/home.html                        # expected: 1
grep -o 'data-stat="sites">[^<]*' /tmp/home.html    # expected: 1.7xM
grep -c "750" /tmp/home.html                        # expected: 0
grep -o 'cache-control: [^\r]*' <(curl -sI https://ancientnerds.com/)   # expected: public, max-age=300
curl -s -A "Googlebot/2.1" https://ancientnerds.com/ | grep -c 'href="/research/'   # expected: >= 7
```

- [ ] **Step 2: Hydration and interaction (Playwright, Chromium)**

```python
# run with: PYTHONIOENCODING=utf-8 python scripts/verify_landing.py (create ad hoc, do not commit)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_context(viewport={"width": 1400, "height": 900}).new_page()
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)[:160]))
    page.on("console", lambda m: errors.append(m.text[:160]) if m.type == "error" else None)
    page.goto("https://ancientnerds.com/", wait_until="networkidle", timeout=90000)
    lead_before = page.inner_text(".ll-lead .ll-title")
    page.click(".ll-chip >> text=artifact")
    page.wait_for_function("document.querySelector('.ll-chip[aria-pressed=true]').innerText === 'artifact'", timeout=15000)
    page.wait_for_timeout(1500)
    lead_after = page.inner_text(".ll-lead .ll-title")
    rows = page.locator(".ll-rail .ll-row").count()
    page.click(".ll-more"); page.wait_for_timeout(2500)
    rows_after = page.locator(".ll-rail .ll-row").count()
    lcp = page.evaluate("() => { const e = performance.getEntriesByType('largest-contentful-paint').pop(); return e && (e.element ? e.element.tagName + '.' + e.element.className : e.url) }")
    print({"errors": errors, "lead_changed": lead_before != lead_after, "rows": rows, "rows_after_more": rows_after, "lcp": lcp, "ago": page.locator("text=/\\d+[hmd] ago/").count()})
    b.close()
```

Expected: `errors == []` (no hydration warnings), `rows == 6`, `rows_after_more > 6`, `lcp` is the hero logo/poster (`IMG.hero-logo` or the poster), `ago > 0` (relative time upgraded after mount).

- [ ] **Step 3: Crawler view with JavaScript blocked**

Same script with `page = b.new_context(java_script_enabled=False, user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)")`: expected the same 7 story links, the journal and paper links, the `#stories-live` section text present.

- [ ] **Step 4: Fallback**

On the VPS: `ssh ancientnerds 'docker stop ancient_nerds_ssr'`, then `curl -s -o /dev/null -w "%{http_code}\n" https://ancientnerds.com/` — expected `200` with the static page (`grep -c 'id="root"></div>'` → 1, no story links). Then `ssh ancientnerds 'docker start ancient_nerds_ssr'` and confirm the live version returns within 5 minutes (cache) — or immediately after `docker restart ancient_nerds_api`.

- [ ] **Step 5: Record**

Note the measured numbers (bundle size, LCP element, first GSC crawl of the new homepage) in the memory file `project-landing-page-rebuild.md` and mark the plan tasks done.
