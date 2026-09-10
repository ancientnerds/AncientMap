# Landingpage: Live-Sektionen für Stories, Journals, Research Papers und Site Search

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
3. Vier Portal-Sektionen, ab 901 px als 2×2-Raster (Betreiber, 2026-09-11: „Stories und Journal auf
   einer Zeile, Research und Sites auf der zweiten"), darunter eine Spalte in derselben Reihenfolge:
   - `>_ [ fig. 1 — stories, live ]` auf `/news.html`
   - `>_ [ fig. 2 — weekly journal ]` auf `/articles.html`
   - `>_ [ fig. 3 — research papers ]` auf `/research/`
   - `>_ [ fig. 4 — site search ]` auf `/search.html` (der Rahmen zeigt `/search.html?random`)
4. Bestehende Sektionen in heutiger Reihenfolge: Globe, Filter, Empires (cinematic), Site data, Lyra,
   Radar, Tools, Sources, API, Founders, Discord, Giants, Browse (Länder-Hubs und Paper-Liste), Final CTA, Footer.

Entfernt werden die Screenshot-Karte "Archaeology Stories" (Split-Row mit Radar) und die Sektion
"Weekly Journals". Die Radar-Karte wird zur normalen Feature-Row in der Breite der anderen Sektionen.
Die Browse-Listen (Länder-Hubs und Paper-Liste) bleiben: sie verlinken für Suchmaschinen jede
Länder-Hub und jedes Paper, die Portale verlinken nur ihre Seite. Mit dem Site-Search-Portal
(2026-09-11) fielen die Tool-Karte „Search" (dieselbe Funktion zweimal auf einer Seite; die fünf
übrigen Karten stehen zentriert, `.tools-grid` ist Flex) und das im Filter-Streifen doppelt
eingebundene `filter-source.webp`; die Globe-Sektion trägt ihre Zahl jetzt als `data-stat`-Span
statt „Hundreds of thousands".

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
  per `size-limit`; react-dom ist ein geteilter Chunk und zählt nicht mit (Stand 11.09.: 2,13 kB,
  nachdem die Listen, ihr Feed-Client und die Paper-Galerie weg sind). Nichts aus `three`, nichts
  aus `SitePopup`, kein `NewsCard` (447 Zeilen, Inline-Video, Share-Logik: zu schwer für eine
  Vorschau), und seit dem Wegfall der Galerie auch kein `PaperCard` — den Chunk lädt jetzt
  `/research/`, also zählt ihn das Startseiten-Budget nicht mehr mit.
- LCP bleibt Logo und Hero-Poster. `#root` reserviert seine Höhe nicht, weil der Inhalt serverseitig
  vollständig ankommt; Bilder tragen `width`/`height` und `aspect-ratio`, damit nichts springt.

### 3.3 Daten: das Route-Payload

Alles wird serverseitig in `landing_html.py` gesammelt und im Payload mitgegeben. Der Client braucht
für den ersten Paint keinen einzigen API-Aufruf.

```
LandingRoute {
  type: 'landing'
  stats:    { sites: number, sources: number, stories: number, journals: number, papers: number }
  journals: { total: number } | null
  papers:   { total: number, theo: TheoStatus | null } | null
}
TheoStatus    { question, started_at, sites_found }
```

Seit 2026-09-10 trägt das Payload **keine Zeilen** mehr, weil es keine Listen mehr gibt (3.4): jede
Sektion ist ein Portal auf die echte Seite, und die Seite darin IST ihre Liste. Seit 2026-09-11 gilt
das auch für die Paper-Karten (Betreiber: "The research paper examples should be inside the portal,
not below it") — sie stehen auf `/research/`, und das dritte Portal zeigt genau diese Seite. Übrig
bleiben die Zähler und die Theo-Zeile. Ein Feld, das keine Komponente liest, gehört nicht ins
Payload; die Schlüssel sind auf beiden Seiten festgenagelt (`tests/api/test_landing_html.py`,
`landingLive.test.tsx`).

Regeln:

- **Stories.** Nur der Zähler `stats.stories` aus `get_news_stats`. Die Statuszeile schreibt
  "{n} stories · newest first", das Portal auf `/news.html` zeigt den Rest. Die Lead-Regel, die
  Kategorie-Chips und `story_teaser()` sind mit der Liste verschwunden, ebenso die beiden Abfragen,
  die sie fütterten.
- **Journals.** Nur `journals.total` (`get_news_stats().total_articles`). `null`, wenn es keine
  einzige Ausgabe gibt — dann fehlt die Sektion. Statuszeile: "{n} issues · every Sunday".
- **Papers.** Nur `papers.total`, ein `COUNT(*)` unter `PUBLIC_PAPER_WHERE`. `null`, wenn kein
  einziges Paper öffentlich ist — dann fehlt die Sektion. Statuszeile: "{n} public · CC BY 4.0 · by
  Theo". Die Karten liegen auf `/research/` (`api/routes/research_html.py::research_listing`), das
  Portal zeigt sie; die Sechs-Zeilen-Abfrage und `paper_teaser()` sind mit der Galerie verschwunden.
  `theo` kommt aus derselben Abfrage, die `/api/theo/research/current` benutzt (laufender
  Batch-Request: Frage, Startzeit, gefundene Sites); die Funktion wird importiert, nicht kopiert.
- **Sites.** Nur `stats.sites` und `stats.sources` (`len(by_source)` aus derselben gecachten
  `get_site_stats()`); Statuszeile "{n} sites · {m} sources". Immer da, wie Stories.
- **Stats.** `sites` aus der gecachten `/api/stats`-Logik, `stories` und `journals` aus
  `get_news_stats`, `papers` per Count unter `PUBLIC_PAPER_WHERE`.

Fehlt eine Datenquelle (kein Journal, kein Paper, kein laufender Theo), fehlt die Sektion oder die
Zeile im Payload und wird nicht gerendert. Es gibt keine Platzhalter-Inhalte.

### 3.4 Interaktion: das Portal

Wunsch des Betreibers am 2026-09-10: "Ich will eine Art Portal zu den Seiten — wie ein Screenshot,
der den aktuellen Stand zeigt." Beides: ein echter Screenshot als Grundschicht, die Seite selbst
darauf — aber nur dort, wo sie sich lohnt.

- Jede Sektion ist ein **NERV-Fenster mit einem Portal darin** (`src/landing/PagePortal.tsx`): das
  Poster der echten Seite — `/news.html`, `/articles.html`, `/research/`, `/search.html` — über die volle Breite
  des Fensterkörpers, auf dem Desktop ein `<iframe>` derselben Seite darüber. Titelleiste `>_ portal — {Pfad}`, rechts die Fensterknöpfe aus
  `nerv-ui/window.css`: ↗ öffnet die Seite, ≡ das Archiv — und ≡ gibt es nur, wo das Archiv eine
  andere Seite ist (Stories: `/news.html` vs. `/news-archive/`, Sites: `/search.html` vs.
  `/sites/`). Der Journal-Hub und die
  Forschungsbibliothek SIND ihr Archiv, dort steht nur ↗.
- **Die Liste daneben ist weg** (Betreiber, 2026-09-10: "Warum haben wir rechts immer noch die Liste
  der Stories, Journals und Research Papers?"). Sie sagte dasselbe wie die Seite im Rahmen. Mit ihr
  gingen `.ll-window-list`, `.ll-row*`, `.ll-img*`, die Chips, "load more", `feedClient.ts` und
  `dates.ts`; der Fensterkörper ist eine Spalte.
- **Der Rahmen ist Dekoration, kein zweiter Browser**: `pointer-events: none`, `tabIndex={-1}`,
  `aria-hidden="true"` (Betreiber: "das Scrollen im Portal wird verhindert, damit ich normal
  weiterscrollen kann"). Ein Wheel-Event oder eine Wischgeste über dem Portal scrollt die
  Startseite, im Rahmen lässt sich nichts anklicken und nichts antabben.
- **Ein Overlay-Link deckt das ganze Portal** (`.ll-portal-link`, `position: absolute; inset: 0`) und
  trägt mittig einen `.cta-primary` — dieselbe rote Schaltfläche wie im Hero. Wo es einen Zeiger gibt
  (`@media (hover: hover)`), wartet der CTA auf ihn: unsichtbar, bis das Portal überfahren oder der
  Link per Tastatur fokussiert wird (kurze Opacity-Blende, nur unter
  `prefers-reduced-motion: no-preference`), und was darunter liegt — der Rahmen, oder vor seinem
  Mount das Poster — dunkelt dabei auf `brightness(.6)` ab. Auf
  Touch-Geräten (`@media (hover: none)`) steht er immer da. `aria-label` trägt die Wörter ohne den
  ↗-Glyphen, den ein Screenreader sonst als "north east arrow" vorliest.
- **Jedes Portal trägt ein Poster** (`<img class="ll-portal-poster">`, seit 2026-09-10): einen echten
  Screenshot genau der Seite, auf die es zeigt, aus `/data/previews/{news,articles,research}.jpg`.
  Betreiber vom Telefon: "Auf dem Handy flackert alles ganz schön — sind Screenshots vielleicht doch
  besser?" Antwort: hybrid. Das Poster ist die Grundschicht und steht schon im SSR-Baum, aufgenommen
  bei 1280×800, gelegt mit `object-fit: cover` und `object-position: top` — im 16/10-Desktopkasten
  ist das der obere Ausschnitt, in der 4/3-Box des Telefons derselbe Ausschnitt, den auch der Rahmen
  zeigt. Aufgenommen wird es außerhalb des Repos, siehe 6.
- **Den Rahmen bekommt nur der Desktop.** `window.matchMedia('(hover: hover) and (min-width: 900px)')`
  entscheidet einmal beim Mount — das ist eine Geräteklasse, keine Fensterbreite, der man hinterher
  läuft. Telefone und Tablets sehen nur das Poster: kein zweiter Seitenaufruf, kein Nachladen, nichts
  das flackern kann. Wo der Rahmen kommt, liegt er über dem Poster (`z-index: 1`, der Overlay-Link
  rückt auf `2`) und ersetzt es optisch.
- **Eine Sektion, eine Komponente.** `src/landing/PortalSection.tsx` ist die Form aller vier
  Sektionen (Label, Fenster, Portal, Fußzeile); `LandingLive.tsx` listet die vier als Daten, die
  Theo-Zeile (`TheoLine.tsx`) kommt als Kind unter das Papers-Fenster. Eine Sektion zeigt auf EINE
  Seite (`page`): Fenstertitel, ↗, Rahmenquelle, CTA und Fußzeilen-Link kommen aus demselben Prop.
  Nur die Suche hat eine eigene Ansicht (`view`): Rahmen und Poster zeigen `/search.html?random`,
  weil eine leere Suchleiste nichts zeigt — `SearchPage.tsx` würfelt mit `?random` einmal beim
  Laden dieselbe Zufallsauswahl wie der Random-Knopf; jeder Link führt auf `/search.html` ohne
  Parameter.
- **Der Server rendert nie ein iframe.** SSR und der erste Client-Render liefern denselben Baum:
  den Container `.ll-portal[data-src]`, das Poster und den Overlay-Link mit seinem CTA. Damit stimmen
  Server- und Client-Baum überein, und ein Crawler bekommt ein Bild und einen Link statt eines
  Rahmens, dem er nicht folgt.
- Der Rahmen erscheint erst **nach dem Mount**. Ausgenommen bleibt neben der Medienabfrage
  `navigator.connection.saveData`: eine ganze zweite Seite ist genau das, worum dieser Header bittet,
  sie nicht zu laden. Geladen wird erst, wenn das Fenster in Sichtweite scrollt
  (`IntersectionObserver`, `rootMargin: 200px`), damit vier Portale nicht vier Seitenaufrufe auf
  einer Startseite kosten, die niemand gescrollt hat. Bis dahin ist die Box das Poster mit dem CTA.
- **Maßstab:** das iframe liegt 1280 CSS-Pixel breit und wird per `transform: scale()` auf die
  Fensterbreite gebracht; ein `ResizeObserver` auf dem Container schreibt `width / 1280` in
  `--ll-portal-scale`. Nicht verkleinert, sondern skaliert — die Seite darin sieht einen
  Desktop-Viewport und ordnet sich so an, wie ein Besucher sie sähe. Die Höhe ist abgeleitet statt
  fest: `calc(100% / var(--ll-portal-scale))` ist skaliert exakt die Höhe der Box, im 16/10-Desktop
  dieselben 800 px wie vorher, in der 4/3-Box des Telefons der höhere Ausschnitt, der sie füllt.
- **Keine Galerie.** Unter dem Papers-Fenster stand bis 2026-09-11 eine Galerie derselben Papers,
  die im Rahmen schon zu sehen waren. Sie ist weg; die Karten sind jetzt die Bibliothek selbst
  (3.5), und crawlbar bleibt die Sektion über ihre drei Links auf `/research/`.
- **SEO:** in `#root` steht kein `h1`; die Sektionsüberschrift bleibt das einzige `h2` der Sektion.
  Jede Sektion verlinkt ihre Seite dreifach (Fensterknopf, Overlay-Link, Fußzeile); die einzelnen
  Papers verlinkt `/research/` selbst und, für Suchmaschinen, die Paper-Liste der Browse-Sektion.
- Zeitangaben: der Server rendert das absolute Datum ("Sep 9"), der Client stellt nach der Hydration
  auf relative Zeit um ("2h ago" über `formatRelativeDate`). So gibt es keinen Hydration-Mismatch.
  Übrig ist davon genau eine Stelle, die Startzeit in der Theo-Zeile.
- Client-Logik gibt es in keiner der drei Sektionen mehr außer dem Portal selbst: Kopfleiste,
  Portal, Fußzeile — und bei den Papers die Theo-Zeile.
- **X-Frame-Options.** `/research/` kommt aus der API, und die setzte auf jeder Antwort `DENY` —
  das eigene Portal wäre leer geblieben. Der Header steht seit 2026-09-10 auf `SAMEORIGIN`
  (`api/main.py`); fremdes Framing bleibt blockiert, ein `frame-ancestors`-CSP existiert nirgends.

### 3.5 Gestaltung

**Grün und rot, sonst nichts** (Betreiber, 2026-09-10: "Seit wann benutzen wir diese blaue Schrift?
Wir haben in NERV nur grün und rot!"). Referenz ist die Story-Seite: weiße Orbitron-Überschriften
(`--text-heading`), neutraler Fließtext (`--nerv-steel`), gedämpfte Meta-Zeilen
(`--nerv-steel-dim`). Jeder Link ist `--accent-primary`, jede Handlungsaufforderung trägt
`.cta-primary` aus `landing.css` und ist damit rot; `--text-link`, `--accent-secondary` und `--nerv-c`
kommen in den Live-Sektionen und im Intro-Absatz nicht mehr vor. Einzige Ausnahme bleibt NERV-Orange
(`--nerv-o`) für die Theo-Zeile, weil das die Farbe eines laufenden Agenten ist. Monospace,
Sektionslabel im Muster `>_ [ fig. 1 — stories, live ]`, rechts daneben der Status. Bausteine,
umgesetzt in `src/styles/landing-live.css`:

- Raster: `.landing-live` ist ein Grid, eine Spalte, ab 901 px zwei (`gap: 48px 24px`); die
  Sektionen haben keine Trennlinien mehr und `min-width: 0`, damit der Fenstertitel seine Ellipse
  behält. 900 px ist der Bruchpunkt der Seite (`.feature-row`) und des Rahmens (`PagePortal`), die
  Zellen halbieren sich also genau dort, wo der Live-Rahmen dazukommt. Fußzeile und Theo-Zeile
  brechen um (`flex-wrap`), weil eine halbe Spalte für eine Reihe zu schmal ist.
- Fenster (alle vier): Panel-Look wie `.empire-borders-window` (`--surface-raised`, Blur,
  `--border-accent`, 4 px Radius, `--nerv-panel-shadow`), 36 px hohe Titelleiste in
  `rgba(0,15,20,.95)`, Titel mit Ellipse, Körper eine Spalte mit 12 px Polster. Der Rahmen ist EINE
  Komponente, `src/landing/LandingWindow.tsx`; die Sektionen liefern nur Titel, die
  Kopfleisten-Links (`archive` ist optional) und den Inhalt.
- Portal: `.ll-portal` ist relativ positioniert, 16 / 10, `overflow: hidden`, Hintergrund
  `--surface-deep`. `.ll-portal-frame` liegt absolut bei 1280 px Breite ohne Rahmen, ohne
  Pointer-Events, und wird über `transform-origin: 0 0` und `scale(var(--ll-portal-scale, .5))` auf
  die Spalte gebracht. Darüber `.ll-portal-link` über die volle Fläche mit dem `.ll-portal-cta` in
  der Mitte — der übernimmt Rahmen und Rot von `.cta-primary` und ändert Größe und Ruhezustand
  (schwarz statt transparent), damit die längste Beschriftung ("Open research library ↗") in eine
  318-px-Box auf einem 390-px-Telefon passt und der Knopf vor der Seite dahinter lesbar bleibt. Die
  beiden Farbregeln stehen als `.ll-portal .ll-portal-cta`: die Shell lädt `landing.css` NACH
  `landing-live.css`, bei gleicher Spezifität hätte also `.cta-primary` gewonnen.
- Fenstertitel: `>_ portal — /news.html`, `>_ portal — /articles.html`, `>_ portal — /research/`,
  `>_ portal — /search.html`.
- Paper-Karten: `.theo-public-grid` mit `src/components/theo/PaperCard.tsx` und den Regeln aus
  `src/styles/paper-card.css` — aber auf `/research/` (`ResearchIndexPage`), nicht auf der
  Startseite. Betreiber, 2026-09-11: "The research paper examples should be inside the portal, not
  below it. And the research library should have the cards, not plain headings." Damit rendert die
  Bibliothek dieselbe Karte wie `/theo.html`, und das Portal zeigt sie mit. Der Auto-Fill der
  Bibliothek bleibt, weil dort alle Papers stehen und nicht sechs. Hero-Bild aus `hero_image_url`;
  fehlt es, zeigt der Hero-Kasten nur die Vignette mit dem Titel — nie ein `<img src="">`. Fußzeile
  der Karte: "by {Autor} · {Datum} · {n} sources · {n} words", zusammengesetzt aus den vorhandenen
  Teilen von `paperCardFooter()` in `src/seo/display.ts` — der Text ist Darstellung, nicht Payload.
- Theo-Zeile unter dem Fenster: gestrichelter oranger Rahmen, pulsierender Punkt, "Theo is
  researching: {Frage} · started {Zeit} · {n} sites found", Link auf `/theo.html`.
- Mobile unter 700 px: Portal 4 / 3 mit sichtbarem CTA, Fußzeile und
  Theo-Zeile zweizeilig statt in einer gequetschten Reihe. Das seitliche Polster bleibt bei
  24 px, damit die Live-Sektionen mit den statischen `.landing-section` bündig stehen; bei
  390 px Viewport läuft trotzdem nichts über: 390 − 2 × 24 − 2 × 12 Fensterpolster = 318 px für
  das Portal, und der längste CTA braucht davon rund 250 px.

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
- Der Rahmen kommt nicht (Telefon, Save-Data, Seite im Rahmen langsam oder tot): die Box bleibt das
  Poster mit dem CTA — genau das, was Server und erster Client-Render ohnehin liefern. Es gibt
  keinen Ladezustand und keinen Platzhalterinhalt.
- Das Poster fehlt (erster Deploy vor dem ersten Lauf von `previews.yml`, Upload gescheitert): der
  `<img>` bleibt leer über dem dunklen `--surface-deep` des Portalkastens, der CTA steht davor. Kein
  Rendercode fängt das ab; sichtbar wird es am nächsten Workflow-Lauf von selbst wieder heil.

## 5. Tests

- **vitest:** `landingMeta` liefert Titel und Description mit der formatierten Site-Zahl;
  `renderToString(<LandingLive/>)` mit dem Fixture-Payload liefert vier Fenster mit je einem
  `.ll-portal[data-src]`, genau einem `img.ll-portal-poster` auf dem Poster der eigenen Seite und
  genau einem `.ll-portal-link` mit `.cta-primary`, kein `<iframe`, keine Listen- und keine
  Kartenklasse mehr, kein `h1`, kein "undefined"/"null", und keine
  Theo-Zeile, wenn `theo` null ist. Die Karten prüft `render.test.tsx` am researchIndex-Fixture:
  ein `a.theo-public-card` je Paper mit `href="/research/{slug}"`, `img.theo-public-card-img` nur
  dort, wo es ein Hero gibt, und die Fußzeile aus den vorhandenen Teilen.
- **pytest (DB-los):** `research_listing()` übergibt genau die acht Kartenfelder je Paper; die
  Landing-Route liefert `{type, stats, journals, papers}` und nichts sonst, lässt Sektionen ohne
  Inhalt weg, antwortet aus dem Cache und bleibt unter gzip dekodierbar.
- **Build-Gate:** `size-limit` auf `dist/assets/landing-*.js` und `LandingLive-*.js` mit 40 kB
  Brotli im `lint-frontend`-Job, gleich nach `npm run build`.
- **Nach dem Deploy (Playwright):** `/` liefert SSR-HTML mit vier Portalen und ohne eine einzige
  Paper-Karte darunter, `/research/` mit einer Karte je Paper, null Hydration-Fehler in der Konsole, LCP-Element ist das Hero-Bild, genau eine H1 mit dem
  Suchbegriff, kein "750K" mehr im Dokument; vier Poster aus `/data/previews/` laden mit 200, nach
  dem Scrollen stehen auf dem Desktop vier iframes im DOM und auf 390 px Breite keins, ein
  Wheel-Event über einem Portal scrollt die Seite und nicht den Rahmen, und auf 390 px Breite gibt
  es keinen horizontalen Überlauf. Crawler-Sicht mit JS-Blockade prüfen (Lehre aus den 2.100
  Soft-404-Seiten).

## 6. Änderungen außerhalb des Codes

- `ancientnerds-nginx-config`: `location = /` und der neue `@home_static`-Block. Der Deploy wendet
  die Datei automatisch an (`nginx -t` und reload), aber Konfigurationsänderungen brauchen deine
  Freigabe vor dem Push.
- **Die Portal-Poster** (`/data/previews/{news,articles,research,search}.jpg`) liegen nicht im Repo. Sie
  entstehen im Workflow `.github/workflows/previews.yml`:
  - `ancient-nerds-map/scripts/capture-previews.mjs` öffnet mit Puppeteer `/news.html`,
    `/articles.html`, `/research/` und `/search.html?random` (wartet auf die erste `.site-card`) auf
    `PREVIEW_BASE_URL` (Vorgabe `https://ancientnerds.com`)
    bei 1280×800, wartet auf `networkidle2` plus 1500 ms, entfernt `#cookie-notice` und schreibt je
    ein JPEG (Qualität 82) nach `PREVIEW_OUT_DIR` (Vorgabe `previews-out`). Lokal: `npm run previews`.
  - Takt: nach **jedem grünen CI-Lauf auf `main`** (`workflow_run`, also nach jedem Deploy; das Verzeichnis ist gitignored und überlebt dessen
    `git clean -fd`, die Poster fehlen also nur bis zum allerersten Lauf) und **alle sechs
    Stunden** (`cron: '23 */6 * * *'`), dazu `workflow_dispatch`. `concurrency: page-previews` ohne
    `cancel-in-progress`, damit sich Deploy-Lauf und Zeitplan nicht ins Gehege kommen.
  - Ziel: `scp` nach `/var/www/ancientnerds/public/data/previews/`. nginx liefert das über den
    bestehenden `location /data/`-Block mit `Cache-Control: public, max-age=3600`; ein Poster ist
    also höchstens sechs Stunden plus eine Cache-Stunde alt.
  - Zugang: dieselben Secrets wie der Deploy-Job (`VPS_SSH_KEY` über `webfactory/ssh-agent@v0.9.0`,
    `VPS_HOST`, `VPS_PORT`, `VPS_USER`). Keine neuen Secrets, kein neuer Schlüssel.
  - `.gitignore`: `public/data/previews/` und `ancient-nerds-map/previews-out/`.
- Kein Migrations-, Compose- oder Secrets-Bedarf.

## 7. Umsetzungsreihenfolge

1. Typen, Registry, `landingMeta`, `LandingLive` mit Fixture, vitest.
2. `landing_html.py` mit Payload-Builder und pytest, Route `/home` in `main.py`.
3. `index.html`: `#root`, H1-Tausch, Intro-Absatz, `data-stat`-Spans, Zahlen in Head, JSON-LD und
   Manifest, Sektionen entfernen, `landingMain.tsx` einbinden; Service-Worker-Denylist; CSS.
4. Portal-Verhalten (Overlay-CTA, Lazy-Mount, Maßstab) und die Papers-Galerie.
5. nginx-Block, size-limit, Deploy, Playwright-Prüfung, GSC-Beobachtung der Startseite.
