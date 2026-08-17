# React-SSR für die indexierten Seiten — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jede indexierte Seite wird nur noch **einmal** beschrieben — als React-Komponente. `pipeline/seo_pages.py` verschwindet ersatzlos.

**Architecture:** Ein Node-Sidecar-Container rendert die React-Komponenten serverseitig (`renderToString`). FastAPI bleibt Routing- und Datenschicht: es fragt wie bisher die DB ab, baut das Payload-Objekt und schickt es per HTTP an den Sidecar, der `{head, html}` zurückgibt. Der Splice-Punkt bleibt exakt derselbe wie heute (`api/seo_shell.py::shell_response()`), deshalb ändert sich an nginx, Sitemap und URLs **nichts**. Im Browser wird aus `createRoot` ein `hydrateRoot` — dasselbe Markup, das der Server geschickt hat, wird übernommen statt weggeworfen. Globus (`globe.html`, `index.html`) und alle übrigen Entries bleiben unangetastet.

**Tech Stack:** React 18.3.1 (`renderToString`, `hydrateRoot`), Vite 5.4.2 (`build --ssr`), Node 20 (auf dem VPS vorhanden), Vitest 4.0.18 (vorhanden, bisher ungenutzt), FastAPI + httpx, Docker Compose.

---

## Ausgangslage (verifiziert 2026-08-09)

**9 indexierte Seitentypen, verteilt auf 4 Vite-Entries:**

| Entry | Route-Typen | FastAPI-Route |
|---|---|---|
| `story.html` | `story`, `storyArchive` | `/news-archive/{slug}`, `/news-archive/`, `/news-archive/page/{n}` |
| `site.html` | `site`, `sitesIndex`, `country` | `/sites/{c}/{slug}`, `/sites/`, `/sites/{c}` |
| `research.html` | `research`, `researchIndex` | `/research/{slug}`, `/research/` |
| `articles.html` | `article`, `articleIndex` | `/articles/{slug}`, `/articles/` |

**Der eine harte SSR-Blocker:** `src/pages/ResearchPaperPage.tsx:213-218` liest `window.location.search` **während des Renderns** (im `useMemo`), weil `anRoute()` auf dem Server `undefined` liefert und der Code dann auf den Legacy-Zweig fällt. Das crasht `renderToString`. Task 1 beseitigt genau das.

**Kein Blocker:** Alle übrigen `window`/`document`/`navigator`-Zugriffe in `ArticlesPage.tsx` (23 Stück) und `ResearchPaperPage.tsx` (20 Stück) liegen ausnahmslos in `useEffect`, `useCallback` oder Event-Handlern. Die laufen bei `renderToString` nicht. `PageHeader`, `AuthContext` und `OfflineContext` haben keinen Browser-Zugriff auf Modulebene (geprüft).

**Warum kein Fallback-Zweig:** CLAUDE.md verbietet defensive Degradation. Der SSR-Container ist eine harte Abhängigkeit — fällt er aus, antwortet die Route mit 502 und der Healthcheck schlägt an. Kein stiller Rückfall auf ein zweites Rendering-System; genau dieses zweite System wollen wir ja loswerden.

---

## Dateistruktur

**Neu:**

| Datei | Verantwortung |
|---|---|
| `ancient-nerds-map/src/seo/RouteContext.tsx` | Stellt das Route-Payload bereit. Server: als Prop. Browser: aus `window.__AN_ROUTE__`. Ersetzt den direkten `window`-Zugriff. |
| `ancient-nerds-map/src/seo/meta.ts` | Reine TS-Funktionen (kein React): pro Seitentyp Title/Description/Canonical/JSON-LD. Das ist die Portierung von `_meta_head()` aus `seo_pages.py`. |
| `ancient-nerds-map/src/seo/registry.tsx` | Eine Tabelle: Route-Typ → `{ Component, meta }`. Einzige Stelle, die alle 9 Typen kennt. |
| `ancient-nerds-map/src/entry-server.tsx` | SSR-Einstieg: `render({type, payload})` → `{head, html}`. |
| `ancient-nerds-map/ssr/server.mjs` | Node-HTTP-Dienst, POST `/render`, GET `/health`. |
| `Dockerfile.ssr` | Container für den Dienst. |
| `ancient-nerds-map/src/seo/__tests__/meta.test.ts` | Vitest-Tests für die Meta-Funktionen. |
| `ancient-nerds-map/src/seo/__tests__/render.test.tsx` | Vitest-Tests, die jeden der 9 Typen serverseitig rendern. |
| `tests/api/test_ssr_client.py` | Pytest für den FastAPI→SSR-Client. |

**Geändert:**

| Datei | Änderung |
|---|---|
| `ancient-nerds-map/src/types/anRoute.ts` | `anRoute()` entfällt; Typen bleiben und werden um die fehlenden Payload-Felder erweitert. |
| `ancient-nerds-map/src/{story,site,research,articles}Main.tsx` | `createRoot` → `hydrateRoot`, Payload über `RouteProvider`. |
| `ancient-nerds-map/src/pages/ResearchPaperPage.tsx` | Legacy-`window.location`-Zweig entfernen. |
| `ancient-nerds-map/vite.config.ts` | SSR-Build-Konfiguration. |
| `ancient-nerds-map/package.json` | `test`- und `build:ssr`-Scripts. |
| `api/ssr_client.py` *(neu)* | httpx-Client zum Sidecar. |
| `api/seo_shell.py` | Ruft den SSR-Dienst statt `seo_pages`. |
| `api/routes/{sites,articles,research}_html.py` | Übergeben Payload-Dicts statt `SeoPage`-Objekte. |
| `docker-compose.yml` | Service `ssr`. |
| `.github/workflows/ci.yml` | SSR-Build + Container im Deploy. |

**Gelöscht (am Ende, Task 16):** `pipeline/seo_pages.py`, `pipeline/app_shell.py`, `tests/pipeline/test_app_shell.py`, `tests/pipeline/test_seo_story_extras.py`, `tests/pipeline/test_seo_country_extras.py`.

---

## Phase 1 — Fundament

> **Reihenfolge:** Task 5 (`meta.ts`) muss **vor** Task 3 (`registry.tsx`) fertig sein — die Registry importiert die Meta-Funktionen. Und Task 3 und 4 gehören in **einen** Commit: die Registry ruft die Komponenten ohne Props auf, was erst nach Task 4 typprüfbar ist. Empfohlene Abarbeitung: **1 → 2 → 5 → 3+4 → 6 …**

### Task 1: Route-Kontext statt `window`-Zugriff

Ohne das crasht jedes serverseitige Rendern. Erst diesen Blocker weg, dann alles andere.

**Files:**
- Create: `ancient-nerds-map/src/seo/RouteContext.tsx`
- Modify: `ancient-nerds-map/src/pages/ResearchPaperPage.tsx:213-218`
- Test: `ancient-nerds-map/src/seo/__tests__/routeContext.test.tsx`

- [ ] **Step 1: `test`-Script anlegen** (Vitest ist als Dependency da, aber nicht aufrufbar)

In `ancient-nerds-map/package.json` bei `"scripts"` ergänzen:

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 2: Den fehlschlagenden Test schreiben**

`ancient-nerds-map/src/seo/__tests__/routeContext.test.tsx`:

```tsx
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { RouteProvider, useRoute } from '../RouteContext'

function Probe() {
  const route = useRoute()
  return <span>{route?.type ?? 'none'}</span>
}

describe('RouteProvider', () => {
  it('liefert das Payload serverseitig, ohne window zu berühren', () => {
    const html = renderToString(
      <RouteProvider value={{ type: 'sitesIndex', countries: [] }}>
        <Probe />
      </RouteProvider>,
    )
    expect(html).toContain('sitesIndex')
  })

  it('liefert undefined ohne Provider statt zu werfen', () => {
    const html = renderToString(<Probe />)
    expect(html).toContain('none')
  })
})
```

- [ ] **Step 3: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/routeContext.test.tsx`
Expected: FAIL — `Failed to resolve import "../RouteContext"`

- [ ] **Step 4: Den Kontext implementieren**

`ancient-nerds-map/src/seo/RouteContext.tsx`:

```tsx
/**
 * Das Route-Payload, das Server und Browser gemeinsam benutzen.
 *
 * Bis 2026-08-09 las jede Seite window.__AN_ROUTE__ direkt. Das ging nur im
 * Browser — serverseitiges Rendern fiel auf einen window.location-Zweig
 * zurück und stürzte ab. Über den Kontext bekommt der Server das Payload als
 * Prop, der Browser liest es beim Hydrieren einmal aus window.
 */

import { createContext, useContext, type ReactNode } from 'react'

import type { AnRoute } from '../types/anRoute'

const RouteCtx = createContext<AnRoute | undefined>(undefined)

export function RouteProvider({ value, children }: { value?: AnRoute; children: ReactNode }) {
  return <RouteCtx.Provider value={value}>{children}</RouteCtx.Provider>
}

export function useRoute(): AnRoute | undefined {
  return useContext(RouteCtx)
}

/** Nur im Browser-Einstieg aufrufen — liest das vom Server injizierte Payload. */
export function readInjectedRoute(): AnRoute | undefined {
  return typeof window === 'undefined' ? undefined : window.__AN_ROUTE__
}
```

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/routeContext.test.tsx`
Expected: PASS, 2 Tests

- [ ] **Step 6: Den SSR-Blocker in ResearchPaperPage entfernen**

In `ancient-nerds-map/src/pages/ResearchPaperPage.tsx` die Zeilen 213-218 ersetzen. Alt:

```tsx
  const slug = useMemo(() => {
    // /research/{slug} is canonical; ?slug= is the legacy entry form.
    const route = anRoute()
    if (route?.type === 'research') return route.slug
    return new URLSearchParams(window.location.search).get('slug') || ''
  }, [])
```

Neu:

```tsx
  // /research.html?slug= antwortet seit 2026-08-07 mit 301 auf /research/{slug}.
  // Der Legacy-Zweig war damit unerreichbar — und las window.location während
  // des Renderns, was serverseitiges Rendern unmöglich machte.
  const route = useRoute()
  const slug = route?.type === 'research' ? route.slug : ''
```

Den Import `import { anRoute } from '../types/anRoute'` ersetzen durch `import { useRoute } from '../seo/RouteContext'`.

- [ ] **Step 7: Typecheck und Tests**

Run: `cd ancient-nerds-map && npm run type-check && npx vitest run`
Expected: keine TS-Fehler, alle Tests grün

- [ ] **Step 8: Commit**

```bash
git add ancient-nerds-map/package.json ancient-nerds-map/src/seo/RouteContext.tsx ancient-nerds-map/src/seo/__tests__/routeContext.test.tsx ancient-nerds-map/src/pages/ResearchPaperPage.tsx
git commit -m "refactor(seo): route payload via context instead of window

renderToString crashed on ResearchPaperPage because the legacy ?slug=
branch read window.location during render. That branch has been
unreachable since /research.html?slug= started answering 301 (1ad85ed).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Alle Seiten auf `useRoute()` umstellen

**Files:**
- Modify: `ancient-nerds-map/src/{story,site,research,articles}Main.tsx`
- Modify: `ancient-nerds-map/src/pages/SitePage.tsx:16-20`
- Modify: `ancient-nerds-map/src/types/anRoute.ts`
- Test: `ancient-nerds-map/src/seo/__tests__/routeContext.test.tsx` (erweitern)

- [ ] **Step 1: Test schreiben, der `anRoute` im Quellbaum verbietet**

An `ancient-nerds-map/src/seo/__tests__/routeContext.test.tsx` anhängen:

```tsx
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const p = join(dir, name)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })
}

describe('kein direkter window.__AN_ROUTE__-Zugriff mehr', () => {
  it('nur RouteContext.tsx darf __AN_ROUTE__ lesen', () => {
    const offenders = walk('src')
      .filter(f => /\.tsx?$/.test(f) && !f.includes('RouteContext'))
      .filter(f => readFileSync(f, 'utf8').includes('__AN_ROUTE__'))
    expect(offenders).toEqual([])
  })
})
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/routeContext.test.tsx`
Expected: FAIL — listet `src/types/anRoute.ts` und ggf. weitere

- [ ] **Step 3: `anRoute()` aus `anRoute.ts` entfernen**

In `ancient-nerds-map/src/types/anRoute.ts` diesen Block **löschen**:

```ts
export function anRoute(): AnRoute | undefined {
  return typeof window === 'undefined' ? undefined : window.__AN_ROUTE__
}
```

Die `declare global`-Deklaration bleibt (`RouteContext.tsx` braucht sie).

- [ ] **Step 4: `SitePage.tsx` umstellen**

In `ancient-nerds-map/src/pages/SitePage.tsx` den Import `import { anRoute } from '../types/anRoute'` ersetzen durch `import { useRoute } from '../seo/RouteContext'` und jeden Aufruf `anRoute()` durch `useRoute()` ersetzen. Der Legacy-Zweig `new URLSearchParams(window.location.search).get('id')` wird gelöscht — `/site.html?id=` antwortet seit 1ad85ed mit 301.

- [ ] **Step 5: Die vier Entries umstellen**

Jeder Entry liest das Payload **einmal** und reicht es in den Provider. Beispiel `ancient-nerds-map/src/siteMain.tsx` vollständig:

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import { SeoRoute } from './seo/registry'
import './styles/index.css'

const route = readInjectedRoute()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouteProvider value={route}>
      <AuthProvider>
        <OfflineProvider>
          <SeoRoute />
        </OfflineProvider>
      </AuthProvider>
    </RouteProvider>
  </React.StrictMode>,
)
```

`storyMain.tsx`, `researchMain.tsx` und `articlesMain.tsx` bekommen denselben Aufbau — identisch bis auf nichts, weil `SeoRoute` den Typ selbst auflöst (Task 3). Die bisherigen `window.location.replace`-Weichen in `storyMain.tsx` und `researchMain.tsx` entfallen: sie liefen nur, wenn kein Payload da war, und das kann nach dem Cutover nicht mehr vorkommen — die Entries sind ausschließlich über die SSR-Routen erreichbar.

- [ ] **Step 6: Tests und Typecheck**

Run: `cd ancient-nerds-map && npm run type-check && npx vitest run && npm run build`
Expected: alles grün, Build erfolgreich

- [ ] **Step 7: Commit**

```bash
git add ancient-nerds-map/src
git commit -m "refactor(seo): every page reads the route through the context

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Die Registry — eine Tabelle für alle 9 Typen

**Files:**
- Create: `ancient-nerds-map/src/seo/registry.tsx`
- Test: `ancient-nerds-map/src/seo/__tests__/registry.test.tsx`

- [ ] **Step 1: Test schreiben**

`ancient-nerds-map/src/seo/__tests__/registry.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'

import { ROUTE_TYPES, registry } from '../registry'

describe('registry', () => {
  it('kennt genau die 9 indexierten Seitentypen', () => {
    expect([...ROUTE_TYPES].sort()).toEqual(
      [
        'article',
        'articleIndex',
        'country',
        'research',
        'researchIndex',
        'site',
        'sitesIndex',
        'story',
        'storyArchive',
      ].sort(),
    )
  })

  it('hat für jeden Typ Komponente und meta()', () => {
    for (const type of ROUTE_TYPES) {
      expect(registry[type].Component, type).toBeTypeOf('function')
      expect(registry[type].meta, type).toBeTypeOf('function')
    }
  })
})
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/registry.test.tsx`
Expected: FAIL — `Failed to resolve import "../registry"`

- [ ] **Step 3: Registry implementieren**

`ancient-nerds-map/src/seo/registry.tsx`:

```tsx
/**
 * Die eine Stelle, die alle indexierten Seitentypen kennt.
 *
 * Server (entry-server.tsx) und Browser (die vier *Main.tsx) lösen den Typ
 * über dieselbe Tabelle auf. Kommt ein Seitentyp dazu, wird er hier
 * eingetragen — und ist damit sofort in beiden Welten vorhanden.
 */

import ArticlesPage from '../pages/ArticlesPage'
import ResearchPaperPage from '../pages/ResearchPaperPage'
import SitePage from '../pages/SitePage'
import { CountrySitesPage, SitesIndexPage } from '../pages/SiteListingPage'
import StoryArchivePage from '../pages/StoryArchivePage'
import StoryPage from '../pages/StoryPage'
import type { AnRoute } from '../types/anRoute'
import * as meta from './meta'
import { useRoute } from './RouteContext'

type Entry = { Component: () => JSX.Element | null; meta: (route: never) => meta.PageMeta }

export const registry = {
  story: { Component: StoryPage, meta: meta.storyMeta },
  storyArchive: { Component: StoryArchivePage, meta: meta.storyArchiveMeta },
  site: { Component: SitePage, meta: meta.siteMeta },
  sitesIndex: { Component: SitesIndexPage, meta: meta.sitesIndexMeta },
  country: { Component: CountrySitesPage, meta: meta.countryMeta },
  research: { Component: ResearchPaperPage, meta: meta.researchMeta },
  researchIndex: { Component: ResearchPaperPage, meta: meta.researchIndexMeta },
  article: { Component: ArticlesPage, meta: meta.articleMeta },
  articleIndex: { Component: ArticlesPage, meta: meta.articleIndexMeta },
} as unknown as Record<AnRoute['type'], Entry>

export const ROUTE_TYPES = Object.keys(registry) as AnRoute['type'][]

/** Rendert die zum Payload passende Seite. Server und Browser benutzen das. */
export function SeoRoute() {
  const route = useRoute()
  if (!route) return null
  const entry = registry[route.type]
  if (!entry) return null
  const { Component } = entry
  return <Component />
}
```

> **Voraussetzung:** `src/seo/meta.ts` aus Task 5 muss existieren, sonst schlägt der Import fehl. Die Komponenten nehmen heute teils Props (`StoryPage story={route}`, `CountrySitesPage country=… sections=…`); Task 4 baut sie auf `useRoute()` um. Bis dahin meldet der Typecheck hier Fehler — deshalb Task 3 und 4 in **einem** Commit.

- [ ] **Step 4: Test laufen lassen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/registry.test.tsx`
Expected: PASS, 2 Tests

---

### Task 4: Komponenten holen ihre Daten selbst

**Files:**
- Modify: `ancient-nerds-map/src/pages/StoryPage.tsx`, `StoryArchivePage.tsx`, `SiteListingPage.tsx`
- Test: `ancient-nerds-map/src/seo/__tests__/render.test.tsx`

- [ ] **Step 1: Den Rendertest für alle 9 Typen schreiben**

`ancient-nerds-map/src/seo/__tests__/render.test.tsx`:

```tsx
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { RouteProvider } from '../RouteContext'
import { SeoRoute } from '../registry'
import { FIXTURES } from './fixtures'

describe('serverseitiges Rendern', () => {
  for (const [type, payload] of Object.entries(FIXTURES)) {
    it(`rendert ${type} ohne Browser-APIs`, () => {
      const html = renderToString(
        <RouteProvider value={payload as never}>
          <SeoRoute />
        </RouteProvider>,
      )
      expect(html.length).toBeGreaterThan(50)
    })
  }
})
```

- [ ] **Step 2: Fixtures anlegen**

`ancient-nerds-map/src/seo/__tests__/fixtures.ts` — je Typ ein realistisches Payload. Die Feldnamen müssen exakt denen aus `_route_json()` in `pipeline/seo_pages.py` entsprechen; dort abschreiben, nicht raten:

```ts
export const FIXTURES = {
  sitesIndex: {
    type: 'sitesIndex',
    countries: [{ name: 'Denmark', count: 42, path: '/sites/denmark' }],
  },
  country: {
    type: 'country',
    country: 'Türkiye',
    periodSpan: '9000 BC – 1964 AD',
    total: 1,
    sections: [
      {
        label: 'Temple complex',
        anchor: 'temple-complex',
        sites: [
          {
            name: 'Göbekli Tepe',
            path: '/sites/türkiye/gobekli-tepe-abc12345',
            summary: 'Ein neolithisches Heiligtum.',
            siteType: 'Temple complex',
            period: '< 4500 BC',
            thumb: '/data/images/wiki/abc12345/hero.webp',
          },
        ],
      },
    ],
  },
  // story, storyArchive, site, research, researchIndex, article, articleIndex
  // analog ergänzen — Feldnamen aus pipeline/seo_pages.py:_route_json() übernehmen.
} as const
```

- [ ] **Step 3: Test laufen lassen, Fehlschläge sehen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/render.test.tsx`
Expected: FAIL für jeden Typ, dessen Komponente noch Props erwartet

- [ ] **Step 4: Komponenten auf `useRoute()` umbauen**

Beispiel `StoryArchivePage.tsx` — Signatur ändern von

```tsx
export default function StoryArchivePage({ page, totalPages, total, stories }: Props) {
```

zu

```tsx
export default function StoryArchivePage() {
  const route = useRoute()
  if (route?.type !== 'storyArchive') return null
  const { page, totalPages, total, stories } = route
```

Dasselbe Muster für `StoryPage`, `SitesIndexPage` und `CountrySitesPage`. Die Props-Interfaces entfallen; die Typen kommen aus `AnRoute`.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd ancient-nerds-map && npx vitest run && npm run type-check`
Expected: alle 9 Rendertests grün

- [ ] **Step 6: Commit**

```bash
git add ancient-nerds-map/src
git commit -m "refactor(seo): pages read their payload from the route context

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Head-Tags nach TypeScript

### Task 5: `meta.ts` — Portierung von `_meta_head()`

Der Head ist der Teil, den Python heute exklusiv baut. Ohne ihn kann `seo_pages.py` nicht sterben. Bewusst **kein** react-helmet: reine Funktionen sind testbar, brauchen keine Dependency und laufen im Node-Dienst ohne React-Baum.

**Files:**
- Create: `ancient-nerds-map/src/seo/meta.ts`
- Test: `ancient-nerds-map/src/seo/__tests__/meta.test.ts`

- [ ] **Step 1: Referenzausgabe aus Python festhalten**

Run:

```bash
cd C:/PythonProjects/AncientMap && python -c "
from pipeline.seo_pages import country_sites_page
p = country_sites_page('Türkiye', [{'name':'Göbekli Tepe','path':'/sites/türkiye/gobekli-tepe-abc12345','description':'Ein neolithisches Heiligtum.','site_type':'Temple complex','period_name':'< 4500 BC','period_start':-9000,'thumbnail_url':'/data/images/wiki/abc12345/hero.webp'}])
print(p.head)
" > /tmp/ref_country_head.txt && cat /tmp/ref_country_head.txt
```

Expected: der vollständige Head-Block. Er ist die Sollvorgabe für den Test.

- [ ] **Step 2: Test schreiben**

`ancient-nerds-map/src/seo/__tests__/meta.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { countryMeta, renderHead } from '../meta'
import { FIXTURES } from './fixtures'

describe('countryMeta', () => {
  const m = countryMeta(FIXTURES.country)

  it('nennt Land und Anzahl im Title', () => {
    expect(m.title).toBe('Archaeological Sites in Türkiye (1) | Ancient Nerds')
  })

  it('nennt die echten Typen und die Zeitspanne', () => {
    expect(m.description).toContain('temple complex')
    expect(m.description).toContain('Spanning 9000 BC – 1964 AD')
  })

  it('kanonisiert prozentkodiert gegen die Apex-Domain', () => {
    expect(m.canonical).toBe('https://ancientnerds.com/sites/t%C3%BCrkiye')
  })

  it('nimmt einen echten Hero als og:image', () => {
    expect(m.image).toBe('https://ancientnerds.com/data/images/wiki/abc12345/hero.webp')
  })
})

describe('renderHead', () => {
  it('erzeugt genau einen canonical und einen title', () => {
    const head = renderHead(countryMeta(FIXTURES.country))
    expect(head.match(/<link rel="canonical"/g)).toHaveLength(1)
    expect(head.match(/<title>/g)).toHaveLength(1)
  })

  it('maskiert < in JSON-LD, damit kein script-Ausbruch möglich ist', () => {
    const head = renderHead({
      title: 'x',
      description: 'y',
      canonical: 'https://ancientnerds.com/x',
      schema: '{"n": "</script><b>"}',
    })
    expect(head).not.toContain('</script><b>')
  })
})
```

- [ ] **Step 3: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/meta.test.ts`
Expected: FAIL — `Failed to resolve import "../meta"`

- [ ] **Step 4: `meta.ts` implementieren**

`ancient-nerds-map/src/seo/meta.ts` — Portierung von `_meta_head()`, `_json_str()` und den neun Seitenfunktionen aus `pipeline/seo_pages.py`. Grundgerüst:

```ts
export const BASE_URL = 'https://ancientnerds.com'

export interface PageMeta {
  title: string
  description: string
  canonical: string
  ogType?: string
  image?: string
  schema?: string
}

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

/** Wie _meta_head(): Whitespace kollabieren, auf 300 Zeichen kappen. */
const desc = (s: string) => s.split(/\s+/).filter(Boolean).join(' ').slice(0, 300)

export function renderHead(m: PageMeta): string {
  const img = esc(m.image ?? `${BASE_URL}/landing/og-image.png`)
  const d = esc(desc(m.description))
  const t = esc(m.title)
  const schema = m.schema
    ? `\n<script type="application/ld+json">${m.schema.replace(/</g, '\\u003c')}</script>`
    : ''
  return `<title>${t}</title>
<meta name="description" content="${d}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="${esc(m.canonical)}">
<meta property="og:type" content="${m.ogType ?? 'website'}">
<meta property="og:url" content="${esc(m.canonical)}">
<meta property="og:site_name" content="Ancient Nerds">
<meta property="og:title" content="${t}">
<meta property="og:description" content="${d}">
<meta property="og:image" content="${img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${t}">
<meta name="twitter:description" content="${d}">
<meta name="twitter:image" content="${img}">
<meta name="twitter:site" content="@AncientNerdsDAO">${schema}`
}
```

Danach je Seitentyp eine Funktion. `countryMeta` als Vorlage — sie ist die komplexeste, weil sie Typen und Zeitspanne aus dem Payload ableitet:

```ts
export function countryMeta(route: CountryRoute): PageMeta {
  const canonical = `${BASE_URL}${encodeURI(`/sites/${slugify(route.country)}`)}`
  const namedTypes = route.sections
    .slice(0, 3)
    .map(s => s.label.toLowerCase())
    .join(', ')
  const hero = route.sections.flatMap(s => s.sites).find(s => s.thumb)?.thumb
  const items = route.sections
    .flatMap(s => s.sites)
    .slice(0, 50)
    .map(
      (s, i) =>
        `{"@type": "ListItem", "position": ${i + 1}, "name": ${JSON.stringify(s.name)}, "url": "${BASE_URL}${encodeURI(s.path)}"}`,
    )
    .join(', ')
  return {
    title: `Archaeological Sites in ${route.country} (${route.total}) | Ancient Nerds`,
    description:
      `${route.total} curated archaeological sites in ${route.country}` +
      (namedTypes ? ` — ${namedTypes} and more` : '') +
      (route.periodSpan ? `. Spanning ${route.periodSpan}` : '') +
      '. Each with location, historical context and sources.',
    canonical,
    image: hero ? `${BASE_URL}${hero}` : undefined,
    schema:
      '{"@context": "https://schema.org", "@type": "ItemList", ' +
      `"name": ${JSON.stringify(`Archaeological Sites in ${route.country}`)}, ` +
      `"numberOfItems": ${route.total}, "itemListElement": [${items}]}`,
  }
}
```

Die übrigen acht (`storyMeta`, `storyArchiveMeta`, `siteMeta`, `sitesIndexMeta`, `researchMeta`, `researchIndexMeta`, `articleMeta`, `articleIndexMeta`) nach demselben Muster aus `pipeline/seo_pages.py` übernehmen. **Wichtig:** Der Title stand bisher als `f"{title} | Ancient Nerds"` in `_meta_head()` — das Suffix gehört jetzt in jede einzelne `*Meta`-Funktion, sonst fehlt es.

- [ ] **Step 5: Test laufen lassen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/meta.test.ts`
Expected: PASS

- [ ] **Step 6: Head-Gleichheit gegen Python prüfen**

Ein Vergleichstest pro Seitentyp, der die Python-Referenz aus Step 1 gegen `renderHead()` hält. Abweichungen sind erlaubt, müssen aber **bewusst** sein — jede Abweichung wird im Commit begründet.

Run:

```bash
cd C:/PythonProjects/AncientMap/ancient-nerds-map && node -e "
const {renderHead, countryMeta} = require('./dist-ssr/meta.cjs')
console.log(renderHead(countryMeta(require('./src/seo/__tests__/fixtures.json').country)))
" > /tmp/ts_country_head.txt; diff /tmp/ref_country_head.txt /tmp/ts_country_head.txt
```

Expected: keine oder ausschließlich begründete Unterschiede

- [ ] **Step 7: Commit**

```bash
git add ancient-nerds-map/src/seo
git commit -m "feat(seo): head tags in TypeScript, one definition per page type

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — SSR-Bundle und Node-Dienst

### Task 6: SSR-Entry und SSR-Build

**Files:**
- Create: `ancient-nerds-map/src/entry-server.tsx`
- Modify: `ancient-nerds-map/vite.config.ts`, `ancient-nerds-map/package.json`

- [ ] **Step 1: Test schreiben**

`ancient-nerds-map/src/seo/__tests__/entryServer.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'

import { render } from '../../entry-server'
import { FIXTURES } from './fixtures'

describe('render()', () => {
  it('liefert head und html für jeden Typ', () => {
    for (const payload of Object.values(FIXTURES)) {
      const out = render(payload as never)
      expect(out.head).toContain('<title>')
      expect(out.head.match(/<link rel="canonical"/g)).toHaveLength(1)
      expect(out.html.length).toBeGreaterThan(50)
    }
  })

  it('wirft bei unbekanntem Typ, statt leer zu liefern', () => {
    expect(() => render({ type: 'gibtsnicht' } as never)).toThrow(/unknown route type/)
  })
})
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd ancient-nerds-map && npx vitest run src/seo/__tests__/entryServer.test.tsx`
Expected: FAIL — Modul fehlt

- [ ] **Step 3: `entry-server.tsx` implementieren**

```tsx
/**
 * SSR-Einstieg. Bekommt das Route-Payload, liefert head und body-HTML.
 *
 * Kein Fallback bei unbekanntem Typ: ein Tippfehler im Payload muss laut
 * scheitern, nicht eine leere Seite ausliefern.
 */

import { renderToString } from 'react-dom/server'

import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import { RouteProvider } from './seo/RouteContext'
import { renderHead } from './seo/meta'
import { SeoRoute, registry } from './seo/registry'
import type { AnRoute } from './types/anRoute'

export function render(route: AnRoute): { head: string; html: string } {
  const entry = registry[route.type]
  if (!entry) throw new Error(`unknown route type: ${route.type}`)
  const html = renderToString(
    <RouteProvider value={route}>
      <AuthProvider>
        <OfflineProvider>
          <SeoRoute />
        </OfflineProvider>
      </AuthProvider>
    </RouteProvider>,
  )
  return { head: renderHead(entry.meta(route as never)), html }
}
```

- [ ] **Step 4: SSR-Build konfigurieren**

In `ancient-nerds-map/package.json` bei `"scripts"`:

```json
    "build:ssr": "vite build --ssr src/entry-server.tsx --outDir dist-ssr"
```

- [ ] **Step 5: Bauen und Tests**

Run: `cd ancient-nerds-map && npm run build:ssr && npx vitest run`
Expected: `dist-ssr/entry-server.js` entsteht, Tests grün

- [ ] **Step 6: Commit**

```bash
git add ancient-nerds-map/src/entry-server.tsx ancient-nerds-map/package.json ancient-nerds-map/vite.config.ts ancient-nerds-map/src/seo/__tests__/entryServer.test.tsx
git commit -m "feat(seo): server-side render entry for the indexed page types

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Der Node-Dienst

**Files:**
- Create: `ancient-nerds-map/ssr/server.mjs`, `Dockerfile.ssr`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Dienst implementieren**

`ancient-nerds-map/ssr/server.mjs`:

```js
/**
 * Rendert die indexierten Seiten serverseitig. Einziger Aufrufer: der API-Container.
 *
 * Bewusst ohne Framework — ein POST-Endpunkt und ein Healthcheck.
 */

import { createServer } from 'node:http'

import { render } from '../dist-ssr/entry-server.js'

const PORT = Number(process.env.SSR_PORT || 8500)

createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end('{"status":"ok"}')
    return
  }
  if (req.method !== 'POST' || req.url !== '/render') {
    res.writeHead(404).end()
    return
  }
  let body = ''
  req.on('data', c => (body += c))
  req.on('end', () => {
    try {
      const out = render(JSON.parse(body))
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(JSON.stringify(out))
    } catch (err) {
      // Laut scheitern: der API-Container macht daraus ein 502.
      res.writeHead(500, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ error: String(err && err.message ? err.message : err) }))
    }
  })
}).listen(PORT, () => console.log(`ssr listening on ${PORT}`))
```

- [ ] **Step 2: Dockerfile schreiben**

`Dockerfile.ssr` (nach dem Muster von `Dockerfile.webcam-proxy`):

```dockerfile
FROM node:20-slim

WORKDIR /app

COPY ancient-nerds-map/package.json ancient-nerds-map/package-lock.json ./
RUN npm ci --omit=dev

COPY ancient-nerds-map/dist-ssr ./dist-ssr
COPY ancient-nerds-map/ssr ./ssr

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser
USER appuser

EXPOSE 8500

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD node -e "fetch('http://localhost:8500/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "ssr/server.mjs"]
```

- [ ] **Step 3: Compose-Service ergänzen**

In `docker-compose.yml` nach dem `api`-Block:

```yaml
  ssr:
    build:
      context: .
      dockerfile: Dockerfile.ssr
    container_name: ancient_nerds_ssr
    restart: unless-stopped
    expose:
      - "8500"
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://localhost:8500/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
      interval: 30s
      timeout: 5s
      retries: 3
```

Beim `api`-Service ergänzen:

```yaml
    depends_on:
      ssr:
        condition: service_healthy
    environment:
      SSR_SERVICE_URL: http://ssr:8500
```

- [ ] **Step 4: Lokal hochfahren und prüfen**

```bash
cd C:/PythonProjects/AncientMap/ancient-nerds-map && npm run build:ssr
cd C:/PythonProjects/AncientMap && docker compose up -d --build ssr
curl -s -X POST http://localhost:8500/render -H 'content-type: application/json' \
  -d '{"type":"sitesIndex","countries":[{"name":"Denmark","count":42,"path":"/sites/denmark"}]}' | head -c 400
```

Expected: JSON mit `head` und `html`, `head` enthält `<title>Archaeological Sites by Country | Ancient Nerds</title>`

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/ssr Dockerfile.ssr docker-compose.yml
git commit -m "feat(seo): node sidecar that renders the indexed pages

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Der FastAPI-Client

**Files:**
- Create: `api/ssr_client.py`
- Test: `tests/api/test_ssr_client.py`

- [ ] **Step 1: Test schreiben**

`tests/api/test_ssr_client.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Der SSR-Dienst ist eine harte Abhängigkeit — Ausfall muss laut sein."""

from __future__ import annotations

import httpx
import pytest

from api.ssr_client import SsrUnavailableError, render_page


def test_returns_head_and_html(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/render"
        return httpx.Response(200, json={"head": "<title>x</title>", "html": "<div>y</div>"})

    monkeypatch.setattr(
        "api.ssr_client._client", httpx.Client(transport=httpx.MockTransport(handler))
    )
    head, html = render_page({"type": "sitesIndex", "countries": []})
    assert head == "<title>x</title>"
    assert html == "<div>y</div>"


def test_raises_loudly_when_the_service_is_down(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "api.ssr_client._client", httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(SsrUnavailableError):
        render_page({"type": "sitesIndex", "countries": []})


def test_raises_on_render_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "unknown route type: nope"})

    monkeypatch.setattr(
        "api.ssr_client._client", httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(SsrUnavailableError, match="unknown route type"):
        render_page({"type": "nope"})
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd C:/PythonProjects/AncientMap && python -m pytest tests/api/test_ssr_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.ssr_client'`

- [ ] **Step 3: Client implementieren**

`api/ssr_client.py`:

```python
"""
Client zum SSR-Sidecar.

Der Dienst ist eine harte Abhängigkeit, kein Bonus: fällt er aus, sollen die
indexierten Routen mit 502 antworten. Ein Rückfall auf einen zweiten Renderer
wäre genau die Doppelung, die dieser Umbau beseitigt.
"""

import os

import httpx

SSR_SERVICE_URL = os.getenv("SSR_SERVICE_URL", "http://ssr:8500")

_client = httpx.Client(base_url=SSR_SERVICE_URL, timeout=10.0)


class SsrUnavailableError(RuntimeError):
    """Der SSR-Dienst hat nicht geliefert — Betriebsfehler, nicht Anfragefehler."""


def render_page(route: dict) -> tuple[str, str]:
    """Rendert ein Route-Payload. Liefert (head, html)."""
    try:
        response = _client.post("/render", json=route)
    except httpx.HTTPError as exc:
        raise SsrUnavailableError(f"SSR service at {SSR_SERVICE_URL} unreachable: {exc}") from exc

    if response.status_code != 200:
        detail = response.json().get("error", response.text) if response.content else response.text
        raise SsrUnavailableError(f"SSR render failed: {detail}")

    data = response.json()
    return data["head"], data["html"]
```

- [ ] **Step 4: Test laufen lassen**

Run: `cd C:/PythonProjects/AncientMap && python -m pytest tests/api/test_ssr_client.py -q`
Expected: PASS, 3 Tests

- [ ] **Step 5: 502 statt 500 ausliefern**

In `api/main.py` einen Exception-Handler registrieren:

```python
from api.ssr_client import SsrUnavailableError


@app.exception_handler(SsrUnavailableError)
async def ssr_unavailable_handler(request, exc):
    logger.error("SSR service unavailable: %s", exc)
    return Response(status_code=502, content="Renderer unavailable", media_type="text/plain")
```

- [ ] **Step 6: Commit**

```bash
git add api/ssr_client.py api/main.py tests/api/test_ssr_client.py
git commit -m "feat(seo): fastapi client for the ssr sidecar

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Cutover, Seitentyp für Seitentyp

Reihenfolge nach Risiko: die kleinste Fläche zuerst, die Story-Seiten (2.248 indexierte URLs) zuletzt.

### Task 9: `shell_response()` auf SSR umstellen

**Files:**
- Modify: `api/seo_shell.py`
- Test: `tests/api/test_seo_shell.py`

- [ ] **Step 1: Test schreiben**

`tests/api/test_seo_shell.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""shell_response spliced jetzt SSR-Ausgabe in die gebaute Shell."""

from __future__ import annotations

from api import seo_shell


def test_splices_ssr_output(monkeypatch, tmp_path):
    monkeypatch.setattr(seo_shell, "render_page", lambda route: ("<title>T</title>", "<p>B</p>"))
    monkeypatch.setattr(
        seo_shell, "render_app_shell", lambda entry, **kw: f"{kw['head_html']}|{kw['root_html']}"
    )
    resp = seo_shell.shell_response("site.html", {"type": "sitesIndex", "countries": []}, {})
    assert resp.body.decode() == "<title>T</title>|<p>B</p>"
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/api/test_seo_shell.py -q`
Expected: FAIL — Signatur passt nicht

- [ ] **Step 3: `shell_response()` umschreiben**

`api/seo_shell.py`:

```python
"""Serviert eine indexierte Seite: SSR-Ausgabe in die gebaute App-Shell gespliced."""

import json

from fastapi import Response

from api.ssr_client import render_page
from pipeline.app_shell import render_app_shell


def shell_response(entry: str, route: dict, headers: dict[str, str]) -> Response:
    """Rendert route über den SSR-Dienst und liefert das vollständige Dokument."""
    head, body = render_page(route)
    html = render_app_shell(
        entry,
        head_html=head,
        root_html=body,
        route=json.dumps(route, ensure_ascii=False).replace("<", "\\u003c"),
    )
    return Response(content=html, media_type="text/html", headers=headers)
```

- [ ] **Step 4: Test laufen lassen**

Run: `python -m pytest tests/api/test_seo_shell.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/seo_shell.py tests/api/test_seo_shell.py
git commit -m "refactor(seo): shell_response renders through the ssr service

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: `/sites/` und `/sites/{country}` umstellen

Diese beiden zuerst: sie werden bereits vollständig aus dem Payload gespeist, hier ist die Abweichung zwischen SSR und React nachweislich null.

**Files:**
- Modify: `api/routes/sites_html.py:61`, `:108`
- Test: `tests/api/test_sites_html_ssr.py`

- [ ] **Step 1: Test schreiben**

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Die Länderrouten übergeben Payload-Dicts, kein vorgerendertes HTML mehr."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_country_route_hands_a_payload_to_the_renderer():
    with patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>y</p>")) as m:
        TestClient(app).get("/sites/denmark")
    route = m.call_args[0][0]
    assert route["type"] == "country"
    assert route["country"] == "Denmark"
    assert route["sections"]
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/api/test_sites_html_ssr.py -q`
Expected: FAIL

- [ ] **Step 3: Routen umstellen**

In `api/routes/sites_html.py` die Gruppierung aus `seo_pages.type_sections()` **nach Python-seitig** verschieben oder — sauberer — das Payload roh übergeben und die Gruppierung in `registry`/`meta.ts` erledigen. Empfehlung: die Gruppierung wandert nach TypeScript, weil sie eine Darstellungsentscheidung ist. `sites_html.py` liefert dann nur noch die flache Liste:

```python
    return shell_response(
        "site.html",
        {
            "type": "country",
            "country": country,
            "sites": sites,
        },
        _HTML_HEADERS,
    )
```

Die Portierung von `type_sections()`, `_period_span()` und `blurb()` nach `src/seo/grouping.ts` gehört in diesen Task — mit den Tests aus `tests/pipeline/test_seo_country_extras.py` als Vorlage, eins zu eins nach Vitest übersetzt.

- [ ] **Step 4: Tests und Live-Vergleich**

Run:

```bash
python -m pytest tests/api/test_sites_html_ssr.py -q
docker compose up -d --build api ssr
curl -s http://localhost:8000/sites/denmark | grep -c '<h1'
```

Expected: Tests grün, genau ein `<h1>`

- [ ] **Step 5: Commit**

```bash
git add api/routes/sites_html.py ancient-nerds-map/src/seo tests/
git commit -m "refactor(seo): country pages render through react

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: `site` — die Detailseiten (5.012 URLs)

Der größte Brocken: das Payload trägt heute **nur** `{"id": "..."}`, alles andere holt `useSiteDetailData()` per Effekt nach. Für SSR muss alles ins Payload, was `site_detail_page()` heute rendert.

**Files:**
- Modify: `api/routes/sites_html.py:181`
- Modify: `ancient-nerds-map/src/types/anRoute.ts`, `src/pages/SitePage.tsx`
- Test: `tests/api/test_sites_html_ssr.py` (erweitern), `src/seo/__tests__/render.test.tsx`

- [ ] **Step 1: Test schreiben**

An `tests/api/test_sites_html_ssr.py` anhängen:

```python
def test_site_detail_hands_the_full_payload():
    with patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>y</p>")) as m:
        TestClient(app).get("/sites/denmark/borremose-5281654c")
    route = m.call_args[0][0]
    assert route["type"] == "site"
    for key in ("name", "country", "siteType", "period", "description", "coords", "image",
                "altNames", "news", "links", "parent", "siblings"):
        assert key in route, key
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/api/test_sites_html_ssr.py -q`
Expected: FAIL — `assert 'name' in route`

- [ ] **Step 3: Payload in `sites_html.py:181` vollständig füllen**

Die Feldliste steht in `pipeline/seo_pages.py::site_detail_page()` (ab Zeile 498) und `_related_content()` (`api/routes/sites_html.py:186-263`). `_related_content()` liefert die verwandten Daten bereits vollständig — sie flossen bisher nur ins HTML statt ins Payload:

```python
    return shell_response(
        "site.html",
        {
            "type": "site",
            "id": row.id,
            "name": row.name,
            "country": row.country,
            "siteType": row.site_type or "Archaeological site",
            "period": _period_display_dict(row),
            "description": row.description or "",
            "coords": {"lat": row.lat, "lon": row.lon},
            **_related_content(row, db),
        },
        _HTML_HEADERS,
    )
```

- [ ] **Step 4: `anRoute.ts` erweitern**

Den `{ type: 'site'; id: string }`-Zweig durch die vollständige Form ersetzen — Feldnamen exakt wie im Payload aus Step 3.

- [ ] **Step 5: `SitePage.tsx` auf das Payload umstellen**

`useSiteDetailData()` wird für den SSR-Pfad nicht mehr gebraucht — die Daten stehen im Kontext. Der Hook bleibt für den Globus-Popup-Pfad, der ihn ebenfalls benutzt; nur `SitePage` liest jetzt `useRoute()`.

- [ ] **Step 6: Rendertest ergänzen und alles laufen lassen**

Run: `cd ancient-nerds-map && npx vitest run && cd .. && python -m pytest tests/api -q`
Expected: alles grün

- [ ] **Step 7: Live prüfen**

```bash
docker compose up -d --build api ssr
curl -s http://localhost:8000/sites/denmark/borremose-5281654c | grep -c '<h1\|rel="canonical"'
```

Expected: `2` — genau ein `<h1>` und genau ein Canonical

- [ ] **Step 8: Commit**

```bash
git add api/routes/sites_html.py ancient-nerds-map/src tests/
git commit -m "refactor(seo): site detail pages render through react

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: `research` + `researchIndex` (14 URLs)

**Files:**
- Modify: `api/routes/research_html.py:61`, `:98`
- Modify: `ancient-nerds-map/src/types/anRoute.ts`, `src/pages/ResearchPaperPage.tsx`
- Test: `tests/api/test_research_html_ssr.py`

- [ ] **Step 1: Test schreiben**

```python
# SPDX-License-Identifier: AGPL-3.0-only
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_research_paper_hands_the_full_payload():
    with patch("api.seo_shell.render_page", return_value=("<t>x</t>", "<p>y</p>")) as m:
        TestClient(app).get("/research/the-squatter-man-petroglyph-and-auroral-sky-mythology")
    route = m.call_args[0][0]
    assert route["type"] == "research"
    for key in ("slug", "title", "summary", "author", "publishedAt", "bodyHtml"):
        assert key in route, key


def test_research_index_hands_the_paper_list():
    with patch("api.seo_shell.render_page", return_value=("<t>x</t>", "<p>y</p>")) as m:
        TestClient(app).get("/research/")
    route = m.call_args[0][0]
    assert route["type"] == "researchIndex"
    assert isinstance(route["papers"], list)
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/api/test_research_html_ssr.py -q`
Expected: FAIL

- [ ] **Step 3: Routen umstellen**

`bodyHtml` bleibt serverseitig gerendertes Markdown (Python-`markdown`) — der Markdown-Renderer wird bewusst **nicht** vereinheitlicht, siehe Audit-Abschnitt „Nicht tun". Das Payload trägt das fertige HTML, React setzt es wie heute per `dangerouslySetInnerHTML`.

- [ ] **Step 4: `researchIndex` bekommt eine echte Seite**

Heute wirft `researchMain.tsx` den Besucher per `window.location.replace` auf `/theo.html`. Das entfällt (Task 2) — `researchIndex` braucht jetzt eine echte Listenkomponente. Die einfachste korrekte Form ist eine Liste der Papers mit Titel, Zusammenfassung und Link, analog `SitesIndexPage`.

- [ ] **Step 5: Tests, Live-Prüfung, Commit**

Run: `python -m pytest tests/api -q && cd ancient-nerds-map && npx vitest run`

```bash
git add api/routes/research_html.py ancient-nerds-map/src tests/
git commit -m "refactor(seo): research pages render through react

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: `article` + `articleIndex` (19 URLs)

**Files:**
- Modify: `api/routes/articles_html.py:68`, `:90`
- Modify: `ancient-nerds-map/src/types/anRoute.ts`, `src/pages/ArticlesPage.tsx`
- Test: `tests/api/test_articles_html_ssr.py`

- [ ] **Step 1: Test schreiben**

```python
# SPDX-License-Identifier: AGPL-3.0-only
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_article_hands_the_full_payload():
    with patch("api.seo_shell.render_page", return_value=("<t>x</t>", "<p>y</p>")) as m:
        TestClient(app).get("/articles/weekly-archaeological-digest")
    route = m.call_args[0][0]
    assert route["type"] == "article"
    for key in ("slug", "title", "summary", "publishedAt", "bodyHtml"):
        assert key in route, key


def test_article_index_hands_the_list():
    with patch("api.seo_shell.render_page", return_value=("<t>x</t>", "<p>y</p>")) as m:
        TestClient(app).get("/articles/")
    route = m.call_args[0][0]
    assert route["type"] == "articleIndex"
    assert isinstance(route["articles"], list)
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/api/test_articles_html_ssr.py -q`
Expected: FAIL

- [ ] **Step 3: Routen umstellen und `ArticlesPage` entzweien**

`ArticlesPage.tsx` ist mit 962 Zeilen die größte Komponente und macht heute **beides**: Liste und Einzelartikel, umgeschaltet über `window.location.hash`. Für die Registry braucht es zwei Einstiegspunkte. Sauberste Form ohne Umbau des Innenlebens: zwei dünne Wrapper im selben Modul, die `view` aus dem Route-Typ ableiten statt aus dem Hash.

- [ ] **Step 4: Der doppelte Canonical verschwindet hier von selbst**

`/articles/*` liefert heute zwei `<link rel="canonical">`, weil `_strip_default_head_tags()` in `app_shell.py` nur `title`/`meta` entfernt, nicht `<link>`. Nach dem Cutover kommt der Head aus `renderHead()` — trotzdem bleibt der Canonical der **gebauten** `articles.html` im Shell-Head stehen. Deshalb in `pipeline/app_shell.py::_strip_default_head_tags()` die Regex um `<link rel="canonical">` erweitern:

```python
    head = re.sub(r'<link\s+rel="canonical"[^>]*/?>\s*', "", head, flags=re.IGNORECASE)
```

Test dazu in `tests/pipeline/test_app_shell.py` (die Datei stirbt erst in Task 16):

```python
def test_only_one_canonical_survives(shell_dir):
    html = _render(head='<link rel="canonical" href="https://ancientnerds.com/articles/">')
    assert html.count('rel="canonical"') == 1
```

- [ ] **Step 5: Tests, Live-Prüfung, Commit**

```bash
curl -s http://localhost:8000/articles/ | grep -c 'rel="canonical"'   # muss 1 sein
git add api/routes/articles_html.py pipeline/app_shell.py ancient-nerds-map/src tests/
git commit -m "refactor(seo): journal pages render through react, one canonical

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: `story` + `storyArchive` (2.248 URLs) — zuletzt

Hier liegt der gesamte Suchtraffic (508 der 614 Seiten mit Impressionen). Deshalb als letztes, wenn das Verfahren an den anderen acht Typen bewiesen ist.

**Files:**
- Modify: `api/routes/articles_html.py:173`, `:280`
- Test: `tests/api/test_story_html_ssr.py`

- [ ] **Step 1: Test schreiben**

```python
# SPDX-License-Identifier: AGPL-3.0-only
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_story_hands_the_full_payload():
    with patch("api.seo_shell.render_page", return_value=("<t>x</t>", "<p>y</p>")) as m:
        TestClient(app).get("/news-archive/aesir-etymology-gods-of-the-great-pole-or-asia-5072")
    route = m.call_args[0][0]
    assert route["type"] == "story"
    for key in ("headline", "summary", "facts", "postText", "sources", "related", "siteName"):
        assert key in route, key


def test_story_archive_keeps_its_pagination():
    with patch("api.seo_shell.render_page", return_value=("<t>x</t>", "<p>y</p>")) as m:
        TestClient(app).get("/news-archive/page/2")
    route = m.call_args[0][0]
    assert route["type"] == "storyArchive"
    assert route["page"] == 2
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/api/test_story_html_ssr.py -q`
Expected: FAIL

- [ ] **Step 3: Routen umstellen**

Das `story`-Payload ist bereits das vollständigste im ganzen System (`_route_json("story", payload)`, `seo_pages.py:447-490`) — es trägt schon Quellen, Related, Screenshot und Speculative-Tag. Hier ist am wenigsten zu ergänzen.

- [ ] **Step 4: Vor/Nach-Vergleich an einer echten Story**

```bash
curl -s http://localhost:8000/news-archive/aesir-etymology-gods-of-the-great-pole-or-asia-5072 > /tmp/nachher.html
grep -c '<h1\|rel="canonical"\|an-src\|story-chip' /tmp/nachher.html
```

Expected: keine Regression gegenüber dem heutigen Stand; insbesondere müssen Quellenblock und Globus-Chip vorhanden sein.

- [ ] **Step 5: Commit**

```bash
git add api/routes/articles_html.py tests/
git commit -m "refactor(seo): story pages render through react

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Hydration und Abriss

### Task 15: `hydrateRoot` statt `createRoot`

Erst wenn alle neun Typen über SSR laufen. Vorher würde React das Server-Markup als Fehler melden.

**Files:**
- Modify: `ancient-nerds-map/src/{story,site,research,articles}Main.tsx`

- [ ] **Step 1: Umstellen**

In allen vier Entries:

```tsx
import { hydrateRoot } from 'react-dom/client'

hydrateRoot(
  document.getElementById('root')!,
  <React.StrictMode>
    <RouteProvider value={route}>
      <AuthProvider>
        <OfflineProvider>
          <SeoRoute />
        </OfflineProvider>
      </AuthProvider>
    </RouteProvider>
  </React.StrictMode>,
)
```

- [ ] **Step 2: Auf Hydration-Warnungen prüfen**

```bash
cd ancient-nerds-map && node -e "
const puppeteer=require('puppeteer');
(async()=>{
 const b=await puppeteer.launch({args:['--no-sandbox']});
 const p=await b.newPage();
 const errs=[];
 p.on('console', m => { if(m.type()==='error') errs.push(m.text()) });
 for (const u of ['/sites/denmark','/sites/','/news-archive/']) {
   await p.goto('http://localhost:8000'+u,{waitUntil:'networkidle2'});
   await new Promise(r=>setTimeout(r,1500));
 }
 console.log(JSON.stringify(errs,null,1));
 await b.close();
})()"
```

Expected: `[]` — jede Hydration-Warnung ist eine echte Abweichung zwischen Server und Browser und muss behoben werden, nicht unterdrückt.

- [ ] **Step 3: Prüfen, dass der Inhalt die Hydration überlebt**

```bash
cd ancient-nerds-map && node scripts/shoot_country.cjs http://localhost:8000/sites/denmark /tmp/hydrated.png
```

Expected: `sections` und `cards` vor und nach der Hydration identisch; im Audit vom 09.08. gingen auf den Detailseiten 37 → 12 Links verloren, das darf nicht mehr passieren.

- [ ] **Step 4: Commit**

```bash
git add ancient-nerds-map/src
git commit -m "feat(seo): hydrate the server markup instead of replacing it

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: `seo_pages.py` löschen

**Files:**
- Delete: `pipeline/seo_pages.py`, `tests/pipeline/test_app_shell.py`, `tests/pipeline/test_seo_story_extras.py`, `tests/pipeline/test_seo_country_extras.py`
- Modify: `pipeline/app_shell.py` (bleibt — spliced weiterhin die Shell)

- [ ] **Step 1: Prüfen, dass niemand mehr importiert**

Run: `cd C:/PythonProjects/AncientMap && grep -rn "seo_pages" --include=*.py . | grep -v ".venv"`
Expected: keine Treffer außer den zu löschenden Testdateien

- [ ] **Step 2: Lebende Helfer retten**

`AI_NOTICE_HTML` (die einzige Stelle im Repo, die `data-ai-generated` setzt — Art.-50-relevant) und `markdown_to_html` leben in `pipeline/article_html_renderer.py`, nicht in `seo_pages.py`. Vor dem Löschen bestätigen:

Run: `grep -rn "AI_NOTICE_HTML\|markdown_to_html" --include=*.py . | grep -v ".venv" | grep -v seo_pages`
Expected: Treffer in `article_html_renderer.py` und den verbleibenden Aufrufern

Der Art.-50-Hinweis muss in React nachgezogen sein — sonst ist das Löschen ein Compliance-Rückschritt. Prüfen, dass `AiNoticeBanner` auf allen KI-generierten Seitentypen gerendert wird.

- [ ] **Step 3: Löschen**

```bash
git rm pipeline/seo_pages.py tests/pipeline/test_app_shell.py tests/pipeline/test_seo_story_extras.py tests/pipeline/test_seo_country_extras.py
```

- [ ] **Step 4: Volle Gates**

Run:

```bash
cd C:/PythonProjects/AncientMap && ruff format --check pipeline/ api/ tests/ && ruff check pipeline/ api/ tests/ && lint-imports && python -m pytest tests/ -q -m "not integration and not live_llm"
cd ancient-nerds-map && npm run type-check && npx vitest run && npm run build && npm run build:ssr && npx knip --no-progress --include files,dependencies,devDependencies
```

Expected: alles grün

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(seo): delete the python renderer

Every indexed page is now described exactly once, as a React component.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: Deploy

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: SSR-Build und Container in den Deploy aufnehmen**

Im Deploy-Block nach `npm run build`:

```bash
              npm run build:ssr
```

und bei `docker compose up`:

```bash
              docker compose up -d --build ssr api
```

- [ ] **Step 2: Health-Gate ergänzen**

Nach dem bestehenden API-Healthcheck:

```bash
              curl -fsS http://localhost:8000/sites/denmark | grep -q '<h1' || { echo "SSR liefert kein h1"; exit 1; }
```

- [ ] **Step 3: Reihenfolge prüfen**

Der `ssr`-Container muss vor `api` gesund sein (`depends_on: condition: service_healthy` aus Task 7). Und: der Worker-Skip aus `project-theo-worker-container` darf nicht gebrochen werden — den Deploy-Block vor dem Push gegen `docs/` gegenlesen.

- [ ] **Step 4: Commit und Freigabe einholen**

Kein Push ohne ausdrückliche Zustimmung.

---

## Risiken

| Risiko | Umgang |
|---|---|
| **Neuer Single Point of Failure.** Fällt der SSR-Container aus, liefern alle 7.404 indexierten URLs 502. | Healthcheck + `depends_on: service_healthy` + Deploy-Gate. Bewusst kein Fallback-Renderer — der wäre die Doppelung, die wir beseitigen. |
| **Latenz pro Anfrage.** `renderToString` für `/sites/england` (1.053 Karten) kann spürbar dauern. | Vor dem Cutover messen: `curl -w '%{time_total}'` gegen den lokalen Container. Über 300 ms → Renderer-Cache (die Daten ändern sich selten) in einem eigenen Task, nicht hier. |
| **Hydration-Abweichungen.** Server- und Browser-Markup müssen identisch sein, sonst verwirft React alles. | Task 15 Step 2 macht Konsolenfehler zum harten Gate. |
| **`ArticlesPage`/`ResearchPaperPage` sind groß** (962 bzw. 672 Zeilen) und laden Daten per Effekt nach. | Ihre Payloads in Task 12/13 vollständig füllen. Wenn das zu weit trägt: diese beiden Typen zuletzt und notfalls in einem eigenen Plan. |
| **Art.-50-Kennzeichnung.** `AI_NOTICE_HTML` ist heute die einzige Stelle mit `data-ai-generated`. | Task 16 Step 2 prüft das vor dem Löschen. Der Audit vom 09.08. hat bereits eine Lücke auf `/news-archive/` gefunden — die muss vorher zu sein. |
| **Build-Zeit im Deploy** steigt um den SSR-Build. | Messen; `dist-ssr` ist klein (nur die SEO-Seiten, nicht der Globus). |

---

## Was dieser Plan **nicht** tut

- **Globus, Landing, Suche, Library, Knowledge, Radar, Cards, Game, Theo, Lyra** werden nicht angefasst. Sie bleiben reine Client-Apps.
- **Keine URL-Änderung**, keine Sitemap-Änderung, keine nginx-Änderung. Die Umstellung ist von außen unsichtbar — außer dass das Markup nicht mehr ausgetauscht wird.
- **Keine der SEO-Quickwins** aus `docs/reports/2026-08-09-seo-audit.md` (Discord-CTA, gzip, 404-Links, Titles). Die sind unabhängig und sollten **vorher** laufen — sie wirken sofort, dieser Umbau wirkt erst am Ende.
