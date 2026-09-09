# Landingpage: Live-Sektionen für Stories, Journals und Research Papers

Datum: 2026-09-09 · Status: Entwurf zur Freigabe · Recherche: `docs/superpowers/research/2026-09-09-landing-page-research.md`

## 1. Ziel

Die Startseite zeigt heute 36 Screenshots und kein einziges interaktives Element. Sie bekommt drei
Sektionen mit echten, aktuellen Inhalten direkt unter dem Hero, in der Reihenfolge Stories, Journals,
Research Papers. Der Hero mit dem Globus-Video bleibt unverändert. Die bestehenden Screenshot-Abschnitte
bleiben darunter erhalten, abzüglich der beiden, die durch Live-Sektionen ersetzt werden.

Entscheidungen aus dem Brainstorming (09.09.2026):

- Hero: Globus-Video oben, wie heute. Kein Mini-Globus, keine Suchbox, keine Umgestaltung des Layouts.
  Drei SEO-Ergänzungen (Freigabe 09.09.): die H1 trägt den Suchbegriff, ein Intro-Absatz kommt unter
  den Hero, und die veraltete Zahl "750K+" wird überall durch die echte Größenordnung ersetzt (3.6).
- Stories: Variante "Lead-Karte plus Liste". Eine große Story, daneben sechs kompakte Zeilen.
- Journals und Papers: zwei eigene Sektionen, jeweils Lead plus Liste.
- Kein eigener Abschnitt für Globus-Fähigkeiten. Die vorhandenen Screenshot-Sektionen decken das ab.
- Lyra-Live-Demo, Bento-Umbau, Performance-Gates per Lighthouse: nicht in diesem Vorhaben.

## 2. Seitenaufbau

1. Hero (Layout unverändert, H1 und Zahlen siehe 3.6)
2. Intro-Absatz (statisch, siehe 3.6)
3. `>_ [ fig. 1 — stories, live ]`
4. `>_ [ fig. 2 — weekly journal ]`
5. `>_ [ fig. 3 — research papers ]`
6. Bestehende Sektionen in heutiger Reihenfolge: Globe, Filter, Empires (cinematic), Site data, Lyra,
   Radar, Tools, Sources, API, Founders, Discord, Giants, Browse (Länder-Hubs und Paper-Liste), Final CTA, Footer.

Entfernt werden die Screenshot-Karte "Archaeology Stories" (Split-Row mit Radar) und die Sektion
"Weekly Journals". Die Radar-Karte wird zur normalen Feature-Row in der Breite der anderen Sektionen.
Die Paper-Liste in der Browse-Sektion bleibt: sie verlinkt alle 24 Papers für Suchmaschinen, die neue
Sektion zeigt nur sechs.

## 3. Architektur

### 3.1 Auslieferung: SSR über den Sidecar, statisches HTML als Rückfall

Die Startseite wird der zehnte Seitentyp über den bestehenden React-SSR-Pfad. Das ist der Weg, den
`/sites/`, `/research/`, `/news-archive/` und `/articles/` schon gehen. Es gibt keinen zweiten Renderer.

- `index.html` bekommt zwischen Hero und den Screenshot-Sektionen ein `<div id="root"></div>`.
  Alles außerhalb bleibt statisches HTML wie heute.
- Neue API-Route `GET /home` (Router `api/routes/landing_html.py`). Sie baut das Route-Payload
  `{type: "landing", ...}` aus der Datenbank, ruft `ssr_shell_response("index.html", route, headers)`
  und liefert das Dokument. `render_app_shell` setzt den gerenderten Baum in `#root` und
  `window.__AN_ROUTE__`, genau wie bei den anderen Seiten.
- Die Route hält das fertige HTML als Bytes 300 Sekunden im Prozess-Cache (nicht das Response-Objekt: die
  Gzip-Middleware verändert dessen Header in-place) und sendet
  `Cache-Control: public, max-age=300`. Bei rund 200 Aufrufen am Tag reicht das; kein nginx-Cache nötig.
- nginx: `location = /` proxied auf `http://an_api/home` statt `try_files /index.html`. Die bestehende
  `$arg_site`-Weiterleitung bleibt davor. Für diesen Block gilt `error_page 502 504 = @home_static`, und
  `@home_static` liefert `/index.html` aus `dist/`; `proxy_intercept_errors on` fängt auch die 500/502, die
  die API selbst sendet, und `error_page 500 502 504` deckt eine Exception in der Route ab. Während der Deploy-Fenster (gemessen 87 bis 110 s)
  bleibt die Startseite damit erreichbar, nur die drei Live-Sektionen sind leer.
- `GET /` der API bleibt der Health-Check. `/home` ist nur intern erreichbar: nginx leitet `/home` von
  außen weiterhin auf die SPA-Fallback-Regel, es entsteht keine zweite URL für dieselbe Seite.
- Service Worker: `/^\/$/` kommt in `navigateFallbackDenylist`. Ohne das würde Workbox
  wiederkehrenden Besuchern das vorgecachte `index.html` statt der frischen SSR-Seite geben.
- Head: `landingMeta` in `src/seo/meta.ts` liefert Titel, Description, Canonical, OG- und
  Twitter-Tags mit den heutigen Texten. `_strip_default_head_tags` entfernt die Duplikate aus der Shell, die drei
  JSON-LD-Blöcke bleiben in `index.html`.

Warum nicht Build-Zeit-Snapshot plus Client-Refresh: die Karten wären so frisch wie der letzte Deploy,
und der Austausch nach dem Laden erzeugt einen sichtbaren Sprung. Warum nicht die App als Startseite:
2,5 MB JavaScript und ein 87-MB-Index haben auf einer Startseite nichts verloren.

### 3.2 Client: eine Insel, keine Ganzseiten-Hydration

- Neuer Vite-Entry `src/landingMain.tsx`, eingebunden in `index.html`. Er liest `readInjectedRoute()`,
  hydratisiert `#root` mit `SeoRoute` und ist damit das Gegenstück zu `siteMain.tsx`. Ohne Payload
  (statischer Rückfall) rendert er nichts und wirft nicht.
- Registry: `landing: { Component: LandingLive, meta: meta.landingMeta }` in `src/seo/registry.tsx`,
  `LandingRoute` in `src/types/anRoute.ts`.
- Es hydratisiert nur `#root`. Hero und Screenshot-Sektionen bleiben reines HTML ohne React.
- Budget für das seitenspezifische JS (`landing-*.js` + `LandingLive-*.js`): 40 kB Brotli, gemessen
  per `size-limit`; react-dom ist ein geteilter Chunk und zählt nicht mit (Stand 09.09.: 3,4 kB). Nichts aus `three`, nichts aus `SitePopup`, kein `NewsCard` (447 Zeilen, Inline-Video,
  Share-Logik: zu schwer für eine Vorschau).
- LCP bleibt Logo und Hero-Poster. `#root` reserviert seine Höhe nicht, weil der Inhalt serverseitig
  vollständig ankommt; Bilder tragen `width`/`height` und `aspect-ratio`, damit nichts springt.

### 3.3 Daten: das Route-Payload

Alles wird serverseitig in `landing_html.py` gesammelt und im Payload mitgegeben. Der Client braucht
für den ersten Paint keinen einzigen API-Aufruf.

```
LandingRoute {
  type: 'landing'
  stats:    { sites: number, stories: number, journals: number, papers: number }
  stories:  { lead: StoryData, rail: StoryData[], categories: string[] }
  journals: { lead: JournalLead, rail: JournalTeaser[], total: number }
  papers:   { lead: PaperLead, rail: PaperTeaser[], total: number, theo: TheoStatus | null }
}
StoryData     = Omit<StoryRoute, 'type'> — dasselbe Payload wie /news-archive/{slug}
JournalTeaser { id, title, summary, week_start, week_end, published_at, words, minutes,
                sections: string[], sources, image_url | null, path }
JournalLead   = JournalTeaser & { body_html, excerpted }
PaperTeaser   { slug, title, summary, published_at, words, minutes, sources_analyzed,
                quality_score, hero_image_url | null, path }
PaperLead     = PaperTeaser & { body_html, excerpted, author | null }
TheoStatus    { question, started_at, sites_found }
```

Regeln:

- **Stories.** Der öffentliche Story-Index (`public_stories_query`: post_text vorhanden, keine
  spekulativen Stories, weil die noindex sind) plus die Signifikanz-Untergrenze des Feeds (≥ 2 oder
  null), neueste zuerst. Seit 2026-09-10 sind das keine Teaser mehr, sondern **ganze
  Story-Payloads**: `articles_html.story_payload(row, related=[])` baut sie — dieselbe Funktion, die
  `/news-archive/{slug}` bedient, damit Fenster und Seite nicht auseinanderlaufen können. `related`
  bleibt leer; eine "Weiterlesen"-Liste im Fenster führte nirgendwohin. Der Lead ist die Story mit
  der höchsten Signifikanz der letzten 48 Stunden, bei Gleichstand die neuere. Gibt es in 48 Stunden
  keine, ist der Lead die höchste Signifikanz unter den 7 neuesten. Die Liste sind die 7 neuesten
  ohne den Lead, gekürzt auf 6 Zeilen. Sichtbar sind also immer 7 Stories: die im Fenster plus
  sechs in der Liste. Die Story-URL leitet der Client aus `headline` und `id` ab (`storyPath`, die
  TS-Seite von `story_slug`); `categories` sind die Kategorien mit mindestens einer Story in den
  letzten 30 Tagen.
- **Journals.** Die 4 neuesten aktiven Artikel nach `week_start`. `words` zählt den Inhalt,
  `minutes` ist `words / 238` aufgerundet, `sections` sind die `##`-Überschriften ohne "Sources" und
  "Videos", `sources` zählt die Links, `image_url` ist der erste Screenshot im Inhalt.
  `path` ist `/articles/{slugify(title)}`, wie in `articles_html.py`. Der Lead trägt seit
  2026-09-10 zusätzlich `body_html`: dieselbe `markdown_to_html(row.content)`-Ausgabe wie
  `/articles/{slug}`, gekürzt durch `excerpt_html()`.
- **Papers.** Die 6 neuesten nach `published_at` unter `PUBLIC_PAPER_WHERE` mit den
  `PAPER_SUMMARY_COLUMNS`. Der Lead ist das neueste. `theo` kommt aus derselben Abfrage, die
  `/api/theo/research/current` benutzt (laufender Batch-Request: Frage, Startzeit, gefundene Sites);
  die Funktion wird importiert, nicht kopiert. Der Lead trägt seit 2026-09-10 zusätzlich `author`
  und `body_html`: `research_html.fetch_paper(slug)` holt den Report nach — die Summary-Spalten
  tragen keinen Text —, `report_markdown()` bereitet ihn genau wie auf der Paperseite auf.
- **Der Auszug (2026-09-10).** `excerpt_html(html, max_chars=2500)` schneidet direkt hinter dem
  ersten Block auf oberster Ebene, dessen Ende den sichtbaren Text über die Grenze schiebt
  (`p, h2, h3, h4, ul, ol, figure, blockquote, pre, table`). Für `ul/ol/blockquote/figure/table`
  wird die Verschachtelungstiefe mitgezählt, damit der Schnitt nie zwischen zwei `<li>` oder
  zwischen `<img>` und `<figcaption>` landet; er liegt immer hinter einem schließenden Tag, nie
  mitten in einem. Zurück kommt `(html, excerpted)`. `excerpted` ist `false`, wenn nichts wegfiel —
  der "continue reading"-Link darf keinen Text versprechen, den es nicht gibt.
- **Stats.** `sites` aus der gecachten `/api/stats`-Logik, `stories` und `journals` aus
  `get_news_stats`, `papers` per Count unter `PUBLIC_PAPER_WHERE`.

Fehlt eine Datenquelle (kein Journal, kein Paper, kein laufender Theo), fehlt die Sektion oder die
Zeile im Payload und wird nicht gerendert. Es gibt keine Platzhalter-Inhalte.

### 3.4 Interaktion in der Stories-Sektion

- Die Sektion ist ein **NERV-Fenster, in dem die Story-Seite läuft**: Titelleiste (`>_ stories.log
  — {Headline}`, rechts die Fensterknöpfe aus `nerv-ui/window.css`), links der Artikel als
  `<StoryArticle compact headingLevel="h3">` — Headline, Meta-Zeile, Standbild, Fließtext, Key
  facts, Site-Chips, Quellen, Art.-50-Fußnote —, rechts die Liste der übrigen Stories. Ein Klick auf
  eine Zeile tauscht den Fensterinhalt, ohne die Seite zu wechseln.
- **SEO:** jede Zeile ist ein echter `<a>` auf `/news-archive/{slug}`; der Tausch ist ein
  `onClick`, der nur einen unmodifizierten Linksklick abfängt. Crawler, Mittelklick und Strg-Klick
  bekommen den Link. Serverseitig steht der Artikel des Leads komplett im HTML, die Zeile des Leads
  trägt `aria-current="true"`. Die Sektionsüberschrift bleibt das einzige `h2` über der Story, deren
  Headline ein `h3` ist — kein `h1` in `#root`.
- Kategorie-Chips über dem Fenster. Ein Klick lädt `/api/news/feed?news_category={cat}&page_size=7`;
  die Antwort wird über `feedItemToStory` in dieselbe `StoryData`-Form gebracht, die der Server
  schickt, der Lead ist die Story mit der höchsten Signifikanz und landet im Fenster. "all" stellt
  das Payload wieder her. Während des Ladens bleibt der alte Inhalt stehen, es gibt keinen
  Spinner-Sprung. Der Feed kennt `site_curated` nicht: nachgeladene Stories zeigen deshalb den
  neutralen Site-Chip statt eines Links auf eine Detailseite, die ein 404 sein könnte.
- "Load more" holt `/api/news/feed?page_size=6&page=N` (mit der aktiven Kategorie), lässt bereits
  gezeigte IDs aus und hängt den Rest an die Liste. Nach zwei Nachladungen wird der Button zum Link
  "all stories →" auf `/news.html`.
- Zeitangaben: der Server rendert das absolute Datum ("Sep 8"), der Client stellt nach der Hydration
  auf relative Zeit um ("2h ago" über `formatRelativeDate`). So gibt es keinen Hydration-Mismatch.
- Kein Auto-Rotieren, kein Ticker. Hover auf dem Screenshot zoomt leicht, unter
  `prefers-reduced-motion: reduce` nicht.
- Journals und Papers haben keine Client-Logik. Sie sind seit 2026-09-10 ebenfalls Fenster, aber
  ohne Tausch: Kopfleiste, Artikel, Liste — und jede Zeile darin ein normaler Link.

### 3.5 Gestaltung

**Eine Palette, die NERV-Palette** (Nutzer-Feedback 2026-09-10: "Warum benutzen wir keine
einheitlichen Farben?"). Referenz ist die Story-Seite: weiße Orbitron-Überschriften
(`--text-heading`), neutraler Fließtext (`--nerv-steel`), gedämpfte Meta-Zeilen
(`--nerv-steel-dim`), grün umrandete Tags, cyan Links (`--text-link`). Die vier privaten
Farbvariablen und die Kategorie-Farben sind gelöscht; einzige Ausnahme bleibt NERV-Orange
(`--nerv-o`) für die Theo-Zeile, weil das die Farbe eines laufenden Agenten ist. Monospace,
Sektionslabel im Muster `>_ [ fig. 1 — stories, live ]`, rechts daneben der Status. Bausteine,
umgesetzt in `src/styles/landing-live.css`:

- Fenster (alle drei): Panel-Look wie `.empire-borders-window` (`--surface-raised`, Blur,
  `--border-accent`, 4 px Radius, `--nerv-panel-shadow`), 36 px hohe Titelleiste in
  `rgba(0,15,20,.95)`, Körper als Raster 1.4fr / 1fr — Artikel mit eigenem Scrollbereich (72 vh,
  dünne grüne Scrollleiste), Liste rechts daneben. Der Rahmen ist EINE Komponente,
  `src/landing/LandingWindow.tsx`; die Sektionen liefern nur Titel, die beiden Kopfleisten-Links,
  den Artikel und die Liste. Im Artikel gelten die Klassen der jeweiligen Seite; überschrieben
  werden nur die Größen (`.story-title`/`.articles-reader-title`/`.theo-paper-title` 1.5em,
  Fließtext 14 px, `.theo-paper-page` ohne eigenes Padding). Die aktive Zeile trägt `--nerv-gl` und
  einen 2 px grünen Balken links.
- Journal-Fenster (seit 2026-09-10): `>_ journal.log — {Titel}`, links `<JournalArticle
  headingLevel="h3">` — die Ausgabe genau so, wie `/articles/{slug}` sie rendert, bis zum Auszug
  —, darunter der `.ll-continue`-Link auf die Ausgabe, wenn `excerpted` gesetzt ist. Rechts oben
  die Abschnitts-Chips der Ausgabe (jetzt Links auf sie), darunter die älteren Ausgaben als
  `.ll-row`. Kein Tausch im Fenster: eine Ausgabe ist eine lange Lektüre, keine Karte, jede Zeile
  ist ein normaler Link.
- Papers-Fenster (seit 2026-09-10): `>_ research.log — {Titel}`, links `<PaperArticle
  headingLevel="h3">` mit Hero, Byline, Lesezeit und Lizenz wie auf `/research/{slug}`, darunter
  der `.ll-continue`-Link und der Evidenz-Streifen (sources analyzed, quality, length, license).
  Die Theo-Zeile bleibt außerhalb des Fensters — sie beschreibt den Agenten, nicht das Paper.
- Liste: eine Zeile je weiterer Ausgabe bzw. weiterem Paper (nur Text), beim Stories-Fenster mit
  96-px-Thumbnail. Zeilen sind komplett klickbar.
- Screenshots als Textur: `saturate(.75)` und ein Verlauf nach unten, kein Text im Bild.
- Theo-Zeile unter den Papers: gestrichelter oranger Rahmen, pulsierender Punkt, "Theo is
  researching: {Frage} · started {Zeit} · {n} sites found", Link auf `/theo.html`. Die Zeit folgt
  derselben Regel wie alle Zeitangaben der Seite: absolut im Server-HTML, relativ ("6h ago") nach
  der Hydration.
- Mobile unter 900 px (der Breakpoint der übrigen Landing-Sektionen): eine Spalte, Artikel bzw. Lead oben, Liste darunter (Trennlinie oben statt links, Artikel ohne eigenen Scrollbereich); Chips scrollen horizontal.

Die Mockups aus dem Brainstorming liegen unter `.superpowers/brainstorm/239-1788951798/content/`
(`stories-cards.html` Variante B, `longreads.html` Variante A).

### 3.6 Hero: H1, Zahlen und Intro-Absatz

**H1 mit Suchbegriff.** Heute ist die H1 der Schriftzug "ANCIENT NERDS", ohne ein einziges Suchwort.
Der Schriftzug bleibt optisch identisch, wird aber ein `<p class="hero-title">`. Die H1 wird die
Slogan-Zeile darunter mit dem Text "The interactive map of <span data-stat="sites-long">1.7 million</span>
archaeological sites, explored through data, maps and AI". Sie behält die Klasse und Optik der
heutigen Slogan-Zeile (`hero-tagline`), es gibt genau eine H1 auf der Seite. "RESEARCH PLATFORM" bleibt.

**Zahlen überall.** Die Datenbank hat 1.759.673 Sites, die Seite behauptet "750K+" an sieben Stellen:
Hero-Statistik, `<title>`, Description, OG- und Twitter-Description, JSON-LD (WebApplication) und
PWA-Manifest in `vite.config.ts`. Die Hero-Werte für Sites und Länder bekommen `data-stat="sites"`
und `data-stat="countries"`; die Landing-Route ersetzt sie und `sites-long` im Shell-HTML durch
formatierte Live-Werte ("1.76M", "98" Länder mit kuratierten Sites, "1.7 million"). Empires und Sources
bleiben statisch "30+" und "20+". `landingMeta` formatiert Titel und Description aus `stats.sites`
("1.7M+"). Die statischen Stellen (JSON-LD, Manifest, Rückfall-Texte in `index.html`) werden einmalig
auf "1.7 million+" beziehungsweise "1.7M+" gesetzt.

**Intro-Absatz.** Direkt unter dem Hero, vor `#root`, statisch in `index.html`, damit er auch im
Rückfall steht. Drei bis vier Sätze, monospace, Lesebreite 70 Zeichen, mit Links auf Globus, Stories,
Journals, Papers und Lyra. Vorschlag (englisch, der User gibt den endgültigen Text frei):

> Ancient Nerds is a free research platform for archaeology and ancient history. A 3D globe maps
> 1.7 million sites from more than 20 open databases, 5,000 of them curated in depth. Lyra reads the
> latest archaeology videos and turns them into sourced stories, which become a journal every week.
> Theo, our research agent, writes long-form papers with thousands of citations, published under CC BY 4.0.

Alle Zahlen darin sind heute korrekt (1.759.673 Sites, 5.004 kuratiert, 20+ Quellen, 2.700 bis 3.200
analysierte Quellen je Paper). Im statischen Rückfall bleiben Absatz und H1 mit den festen Zahlen stehen.

## 4. Fehlerfälle

- Sidecar oder API antworten nicht: nginx liefert das statische `index.html`, die Live-Sektionen
  fehlen, alles andere funktioniert. Kein zweiter Renderer, wie bei den anderen SSR-Seiten.
- Payload leer oder unbekannter Typ im Client: `landingMain.tsx` rendert nichts und meldet nichts.
- `/api/news/feed` schlägt beim Chip-Klick fehl: der bisherige Inhalt bleibt, der Chip springt
  zurück, ein kurzer Hinweis "feed unavailable" erscheint in der Statuszeile.
- Screenshot fehlt (404): `LazyImage`-Fallback wie in den Story-Seiten.

## 5. Tests

- **vitest:** `landingMeta` liefert Titel und Description mit der formatierten Site-Zahl; `renderToString(<LandingLive/>)` mit einem
  Fixture-Payload enthält alle Story-, Journal- und Paper-Links, keine "undefined"-Strings, und rendert
  ohne Theo-Zeile, wenn `theo` null ist. Bestehender Route-Guard-Test um `landing` erweitern.
- **pytest (DB-los):** der Payload-Builder bekommt Fake-Rows und liefert die Lead-Regel korrekt
  (48-Stunden-Fenster, kein Duplikat, Fallback auf die 7 neuesten), Wortzahl und Lesezeit, Sektionen
  ohne "Sources"/"Videos".
- **Build-Gate:** `size-limit` auf `dist/assets/landing-*.js` und `LandingLive-*.js` mit 40 kB
  Brotli im `lint-frontend`-Job, gleich nach `npm run build`.
- **Nach dem Deploy (Playwright):** `/` liefert SSR-HTML mit sieben Story-Links (Lead plus sechs), null
  Hydration-Fehler in der Konsole, LCP-Element ist das Hero-Bild, genau eine H1 mit dem Suchbegriff,
  kein "750K" mehr im Dokument, und ein Chip-Klick tauscht den Inhalt.
  Crawler-Sicht mit JS-Blockade prüfen (Lehre aus den 2.100 Soft-404-Seiten).

## 6. Änderungen außerhalb des Codes

- `ancientnerds-nginx-config`: `location = /` und der neue `@home_static`-Block. Der Deploy wendet
  die Datei automatisch an (`nginx -t` und reload), aber Konfigurationsänderungen brauchen deine
  Freigabe vor dem Push.
- Kein Migrations-, Compose- oder Secrets-Bedarf.

## 7. Umsetzungsreihenfolge

1. Typen, Registry, `landingMeta`, `LandingLive` mit Fixture, vitest.
2. `landing_html.py` mit Payload-Builder und pytest, Route `/home` in `main.py`.
3. `index.html`: `#root`, H1-Tausch, Intro-Absatz, `data-stat`-Spans, Zahlen in Head, JSON-LD und
   Manifest, Sektionen entfernen, `landingMain.tsx` einbinden; Service-Worker-Denylist; CSS.
4. Stories-Interaktion (Chips, Load more, relative Zeit).
5. nginx-Block, size-limit, Deploy, Playwright-Prüfung, GSC-Beobachtung der Startseite.
