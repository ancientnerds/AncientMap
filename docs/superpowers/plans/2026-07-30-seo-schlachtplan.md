# SEO-Schlachtplan: Von 6 indexierten Seiten zu echter Sichtbarkeit

> **For agentic workers:** Dies ist der Master-Plan. Jede Phase mit Code-Arbeit bekommt bei Ausführungsstart einen eigenen detaillierten Implementation-Plan (superpowers:writing-plans), der dann mit superpowers:subagent-driven-development oder superpowers:executing-plans abgearbeitet wird.

**Goal:** Die wertvollen Inhalte (Theo-Papers, Journals, Stories, 5.000 kuratierte Sites, API) für Google crawlbar und indexierbar machen und die organische Sichtbarkeit von ~0 Non-Brand-Klicks auf messbares Wachstum bringen.

**Architecture:** Das Erfolgsmuster existiert bereits im Haus: `api/routes/articles_html.py` rendert server-seitiges HTML (`/articles/{slug}` = 2.400 Wörter echter Text, von nginx an die API geproxt). Dieses Muster wird auf Research-Papers, Stories und Site-Seiten ausgeweitet. Dazu: Sitemap vervollständigen, Orphan-Pages verlinken, interne Linkstruktur aufbauen, Schema.org-Markup, Distribution.

**Tech Stack:** FastAPI (HTML-Routen), nginx (Proxy-Regeln in `ancientnerds-nginx-config`), `pipeline/article_html_renderer.py` (Render-Muster), `api/routes/sitemap.py`, `scripts/gsc_report.py` (Messung).

---

## Ist-Zustand (gemessen 2026-07-30)

| Fakt | Messung |
|---|---|
| Indexierte Seiten | 6 (nur statische Einstiege) |
| Sitemap-URLs indexiert | **0 von 5.014** |
| Sitemap zuletzt von Google gelesen | 20. Feb (1×; am 30.07. per API neu eingereicht → pending) |
| Klicks 90 Tage | 126, fast ausschließlich Brand („ancient nerds") |
| Body-Text der SPA-Seiten für Googlebot | api.html: 3 Wörter, library.html: 21, search.html: 36, theo.html: 41, articles.html: 88, news.html: 92 |
| Artikel-Detailseiten (`/articles/{slug}`) | ✅ 2.416 Wörter echtes HTML — bestes Asset |
| `/news-archive/` | 32.123 Wörter auf EINER Seite, 211 Links **fast alle zu YouTube**, keine internen Story-URLs |
| `/research/{slug}` (Theo-Papers) | ❌ liefert Homepage-Shell — die 10 Papers existieren nur als JSON-API |
| Orphan-Pages (nicht verlinkt + nicht in Sitemap) | search.html, theo.html, library.html |
| In Sitemap fehlend | api.html, search.html, theo.html, library.html, alle `/research/`-URLs |
| Homepage-HTML-Links | api, articles, globe, lyra, news, radar + Legal — **nicht**: search, theo, library, /articles/, /news-archive/ |
| site.html?id= Seiten | nginx liefert Bots individuelle Meta-Tags ✅, aber Body ist leere SPA-Shell ❌ |

**Diagnose in einem Satz:** Google bekommt fast nirgends echten HTML-Inhalt und hat kaum crawlbare Pfade — die Domain ist jung, also crawlt Google nur, was billig und lohnend aussieht, und das ist derzeit fast nichts.

**Drei Gesetze, an denen sich jede Maßnahme messen lassen muss:**
1. **Crawlbarer Pfad** — jede wichtige URL ist über normale `<a href>`-Ketten von der Homepage erreichbar (Sitemap allein reicht bei junger Domain nicht).
2. **Echter Inhalt im HTML** — der Googlebot sieht den Text ohne JavaScript.
3. **Autorität** — Backlinks und Erwähnungen entscheiden, wie viel Google überhaupt crawlt. Technik ist die Voraussetzung, Autorität der Multiplikator.

---

## Phase 0: Sofortmaßnahmen — ERLEDIGT 2026-07-30

- [x] GSC-API-Zugriff eingerichtet (`scripts/gsc_report.py`)
- [x] Sitemap per API neu eingereicht (Google kannte keinen einzigen Artikel seit Februar)

## Phase 1: Quick Wins — Orphans anschließen (½ Tag, sofort machbar)

**Files:** `api/routes/sitemap.py`, Landing-Page-Quelle von `index.html` (Footer/Nav), ggf. `ancient-nerds-map/*.html` Einstiegsseiten

- [ ] **1.1 Sitemap vervollständigen:** `api.html`, `search.html`, `theo.html`, `library.html` als statische Einträge in `sitemap.py` ergänzen (Muster der bestehenden Einträge, priority 0.7).
- [ ] **1.2 Footer-Navigation mit echten HTML-Links auf ALLE Bereiche:** search, theo, library, `/articles/`, `/news-archive/` — auf der Homepage und idealerweise auf allen statischen Einstiegsseiten. Das schafft die Crawl-Pfade, die aktuell komplett fehlen.
- [ ] **1.3 `/articles/`-Listing prüfen/anreichern:** aktuell nur 12 Links und 148 Wörter — alle Journals mit Teaser-Absatz listen (in `articles_html.py`).
- [ ] **1.4 Deploy + `python scripts/gsc_report.py resubmit`**

**Erwarteter Effekt:** Die vier Orphan-Seiten werden auffindbar; Google bekommt erstmals Crawl-Pfade zu Journals und News-Archiv.

## Phase 2: Theo-Papers als HTML-Seiten (1–2 Tage — größter Content-Hebel)

Die 10 publizierten Papers (CC BY 4.0, Tausende Wörter Unikat-Recherche mit Zitaten) sind aktuell für Google **unsichtbar**. Das ist das wertvollste ungenutzte Asset.

**Files:** Neu `api/routes/research_html.py` (Muster: `articles_html.py`), `ancientnerds-nginx-config` (Proxy `/research/` → API), `api/routes/sitemap.py` (Papers aus DB ergänzen), `api/main.py` (Router registrieren)

- [ ] **2.1 `/research/` Listing-Seite:** server-gerendert, alle Papers mit Titel, Frage, Summary, Datum, Quality-Badge.
- [ ] **2.2 `/research/{slug}` Volltext-Seite:** komplettes Paper als HTML, Zitationsliste, CC-BY-4.0-Attribution, `Schema.org ScholarlyArticle`-Markup (JSON-LD), Canonical auf sich selbst.
- [ ] **2.3 nginx-Route** `/research/` an die API proxen (exakt wie `/articles/`).
- [ ] **2.4 Sitemap:** Papers dynamisch aus der DB ergänzen (wie Artikel, priority 0.9).
- [ ] **2.5 Interne Verlinkung:** theo.html-SPA und Footer verlinken auf `/research/`; jedes Paper verlinkt verwandte Site-Seiten.

**Erwarteter Effekt:** 11 neue Seiten mit dichtem Long-Tail-Content („pineal gland DMT near-death", „mustatils Saudi Arabia" …) — genau die Art Inhalt, die junge Domains ranken kann, weil kaum Konkurrenz existiert.

## Phase 3: Stories einzeln crawlbar machen (2–3 Tage)

`/news-archive/` ist eine einzige 32.000-Wörter-Seite, deren 211 Links fast alle **zu YouTube** führen — die Link-Power fließt ab, keine Story hat eine eigene URL.

**Files:** `api/routes/articles_html.py` (bzw. neues `news_html.py`), `ancientnerds-nginx-config`, `api/routes/sitemap.py`

- [ ] **3.1 Individuelle Story-URLs** `/news-archive/{slug}`: Titel, Zusammenfassung, eingebettetes/verlinktes Video, **interne Links auf erwähnte Sites** (NewsItem hat `site_id`!), `NewsArticle`-Schema.
- [ ] **3.2 Archiv paginieren** (z.B. 25 Stories/Seite mit rel-prev/next-Verlinkung) statt einer Monsterseite.
- [ ] **3.3 Interne Links vor externe:** jede Story verlinkt zuerst die eigene Site-Seite, dann erst YouTube.
- [ ] **3.4 Sitemap:** Story-URLs ergänzen.

**Erwarteter Effekt:** Hunderte indexierbare News-Seiten mit Aktualitätssignal (täglich neue Inhalte = Grund für Google, öfter zu crawlen — auch die Sitemap).

## Phase 4: Die 5.000 Site-Seiten erschließen (3–5 Tage — größter struktureller Hebel)

**Files:** Neu `api/routes/sites_html.py`, `ancientnerds-nginx-config`, `api/routes/sitemap.py`

- [ ] **4.1 Browse-Struktur** `/sites/` → `/sites/{country}/` (server-gerendert): Länderübersicht → Liste aller kuratierten Sites des Landes mit Name, Periode, Typ, Kurzbeschreibung und Link. Das ist der fehlende Crawl-Pfad zu allen 5.000 Seiten.
- [ ] **4.2 Site-Detail mit echtem Inhalt:** Entscheidung nötig (bei Ausführung klären):
  - **Option A (empfohlen):** SSR-Seiten `/sites/{country}/{slug}` als kanonische URLs; `site.html?id=` bekommt `rel=canonical` auf die neue URL. Saubere, keyword-tragende URLs statt UUID-Query-Params.
  - **Option B (minimal):** Der bestehende nginx-Bot-Mechanismus liefert zusätzlich zum Meta-Tag den Beschreibungstext + Fakten als HTML-Body aus.
- [ ] **4.3 `Place`/`TouristAttraction`-Schema** mit Koordinaten pro Site-Seite.
- [ ] **4.4 Sitemap auf die neuen URLs umstellen** (gestaffelt einreichen; 5.000 auf einmal bleibt bei junger Domain trotzdem ein Marathon — Erwartung: Indexierung über Monate).
- [ ] **4.5 Querverlinkung:** Site-Seite ↔ Stories (site_id) ↔ Papers ↔ Journals. Interne Vernetzung ist bei 5.000 Seiten das Ranking-Rückgrat.

## Phase 5: Technik-Feinschliff (1 Tag, parallel möglich)

- [ ] **5.1 Schema.org überall:** `Article` (Journals), `ScholarlyArticle` (Papers), `NewsArticle` (Stories), `Dataset`/`WebAPI` (api.html), `BreadcrumbList` auf allen SSR-Seiten.
- [ ] **5.2 api.html mit statischem Doku-Text** (3 Wörter → echte Doku): API-Dokus sind Backlink-Magneten für Entwickler; die `/api/v1`-Doku als HTML rendern oder statisch einbetten.
- [ ] **5.3 search.html/library.html:** statischen Einführungstext (200+ Wörter) ins HTML legen — beschreibt, was das Tool kann, welche Quellen (Pleiades, DARE, UNESCO …) durchsucht werden.
- [ ] **5.4 OG-Images pro Content-Typ** (Papers/Stories/Sites) für Social-Sharing-CTR.

## Phase 6: Autorität & Distribution (laufend, kein Code — der Multiplikator)

- [ ] **6.1 Papers streuen:** CC BY 4.0 ist ein Geschenk — Zenodo/OSF-Upload mit DOI (zitierbar!), Medium-Crosspost mit Canonical-Link zurück (Account existiert), passende Subreddits, Hacker News (Show HN für die Map/API), Archäologie-Newsletter.
- [ ] **6.2 API in Verzeichnisse:** GitHub awesome-Listen (awesome-archaeology, public-apis), Open-Data-Verzeichnisse — jede Listung ist ein dauerhafter Backlink.
- [ ] **6.3 Quellen-Communities:** Pleiades/DARE/Wikidata-Communities über die Weiternutzung informieren — legitime Erwähnungen/Links von Autoritäts-Domains.
- [ ] **6.4 YouTube-Beschreibungen** der eigenen Kanäle: Links auf Site-/Story-Seiten statt nur Homepage.
- [ ] **6.5 Monitoring-Routine:** wöchentlich `python scripts/gsc_report.py summary --days 28` + `sitemaps`; KPIs: indexierte Seiten, Non-Brand-Klicks, Impressionen. Nach jedem Phasen-Deploy: `resubmit` + Stichproben-`inspect`.

---

## Priorisierung & realistische Erwartung

**Reihenfolge:** 1 → 2 → 3 → 5 → 4 → 6 (6 beginnt parallel ab Phase-2-Abschluss, denn ohne crawlbare Papers gibt es nichts zu verlinken).

Phase 4 ist bewusst NACH 2/3/5: Die 5.000 Site-Seiten sind der größte Brocken, aber Papers/Stories/Journals ranken schneller (weniger Konkurrenz, mehr Textmasse pro Seite) und bauen die Autorität auf, die Google braucht, um 5.000 Seiten überhaupt crawlen zu wollen.

**Ehrliche Erwartung:** Die Domain ist jung. Selbst mit perfekter Technik dauert es 4–12 Wochen, bis Google nennenswert indexiert, und Monate, bis Non-Brand-Traffic sichtbar wächst. Der Kompass: erst steigen „indexierte Seiten", dann Impressionen, dann Klicks — in dieser Reihenfolge messen und Geduld behalten.
