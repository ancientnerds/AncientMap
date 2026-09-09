# Landingpage: Live-Sektionen für Stories, Journals und Research Papers

Datum: 2026-09-09 · Status: Entwurf zur Freigabe · Recherche: `docs/superpowers/research/2026-09-09-landing-page-research.md`

## 1. Ziel

Die Startseite zeigt heute 36 Screenshots und kein einziges interaktives Element. Sie bekommt drei
Sektionen mit echten, aktuellen Inhalten direkt unter dem Hero, in der Reihenfolge Stories, Journals,
Research Papers. Der Hero mit dem Globus-Video bleibt unverändert. Die bestehenden Screenshot-Abschnitte
bleiben darunter erhalten, abzüglich der beiden, die durch Live-Sektionen ersetzt werden.

Entscheidungen aus dem Brainstorming (09.09.2026):

- Hero: Globus-Video oben, wie heute. Kein Mini-Globus, keine Suchbox, keine Umgestaltung.
- Stories: Variante "Lead-Karte plus Liste". Eine große Story, daneben sechs kompakte Zeilen.
- Journals und Papers: zwei eigene Sektionen, jeweils Lead plus Liste.
- Kein eigener Abschnitt für Globus-Fähigkeiten. Die vorhandenen Screenshot-Sektionen decken das ab.
- Lyra-Live-Demo, Bento-Umbau, Performance-Gates per Lighthouse: nicht in diesem Vorhaben.

## 2. Seitenaufbau

1. Hero (unverändert, siehe 3.6 für die Zahlen)
2. `>_ [ fig. 1 — stories, live ]`
3. `>_ [ fig. 2 — weekly journal ]`
4. `>_ [ fig. 3 — research papers ]`
5. Bestehende Sektionen in heutiger Reihenfolge: Globe, Filter, Empires (cinematic), Site data, Lyra,
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
- Die Route hält das fertige HTML 300 Sekunden im Prozess-Cache und sendet
  `Cache-Control: public, max-age=300`. Bei rund 200 Aufrufen am Tag reicht das; kein nginx-Cache nötig.
- nginx: `location = /` proxied auf `http://an_api/home` statt `try_files /index.html`. Die bestehende
  `$arg_site`-Weiterleitung bleibt davor. Für diesen Block gilt `error_page 502 504 = @home_static`, und
  `@home_static` liefert `/index.html` aus `dist/`. Während der Deploy-Fenster (gemessen 87 bis 110 s)
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
- Budget für den Entry `landing-*.js`: 80 kB Brotli. Enthalten sind react-dom, die drei Sektionen und
  die Feed-Logik. Nichts aus `three`, nichts aus `SitePopup`, kein `NewsCard` (447 Zeilen, Inline-Video,
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
  stories:  { lead: StoryTeaser, rail: StoryTeaser[], categories: string[] }
  journals: { lead: JournalTeaser, rail: JournalTeaser[], total: number }
  papers:   { lead: PaperTeaser, rail: PaperTeaser[], total: number, theo: TheoStatus | null }
}
StoryTeaser   { id, headline, summary, screenshot_url, category, significance, created_at,
                channel, sources, path, site: { name, country, path } | null }
JournalTeaser { id, title, summary, week_start, week_end, published_at, words, minutes,
                sections: string[], sources, image_url | null, path }
PaperTeaser   { slug, title, summary, published_at, words, minutes, sources_analyzed,
                quality_score, hero_image_url | null, path }
TheoStatus    { question, started_at, sites_found }
```

Regeln:

- **Stories.** Dieselbe Grundfilterung wie `/api/news/feed` (post_text vorhanden, Signifikanz ≥ 2
  oder null, neueste zuerst). Der Lead ist die Story mit der höchsten Signifikanz der letzten 48
  Stunden, bei Gleichstand die neuere. Gibt es in 48 Stunden keine, ist der Lead die höchste
  Signifikanz unter den 7 neuesten. Die Liste sind die 7 neuesten ohne den Lead, gekürzt auf 6
  Zeilen. Sichtbar sind also immer 7 Stories: Lead plus sechs. `summary` ist der erste Satz aus `post_text` über `splitPostText`, `sources` ist die
  Länge von `web_sources`, `path` kommt aus `story_slug`, `categories` sind die Kategorien mit
  mindestens einer Story in den letzten 30 Tagen.
- **Journals.** Die 4 neuesten aktiven Artikel nach `week_start`. `words` zählt den Inhalt,
  `minutes` ist `words / 238` aufgerundet, `sections` sind die `##`-Überschriften ohne "Sources" und
  "Videos", `sources` zählt die Links, `image_url` ist der erste Screenshot im Inhalt.
  `path` ist `/articles/{slugify(title)}`, wie in `articles_html.py`.
- **Papers.** Die 6 neuesten nach `published_at` unter `PUBLIC_PAPER_WHERE` mit den
  `PAPER_SUMMARY_COLUMNS`. Der Lead ist das neueste. `theo` kommt aus derselben Abfrage, die
  `/api/theo/research/current` benutzt (laufender Batch-Request: Frage, Startzeit, gefundene Sites);
  die Funktion wird importiert, nicht kopiert.
- **Stats.** `sites` aus der gecachten `/api/stats`-Logik, `stories` und `journals` aus
  `get_news_stats`, `papers` per Count unter `PUBLIC_PAPER_WHERE`.

Fehlt eine Datenquelle (kein Journal, kein Paper, kein laufender Theo), fehlt die Sektion oder die
Zeile im Payload und wird nicht gerendert. Es gibt keine Platzhalter-Inhalte.

### 3.4 Interaktion in der Stories-Sektion

- Kategorie-Chips über der Sektion. Ein Klick lädt `/api/news/feed?news_category={cat}&page_size=7`;
  der Lead wird die Story mit der höchsten Signifikanz der Antwort, die übrigen sechs die Liste.
  "all" stellt das Payload wieder her. Während des Ladens bleibt der alte Inhalt stehen, es gibt
  keinen Spinner-Sprung.
- "Load more" holt `/api/news/feed?page_size=6&page=N` (mit der aktiven Kategorie), lässt bereits
  gezeigte IDs aus und hängt den Rest an die Liste. Nach zwei Nachladungen wird der Button zum Link
  "all stories →" auf `/news.html`.
- Zeitangaben: der Server rendert das absolute Datum ("Sep 8"), der Client stellt nach der Hydration
  auf relative Zeit um ("2h ago" über `formatRelativeDate`). So gibt es keinen Hydration-Mismatch.
- Kein Auto-Rotieren, kein Ticker. Hover auf dem Screenshot zoomt leicht, unter
  `prefers-reduced-motion: reduce` nicht.
- Journals und Papers haben keine Client-Logik. Sie sind Links.

### 3.5 Gestaltung

NERV-Sprache mit den vorhandenen Variablen aus `styles/index.css`, monospace, Sektionslabel im Muster
`>_ [ fig. 1 — stories, live ]`, rechts daneben der Status ("updated 2h ago · 3,189 stories from 39
channels"). Bausteine, umgesetzt in `src/styles/landing-live.css`:

- Lead-Karte: Bild 16:9 (Journal 21:9), Badge (STORY / JOURNAL / PAPER), Titel in Orbitron, ein
  Absatz, Meta-Zeile. Stories zeigen ein Signifikanz-Meter, Journals die Inhaltsverzeichnis-Chips,
  Papers den Evidenz-Streifen (sources analyzed, quality, license).
- Liste: sechs beziehungsweise vier Zeilen, Stories mit 96-px-Thumbnail, Journals und Papers nur
  Text. Zeilen sind komplett klickbar.
- Screenshots als Textur: `saturate(.75)` und ein Verlauf nach unten, kein Text im Bild.
- Theo-Zeile unter den Papers: gestrichelter oranger Rahmen, pulsierender Punkt, "Theo is
  researching: {Frage} · {Dauer} in · {n} sites found", Link auf `/theo.html`.
- Mobile unter 768 px: eine Spalte, Lead oben, Liste darunter; Chips scrollen horizontal.

Die Mockups aus dem Brainstorming liegen unter `.superpowers/brainstorm/239-1788951798/content/`
(`stories-cards.html` Variante B, `longreads.html` Variante A).

### 3.6 Hero-Zahlen

Der Hero zeigt "750K+ Sites". Die Datenbank hat 1.759.673. Die Werte für Sites und Länder bekommen
`data-stat="sites"` und `data-stat="countries"`, und die Landing-Route ersetzt sie im Shell-HTML durch
formatierte Live-Werte ("1.76M" aus der gecachten Stats-Abfrage, "98" als Zahl der Länder mit
kuratierten Sites). Empires und Sources bleiben statisch "30+" und "20+". Das ist die einzige Änderung
am Hero. Im statischen Rückfall bleiben die heutigen Texte stehen.

## 4. Fehlerfälle

- Sidecar oder API antworten nicht: nginx liefert das statische `index.html`, die Live-Sektionen
  fehlen, alles andere funktioniert. Kein zweiter Renderer, wie bei den anderen SSR-Seiten.
- Payload leer oder unbekannter Typ im Client: `landingMain.tsx` rendert nichts und meldet nichts.
- `/api/news/feed` schlägt beim Chip-Klick fehl: der bisherige Inhalt bleibt, der Chip springt
  zurück, ein kurzer Hinweis "feed unavailable" erscheint in der Statuszeile.
- Screenshot fehlt (404): `LazyImage`-Fallback wie in den Story-Seiten.

## 5. Tests

- **vitest:** `landingMeta` liefert Titel und Description; `renderToString(<LandingLive/>)` mit einem
  Fixture-Payload enthält alle Story-, Journal- und Paper-Links, keine "undefined"-Strings, und rendert
  ohne Theo-Zeile, wenn `theo` null ist. Bestehender Route-Guard-Test um `landing` erweitern.
- **pytest (DB-los):** der Payload-Builder bekommt Fake-Rows und liefert die Lead-Regel korrekt
  (48-Stunden-Fenster, kein Duplikat, Fallback auf die 7 neuesten), Wortzahl und Lesezeit, Sektionen
  ohne "Sources"/"Videos".
- **Build-Gate:** `size-limit` auf `dist/assets/landing-*.js` mit 80 kB Brotli im
  `lint-frontend`-Job, gleich nach `npm run build`.
- **Nach dem Deploy (Playwright):** `/` liefert SSR-HTML mit sieben Story-Links (Lead plus sechs), null
  Hydration-Fehler in der Konsole, LCP-Element ist das Hero-Bild, und ein Chip-Klick tauscht den Inhalt.
  Crawler-Sicht mit JS-Blockade prüfen (Lehre aus den 2.100 Soft-404-Seiten).

## 6. Änderungen außerhalb des Codes

- `ancientnerds-nginx-config`: `location = /` und der neue `@home_static`-Block. Der Deploy wendet
  die Datei automatisch an (`nginx -t` und reload), aber Konfigurationsänderungen brauchen deine
  Freigabe vor dem Push.
- Kein Migrations-, Compose- oder Secrets-Bedarf.

## 7. Umsetzungsreihenfolge

1. Typen, Registry, `landingMeta`, `LandingLive` mit Fixture, vitest.
2. `landing_html.py` mit Payload-Builder und pytest, Route `/home` in `main.py`.
3. `index.html`: `#root`, `data-stat`-Spans, Sektionen entfernen, `landingMain.tsx` einbinden;
   Service-Worker-Denylist; CSS.
4. Stories-Interaktion (Chips, Load more, relative Zeit).
5. nginx-Block, size-limit, Deploy, Playwright-Prüfung, GSC-Beobachtung der Startseite.
