# Bestandsaufnahme 2026-10-01: vier Beobachtungen des Owners

Auftrag (erster Teil): Bestandsaufnahme, Fehler finden, **Lösungen nur vorschlagen**. Die Abschnitte 1–4 sind
diese Diagnose; alle Produktionszugriffe dafür waren lesend (HTTP, `psql` SELECT, Umami-DB SELECT,
Search-Console-Abfragen, Browser-Läufe mit blockiertem Tracker und blockiertem Mapbox).
Messzeitpunkt: 2026-10-01 vormittags. Produktion = `ancientnerds.com` (Commit-Stand wie deployed).

## Umsetzung (Nachtrag 2026-10-01, auf Entscheidung des Owners)

Branch `fix/2026-10-01-user-report` (Worktree, Basis `origin/main` df03b5d):

| Commit | Was |
|---|---|
| `0fd0304` | Punkt 1: Journal-Hash dekodieren (`utils/articleHash.ts`); Test mit den drei echten Titeln, vorher rot |
| `19d1d3d` | Punkt 2: 410-Seite einer zurückgezogenen Story mit Archivsuche, 5 neuesten Stories, Globus-Link; 410 bleibt; alle anderen Fehlerseiten byte-identisch |
| `c95fd76` | Punkt 3: Schrift-Sperre in Summarizer, Post-Schritt und Verifier über den vorhandenen Detektor; Prompt-Vorgabe |
| `12fe989` | Punkt 4: Touch-Steuerung (ein Finger dreht, Pinch zoomt zum Fingerpunkt, Nachlauf, kein Pan); Desktop nachweislich unverändert |
| `2b15805` | Aufräumen: toter `useGlobeEvents.ts` entfernt |
| `a1e3c64` | Aufräumen: falscher Docstring im Scorer |
| `21b8574` | **Eigentliche Ursache von 8351/8359**: Boot-Migration v14 durch die Namens-Sperre des Matchers geführt (siehe Korrektur in Abschnitt 3) |

Datenkorrektur (Owner-Freigabe, eine Transaktion, jede Zeile per Vorher-Wert abgesichert, nach Commit
nachgezählt): 8351, 8359, 6342, 5733, 5797 minimal, 6266 auf Englisch neu aus dem Transkript. Protokoll, Diff,
Apply/Rollback-SQL: `output/remediation/story_script_bleed_2026-10-01/`. Danach flaggt der Detektor 0 von
3.489 Stories; neue URLs 200, alte 301.

Abweichungen von der Auswahl: kein eigener Doppeltipp-Zoom (Chrome/Android zoomt schon per `dblclick`,
gemessen 2,41 → 1,98; ein zweiter Pfad hätte doppelt gezoomt). Nicht getestet: Touch im echten Mapbox-Modus
(bräuchte einen bezahlten Kartenaufruf), iOS Safari.

Offen, Entscheidung des Owners: **86 Stories (69 öffentlich) tragen den Namen eines anderen Sites in der
Überschrift**, von v14 bei früheren Boots geschrieben (z. B. „Mausoleum of the Atilii: scale, terracotta army,
and mercury evidence" für das Qin-Shi-Huang-Mausoleum). Einige sind dieselbe Stätte unter verhörtem Namen
(„Black Pyramid of Dasher"); eine Rückabwicklung braucht Einzelurteile, Vorlage
`scripts/repair_garble_alias_damage.py` (14.09.). Ebenso offen: Die Seiten von 8351 und 8359 zeigen als
Site-Etikett weiterhin den OSM-Namen in Landesschrift (`unified_sites.name` der verknüpften
`osm_historic`-Datensätze, nur diese 2 öffentlichen Stories betroffen); in 8351 widersprechen sich Facts und
Post („2021 monograph"/„Rudnik Glava" gegen „2010 … paper"/„Rudna Glava").

## Kurzfassung

| # | Beobachtung | Befund | Ursache (belegt) | Schwere | Aufwand (Schätzung) |
|---|---|---|---|---|---|
| 1 | Neuester Journal-Artikel auf `/articles.html` lässt sich nicht öffnen | Reproduziert. 3 von 26 Journalen öffnen nicht: Nr. 77 (neuester), 72, 52 | Hash-Routing vergleicht den **percent-kodierten** `location.hash` mit einem Slug, der Akzente enthält (`á`, `ç`, `ö`). Seit 2026-02-18 im Code, sichtbar seit Titel Akzente tragen | hoch (jede Woche neu, wenn ein Titel einen Akzent hat) | 1 Zeile + Test |
| 2 | `/news-archive/pittsburgh-…-7458` „404", wird aber besucht | Es ist **410**, nicht 404, und es ist so gewollt. Kein Routing-Fehler. 12 % aller Story-Aufrufe (Umami) und 24 % der Google-Klicks auf Story-Seiten (Search Console, 28 Tage) treffen aber solche Seiten | Seit 2026-09-11 liefern Stories mit `significance < 2` 410. Suchmaschinen verarbeiten das noch (Recrawl läuft). Darunter liegt ein **Design-Konflikt**: `significance = 1` bedeutet „keine Archäologie" *und* „Verifier hat verworfen" | mittel | Entscheidung des Owners, danach klein |
| 3 | Kyrillische Zeichen in der Überschrift von Story 8351 | Bestätigt. Es ist **serbisches** Kyrillisch (kein Russisch): der OSM-Name des verknüpften Sites, von der Boot-Migration v14 eingesetzt (Korrektur, siehe Abschnitt 3). Zusätzlich 5 weitere Stories, 4 davon mit Modell-Drift ins Chinesische | Ein Detektor für „LLM language bleed" **existiert** (`theo_citations.py`), hängt aber nur an Theo-Papers und Bildunterschriften, nicht an der Story-Pipeline. Probelauf: er flaggt genau diese 6 Stories, 0 Fehlalarme in 3.489 | mittel (6 von 3.489 Stories, 5 öffentlich sichtbar) | klein |
| 4 | Globus auf Mobile nicht drehbar, Pinch-Zoom fehlt, Verschieben unerwünscht | Reproduziert und gemessen. Ein Finger: nichts. Pinch: nichts. Zwei Finger: **verschiebt den Globus** (ungewollt) | Drehen und Zoomen sind nur für Maus/Mausrad implementiert. `OrbitControls` hat `enableRotate=false` und `enableZoom=false`, aber `enablePan=true` | hoch für Handy-Nutzer | mittel |

Reihenfolge-Empfehlung: 1 (trivial, sichtbar), 4 (größte Wirkung), 3 (Qualität und Schutz), 2 (zuerst Entscheidung).

---

## 1. `/articles.html`: neuester Artikel öffnet nicht

### Befund

Browser-Lauf gegen Produktion (Playwright, Chromium 1280×900, Service Worker und Tracker blockiert): Auf
`/articles.html` Hero-Karte (Button „Read Journal" und Klick auf die Karte) sowie alle 25 Grid-Karten
angeklickt, danach geprüft, ob `.articles-reader` im DOM steht.

- Hero (Journal 77, „…Sacsayhuamán Waterworks…"): öffnet **nicht**.
- Grid-Karte 4 (Journal 72, „…Sayburç Chamber…"): öffnet **nicht**.
- Grid-Karte 22 (Journal 52, „…Göbekli Tepe Porthole Door…"): öffnet **nicht**.
- Alle übrigen 23 Grid-Karten: öffnen.
- Keine JavaScript-Fehler, keine Konsolenfehler. Das Muster deckt sich exakt mit der Menge der Journale,
  deren Slug Nicht-ASCII-Zeichen enthält (Abfrage von `/api/news/articles?limit=50` plus `slugify`).

Die SEO-Variante funktioniert: `/articles/week-of-september-21-…-sacsayhuam%C3%A1n-…` liefert 200, die
Sitemap (`sitemap-articles.xml`, 27 URLs) ist in Ordnung. Betroffen ist nur die Standalone-SPA.

### Ursache

`ancient-nerds-map/src/pages/ArticlesPage.tsx`:

- `openArticle` (Zeile 689-691) setzt `window.location.hash = slugify(article.title)`.
- `resolveHash` (Zeile 648-663) liest `window.location.hash.slice(1)` und vergleicht mit
  `slugify(a.title) === hash` (Zeile 655).
- `slugify` (`src/seo/meta.ts:95-102`) behält Unicode-Buchstaben (`\p{L}`), also bleibt `á` im Slug.
- Ein Browser liefert `location.hash` **percent-kodiert** zurück. Gemessen: `#…sacsayhuam%C3%A1n-…`.
  `"…sacsayhuamán…" === "…sacsayhuam%C3%A1n…"` ist falsch, `match` bleibt leer, der `else`-Zweig fällt
  still in die Listenansicht zurück. Deshalb: kein Fehler, nur „es passiert nichts".

Herkunft: Hash-Routing seit Commit `5f109c5` (2026-02-18). Der Fehler schlief, bis Titel Akzente trugen.
Wiederholungsgefahr: Lyra erzeugt die Titel aus Fundnamen („Göbekli", „Çatalhöyük", „Sacsayhuamán"),
bisher 3 von 26 Journalen (12 %).

### Lösungsvorschlag

Kern (empfohlen): in `resolveHash` den Hash **dekodieren**, bevor verglichen wird.

- Die Auswahl „welches Journal gehört zu diesem Hash" in eine reine Funktion auslagern (z. B.
  `journalForHash(hash, articles)`), die `decodeURIComponent` anwendet. So ist sie ohne DOM testbar.
- `decodeURIComponent` wirft bei kaputten Sequenzen (`#%`, `#%E0%A4%A`). Das ist Eingabe-Validierung
  für eine vom Nutzer editierbare URL, kein Fallback-Code: ein ungültiger Hash heißt „kein Treffer",
  also Listenansicht (so ist es heute für unbekannte Hashes). Das bewusst und sichtbar im Code
  entscheiden, nicht per leerem `catch`.
- Test (Vitest, kein ArticlesPage-Test vorhanden; `src/seo/__tests__/render.test.tsx` deckt nur die
  Payload-Ansichten): die drei echten Titel (Sacsayhuamán, Sayburç, Göbekli) mit kodiertem Hash plus
  ein ASCII-Titel plus ein ungültiger Hash.

Erwogen und verworfen:
- Hash auf die numerische ID umstellen: bricht vorhandene Lesezeichen, Slugs im Hash sind das
  dokumentierte Verhalten (Datei-Kopfkommentar: „must keep working unchanged").
- `/articles.html#slug` auf `/articles/slug` umleiten: ändert das Produktverhalten der SPA.

Nachprüfung nach dem Fix: derselbe Klick-Durchlauf über alle 26 Karten. Erwartung: 26 von 26.

---

## 2. `/news-archive/pittsburgh-lawyer-discovers-cipher-on-boulder-plaque-in-frick-park-7458`

### Befund

- Die URL antwortet **410 Gone** (nicht 404): `<title>Story No Longer Available</title>`, `noindex`,
  `Cache-Control: public, max-age=86400`, Text „This story has been withdrawn from the archive."
- Zeile in der Produktions-DB: `id 7458`, `news_category = unverified`, **`significance = 1`**,
  `post_text` vorhanden, `score_reason` leer, `created_at 2026-07-13`.
- Die URL steht in **keinem** der 7 Sitemap-Teile (static, sites, countries, stories, research, articles,
  legacy geprüft).
- Search Console (URL-Inspection): `coverageState "Not found (404)"`, `pageFetchState NOT_FOUND`,
  zuletzt gecrawlt 2026-10-01 01:56 UTC. Zwei weitere stark geklickte Beispiele (6937, 7940) wurden
  innerhalb der letzten ~36 Stunden neu gecrawlt, ebenfalls `NOT_FOUND`. Annahme, nicht geprüft: die
  Search Console weist 404 und 410 beide als „Not found (404)" aus. Der echte Status wurde per `curl` als
  410 verifiziert.
- Google verarbeitet die Entfernung also gerade, aber noch nicht überall.

### Umfang (wie viele Besucher landen dort?)

Umami (seit 2026-09-17, 809 Story-Aufrufe auf 400 verschiedenen Stories):

| Gruppe | Aufrufe | Sitzungen |
|---|---|---|
| Story öffentlich (200) | 711 | – |
| Story zurückgezogen (410), mit externem Referrer | 60 (55 Google, 2 DuckDuckGo, 2 Bing, 1 Yahoo) | 47, auf 29 Stories verteilt |
| Story zurückgezogen (410), ohne Referrer | 36 | 17 (überwiegend Windows/de-DE: sehr wahrscheinlich eigene Prüfungen, nicht belegt) |
| Story-ID nicht in der DB (echtes 404) | 2 | 2 |

Search Console (28 Tage, 2026-09-02 bis 2026-09-29, Seiten mit `/news-archive/`):
**331 zurückgezogene Story-URLs hatten 3.900 Impressions und 99 Klicks, das sind 24 % aller 419 Klicks auf
Story-Seiten.** Einschränkung: das Fenster beginnt vor dem 410-Start (die Logik kam am 2026-09-11,
Commit `878c389`), also überzeichnet die Zahl den heutigen Stand. Umami belegt unabhängig, dass die
Google-Zugriffe nach dem Start weitergehen (55 Aufrufe in 14 Tagen).

Auffällig: die meistgeklickten zurückgezogenen Seiten sind Randthemen, nach denen Menschen aktiv suchen
(z. B. „Mysterious 40m Metallic Object … Hawara": 14 Klicks, „Solon's Egyptian travels … Atlantis": 5).

### Ursache

Kein Fehler im Routing. `story_page` (`api/routes/articles_html.py:344-391`): existiert die Zeile, ist aber
nicht mehr in `story_page_query` (`public_story_criteria`: `post_text IS NOT NULL` und
`significance IS NULL OR >= 2`), kommt 410; unbekannte ID kommt 404.

Darunter liegt ein **Bedeutungskonflikt** bei `significance = 1`:

- Der Scorer (`pipeline/lyra/prompts/rescore_significance.txt`) vergibt 1 für „Not archaeology".
- Der **Tweet-Verifier setzt dieselbe 1 auch als „Behauptungen nicht belegt"**: `tweet_verifier.py:280-283`
  (REJECT) und `:524-527` (Web-Verify REJECT) schreiben `news_category = "unverified"` und
  `significance = 1`.
- Verteilung der 876 zurückgezogenen von 3.489 Stories mit Text (25 %): **573 `unverified`** (351 davon ohne
  `score_reason`, weil der Scorer `significance IS NULL` voraussetzt und sie übersprungen hat), 149
  `speculative`, 118 `general`, 36 verteilt auf weitere Kategorien.
- Die 410-Seite nennt absichtlich keinen Grund (Kommentar im Code), Besucher und Suchmaschinen sehen beide
  Fälle gleich.
- Der Kopfkommentar von `significance_scorer.py:5-6` behauptet, Items mit 1 bekämen `post_text = NULL`.
  Der Code tut das nicht (nur `significance`). Kommentar ist veraltet.

Inhaltliche Stichprobe (nicht gegen Transkripte geprüft, nur Überschriften): unter den 39 zurückgezogenen
Stories, die Umami gesehen hat (29 davon über Suchmaschinen), stehen mehrere, die wie normale Archäologie
klingen, z. B. 8468 („10,000 BC
Kilisik androgynous idol parallels Karahan Tepe…", angelegt 2026-09-26), 7796 („54 granite columns at Baalbek
sourced from Aswan quarry"), 7662 („Temple of the Feathered Serpent burned and hidden; 200+ burials").
Ob der Verifier dort zu Recht verworfen hat, ist eine redaktionelle Frage. Die Liste liegt im Anhang A.

### Lösungsvorschläge (Entscheidung nötig)

**Frage an den Owner:** Sollen vom Verifier verworfene Stories (`unverified`, 573) genauso behandelt werden
wie „keine Archäologie" (410 und raus aus dem Feed)? Davon hängt alles Weitere ab.

- **Option A, empfohlen als Standard: Verhalten belassen, Besucher besser auffangen.** 410 ist für
  Suchmaschinen die richtige Antwort, der Schwanz läuft aus. Die 410-Seite für Stories
  (`render_error_html("Story", 410, …)`, `pipeline/article_html_renderer.py:451-487`, geteilt mit allen
  Fehlerseiten) um echte Auswege ergänzen: Suchfeld auf `/news-archive/`, die neuesten Stories, Link zum
  Globus. Heute stehen nur drei allgemeine Links dort. Keine Weiterleitung (Soft-404-Risiko, Google behandelt
  Weiterleitungen auf unverwandte Seiten als 404).
- **Option B, nur ergänzend: Beschleunigen.** Die zurückgezogenen URLs per IndexNow melden (Bing, DuckDuckGo,
  Yahoo, 5 der 60 externen Aufrufe). Für Google gibt es keinen programmatischen Weg; das manuelle
  Removals-Tool wirkt nur 6 Monate und lohnt bei einem ohnehin laufenden Recrawl nicht.
- **Option C, falls der Owner Verifier-Rejects nicht verstecken will:** `unverified` von `significance = 1`
  trennen (z. B. eigenes Gate-Kriterium über `news_category`, nicht über die Zahl). Das ist ein
  Schema-/Gate-Eingriff in `public_story_criteria` (Feed, Seitenabfrage, Sitemap, Related-Links, API) und
  braucht eine Rückfrage (Migration oder Datenänderung). Die 29 über Suche besuchten Stories wären dann die
  Kandidaten zur Einzelprüfung.
- In jedem Fall: den veralteten Docstring in `significance_scorer.py` korrigieren.

---

## 3. Kyrillische Zeichen in der Überschrift (`/news-archive/локалитет-…-8351`)

### Befund

- Die Seite antwortet 200 (Story 8351, `significance 3`, `technology`, angelegt 2026-09-17 13:59:43,
  `verified`, `rescored`).
- Überschrift: „Локалитет Беловоде код Петровца на Млави furnaces: earliest secure copper smelting evidence
  worldwide, dated to 4900 BC". Das ist **serbisches** Kyrillisch, nicht Russisch: „Fundort Belovode bei
  Petrovac na Mlavi", der serbische Name des Fundplatzes.
- Dieselbe Phrase steckt in `headline`, `summary`, `post_text` **und** `facts`. `site_name_extracted` ist
  dagegen korrekt „Belovode".
- Quellvideo `wQ4VNGqFV1Q` („Vinča people (from genetics, writing, tech, etc.)", Timeless with Fred Snyder) ist
  englisch. Transkript (66.829 Zeichen), Beschreibung, Titel und Tags enthalten **kein einziges kyrillisches
  Zeichen**.
- **Korrektur (Nachtrag, belegt im Lyra-Log und im Code):** Nicht das Modell hat die Phrase erzeugt. Der
  Summarizer schrieb um 13:59 „Belovode furnaces: …" (im Post-Schritt um 14:15 als Überschrift des Modells
  geloggt). Um 14:04 verknüpfte der `site_identifier` die Story über eine selbst recherchierte Namensvariante
  „Беловоде (Serbian Cyrillic)" mit dem `osm_historic`-Datensatz „Локалитет Беловоде код Петровца на Млави".
  Danach ersetzte die Lyra-Boot-Migration **v14** (`orchestrator._run_migrations`, läuft bei jedem Start) in
  Überschrift, Summary, Post und Facts „Belovode" durch diesen Site-Namen, ohne die Gleichnamigkeits-Sperre,
  die der Matcher seit 14.09. hat. 8359 genauso („Dawenkou" → „大汶口遗址公园", ebenfalls `osm_historic`).
  Die anfängliche Aussage „vom Modell erzeugt" war falsch; sie stützte sich nur auf den `created_at`.
- Der Slug enthält die kyrillischen Wörter, weil `slugify` Unicode-Buchstaben behält. Die URL funktioniert,
  ist aber unleserlich und für deutsch-/englischsprachige Teiler hässlich.

### Umfang

Scan aller 3.489 öffentlich gespeicherten Stories (Überschrift, Summary, Post, Facts) auf Buchstaben außerhalb
von Latein, Zeichen-für-Zeichen per Unicode-Name:

| Story | Feld(er) | Fund | `significance` (sichtbar?) |
|---|---|---|---|
| 8351 | Überschrift, Summary, Post, Facts | serbisches Kyrillisch (Fundortname) | 3, sichtbar |
| 8359 | Überschrift, Summary, Post | „China's 大汶口遗址公园 holds oldest elongated skulls…" | 2, sichtbar |
| 6342 | Überschrift, Summary | „…natural volcanic formation vs人工 structure" (Sprachwechsel mitten im Satz) | 2, sichtbar |
| 6266 | alle Felder | **komplette Story auf Chinesisch** („伪造说逻辑漏洞：1960年代无精密加工能力") | 3, sichtbar |
| 5733 | Facts | „Researchers科尔 Chromemer and Regillo…" (Sprachwechsel mitten im Wort) | 3, sichtbar |
| 5797 | Post | „…have存在的问题 — Göbekli Tepe…" | 1, zurückgezogen |

Griechische Treffer (6289, 6294, 7128: Odyssee-Zitat, π/φ, °) sind legitim. Die 26 Journale wurden ebenfalls
gescannt: alle Treffer sind legitim (Originalschreibweisen in Klammern wie „單于", „天の浮石", „牺牲坑", der
Maya-Apostroph in „Kʼinich", ein YouTube-Titel mit mathematischen Fettbuchstaben). Nicht gescannt: Site-
Beschreibungen, Theo-Papers, Radar-Einträge.

### Ursache

- **Zwei Mechanismen (Nachtrag).** 8351 und 8359: die Boot-Migration v14 setzt bei jedem Lyra-Start den Namen
  des verknüpften Sites in den Story-Text, auch wenn er ein anderer Ort oder in Landesschrift ist (siehe Befund;
  behoben in `21b8574`, dieselbe Sperre wie im Matcher). Sie hat zusätzlich 86 Überschriften mit dem Namen
  eines anderen Sites versehen (offen, siehe Umsetzung). 6342, 5733, 5797, 6266: Sprachwechsel des Modells
  (MiniMax) mitten im Satz bzw. die ganze Story; dagegen hilft die Sperre in Summarizer, Post-Schritt und
  Verifier (`c95fd76`). Die Sperre allein hätte 8351 nicht verhindert, weil v14 *nach* diesen Schritten schreibt.
- **Die Story-Pipeline prüft die Schrift nirgends, obwohl der Detektor im selben Paket liegt.**
  `pipeline/lyra/theo_citations.py:486-553` hat `contains_non_latin_script(text)` und
  `detect_language_bleed(text)` (CJK, Kyrillisch, Arabisch; Griechisch bewusst ausgenommen; Klammer-Glossen
  wie „(遮光器, "light-blocker")" bleiben erlaubt). Der Kommentar dort nennt das Fehlerbild ausdrücklich
  „MiniMax drift". Aufgerufen wird er nur vom Theo-Judge/Quality-Gate (`judge.py`, `quality_gate.py`) und von
  der Bildunterschriften-Bereinigung (`clean_image_titles.py`). `summarizer.py` und `tweet_generator.py`
  rufen ihn nicht auf.
- **Probelauf mit dem vorhandenen Detektor** über alle 3.489 Stories (Überschrift, Summary, Post, Facts):
  flaggt genau 8351, 8359, 6342, 6266, 5733, 5797 und sonst keine Story. Es gibt keinen Fehlalarm, die
  Griechisch-Treffer (6289, 6294, 7128) bleiben unmarkiert.
- **Die Überschrift entsteht im Summarizer:** `summarizer.py:401` übernimmt `topic["headline"]` des Modells,
  `:423-424` baut die Summary aus Überschrift plus ersten Facts. `tweet_generator.py` ordnet Posts den fertigen
  Items nur über die Überschrift zu.
- Der Summarizer-Prompt (`pipeline/lyra/prompts/summary.txt:12-13`) verlangt „most common English name" nur für
  `primary_site`. Für Überschrift, Facts und Summary gibt es keine Sprach- oder Schriftvorgabe.
- Der Verifier prüft Behauptungen und Namensschreibung gegen Transkript und Titel (`verify_tweets.txt`), nicht
  die Schrift. Ein serbischer Fundortname, den das Modell korrekt zuordnet, besteht ihn.
- In Produktion läuft `LYRA_LLM_BACKEND=minimax` (VPS `.env` und Container geprüft). Dann ersetzt `call_api`
  jeden konfigurierten `claude-*`-Namen durch `MINIMAX_MODEL` (`pipeline/lyra/config.py:417-419`). Der
  Sprachwechsel mitten im Satz („vs人工", „have存在的问题") ist ein typisches Fehlerbild chinesisch
  trainierter Modelle. Plausibel, aber für die April-Zeilen **nicht belegt**: ich konnte nicht prüfen, welches
  Backend im April lief.
- Die Namens-Korrektur im Verifier (`tweet_verifier.py:293-315`, Ersetzung „gleiche ersten 3 Buchstaben")
  wurde durch Lesen als Quelle ausgeschlossen: sie ersetzt einzelne Wörter, und ein lateinisches Wort
  teilt nie die ersten drei Buchstaben mit einem kyrillischen. Nicht durch Test belegt.

### Lösungsvorschlag

1. **Vorhandenen Detektor in die Story-Pipeline einhängen (Validierung, kein Fallback, keine neue
   Funktion).** `detect_language_bleed` für `post_text` und Facts (toleriert Klammer-Glossen),
   `contains_non_latin_script` für `headline` und `summary` (eine Überschrift braucht keine Gloss).
   Import aus `pipeline.lyra.theo_citations` (liegt in `pipeline/lyra/`, also in beiden Images; vor dem
   Push den Lyra-Import-Test aus CLAUDE.md fahren). Ob das Modul langfristig einen neutraleren Ort
   braucht, ist eine spätere Aufräumfrage. Einhängepunkte: (a) im Summarizer **bevor** das `NewsItem`
   angelegt wird (`summarizer.py:401-432`), (b) nach jeder Verifier-Änderung, denn `modified_text` und
   `corrected_text` können die Schrift ebenfalls einführen (`tweet_verifier.py:291` und `:523`).
   Verhalten bei einem Treffer: das Thema nicht veröffentlichen und die Warnung loggen. Es gibt dafür ein
   Muster im selben Code (`summarizer.py:337`, Thema wird übersprungen). Ob stattdessen der Modellaufruf
   einmal wiederholt werden soll, ist eine Entscheidung des Owners.
   Grenze des Detektors: er erkennt nur CJK-Ideogramme, Kyrillisch und Arabisch. Reines Japanisch ohne Kanji
   (Kana), Koreanisch, Hebräisch, Devanagari und Thai würden durchrutschen. Bisher kein Fall in den Daten.
2. **Prompt-Vorgabe** in `summary.txt` und den Post-Prompts: Überschrift, Summary und Facts auf Englisch,
   Fundnamen in lateinischer Umschrift, keine Landesschrift. Die Sperre bleibt trotzdem nötig, ein Prompt
   garantiert nichts.
3. **Datenkorrektur der sechs Zeilen** nach der Projektregel „Einzelurteil pro Eintrag, journalisiert":
   - 8351: Phrase in allen vier Feldern durch „Belovode" ersetzen. Der Slug ändert sich damit; die alte URL
     leitet per ID-Auflösung mit 301 auf den neuen Slug (`articles_html.py:393-398`, durch Lesen
     verifiziert, nicht getestet).
   - 6266 (ganz Chinesisch): aus dem Transkript von Video `QFPQ7jtLgB0` neu auf Englisch erzeugen oder
     zurückziehen, Entscheidung beim Owner.
   - 8359, 6342, 5733, 5797: einzelne Wörter im Satz, jeweils einzeln korrigieren (5797 ist ohnehin
     zurückgezogen).
4. Slugs mit Landesschrift allgemein (6 Stories, 3 Journale): kein Fehler, aber eine Produktentscheidung
   (Umschrift im Slug?). Nicht Teil dieses Vorschlags.

---

## 4. Globus auf dem Handy: Drehen, Zoomen, kein Verschieben

### Befund (gemessen, Produktion, Pixel-7-Emulation, echte GPU, `?demo=1`)

Kamerazustand über `window.__DEMO.getCameraState()` vor und nach CDP-Touch-Gesten (`Input.dispatchTouchEvent`),
Startpose lng 10, lat 30 (Distanz wird auf das Maximum 2,44 begrenzt):

| Geste | Vorher | Nachher | Ergebnis |
|---|---|---|---|
| 1 Finger, 160 px nach rechts | lng 10, lat 30, d 2,44 | unverändert | **keine Rotation** |
| 2 Finger spreizen (80 → 240 px) | d 2,44 | d 2,44 | **kein Zoom** |
| 2 Finger parallel, 80 px nach rechts | lng 10, lat 30, d 2,44 | lng **3,34**, lat 29,83, d 2,452 | **Globus wird verschoben** |
| danach 1 Finger, 160 px | (verschoben) | unverändert | **bleibt verschoben**, keine Rückstellung |
| Kontrolle Desktop: Maus-Drag 168 px nach rechts | lng 10, lat 30, d 2,44 | lng **−14,77**, lat 29,83, d 2,44 | rotiert (so soll es sein) |

Screenshots (vorher / nach 2-Finger-Drag + 1-Finger-Drag): Europa wandert nach rechts zum Bildrand und bleibt
dort. Seiten-Scroll tritt nicht auf (`touch-action: none` am Canvas, Wert gemessen). Keine JS-Fehler.

Die Handy-Gate-Seite (Phone-Gate) und der Weg „3D Globe" funktionieren. Frühere Messungen „Globus erreicht"
meinten das Laden, nicht die Bedienung per Touch. Das Handy-Layout-Projekt (Globus oben, GUI zugeklappt) ist
unabhängig davon und wird hier **nicht** angefasst.

### Ursache

- `src/components/Globe/rendering/sceneInit.ts:760`: `controls.enableRotate = false  // Custom arcball rotation`.
- `src/components/Globe/rendering/eventHandlers.ts:843`: `controls.enableZoom = false`.
- Die eigene Rotation (Arcball, `:263-365`) und der eigene Zoom (`createWheelHandler`, `:138-200`) hängen nur an
  `mousedown`, `mousemove`, `wheel` (`:855`, `:936-941`). In `components/Globe/` und `hooks/globe/` gibt es
  **kein** `touch*`- oder `pointer*`-Ereignis (per Suche geprüft).
- `three@0.182.0` `OrbitControls` (`node_modules/three/examples/jsm/controls/OrbitControls.js`) setzt
  `touch-action: none` am Canvas (`:478`), nimmt `touches = { ONE: ROTATE, TWO: DOLLY_PAN }` (`:371`) und
  `enablePan = true` (`:271`) und wird nirgends auf `false` gesetzt. Folge: 1 Finger → Rotation deaktiviert,
  nichts. 2 Finger → Zoom deaktiviert, **Pan aktiv** und verschiebt das Kamera-Ziel.
- Der Pan wird nie zurückgesetzt: `controls.target.set(0, 0, 0)` steht in `src/` nur im Mausrad-Handler
  (`eventHandlers.ts:191`, plus die tote Kopie in `useGlobeEvents.ts:259`), den Touch nie auslöst.
  Der Zoom-Schieberegler (`hooks/globe/useGlobeZoom.ts:75-76`) rechnet die Kamerarichtung relativ zu
  `controls.target`. Ein verschobenes Ziel verzerrt ihn vermutlich ebenfalls (aus dem Code gelesen, nicht
  getestet).
- Randbefund: `hooks/globe/useGlobeEvents.ts` ist eine zweite Kopie derselben Maus-/Rad-Handler, wird aber
  nirgends aufgerufen (nur der Export in `hooks/globe/index.ts`). Aktiv ist `setupEventHandlers`
  (`Globe.tsx:846`). Wer dort Touch nachrüstet, ändert totes Gerüst. Als eigener Schritt entfernen.

### Lösungsvorschlag (Skizze, nicht angewendet)

Ziel: Touch **zusätzlich** unterstützen, Desktop unverändert.

1. **Touch-Eingabe nur für `pointerType === 'touch'`**, am Canvas, in `setupEventHandlers`:
   `pointerdown`, `pointermove`, `pointerup`, `pointercancel`, aktive Zeiger in einer `Map`. Jeder neue
   Handler beginnt mit `if (e.pointerType !== 'touch') return`. Maus-Pfad bleibt wie er ist.
2. **Ein Finger = Rotation mit der vorhandenen Arcball-Mathematik.** Den Rotationsblock
   (`eventHandlers.ts:312-360`) in eine gemeinsame Funktion `rotateByDrag(fromX, fromY, toX, toY)`
   herausziehen, die Maus **und** Touch aufrufen. Keine zweite Kopie der Mathematik. Der Maus-Handler ruft
   dann nur noch diese Funktion auf.
3. **Zwei Finger = Pinch-Zoom.** Abstandsverhältnis der beiden Zeiger als Skalierung der Kameradistanz, mit
   exakt derselben Klemmung wie der Mausrad-Handler (`controls.minDistance`, `maxDist`). Dafür den
   Distanz-Teil aus `createWheelHandler` in `zoomToDistance(newDist)` herausziehen und von beiden nutzen.
   Keine Verschiebung durch Zwei-Finger-Parallelbewegung, keine Drehung durch Verdrehen.
4. **Pan für Touch abschalten, ohne die Maus anzufassen:** `controls.touches = { ONE: null, TWO: null }`
   (die Typen und das Verhalten bei der Umsetzung gegen `@types/three` prüfen). `enablePan = false` wäre
   falsch, es nähme auch das Rechtsklick-Verschieben am Desktop weg.
5. **Mapbox-Modus** (`showMapboxRef.current`): die neuen Handler kehren wie die Maus-Handler früh zurück,
   Mapbox bedient dort seine eigene Touch-Geste. **Nicht getestet**, in den Abnahmetest aufnehmen
   (Zoom über den Umschaltpunkt, Zurück-Zoomen).
6. Antippen bleibt der synthetische `click` des Browsers (Site-Auswahl). Nach Pinch/Drehen darf kein
   ungewollter Klick feuern, im Test prüfen.

**Schutz für Desktop** (die Auflage des Owners):
- Zuerst ein Charakterisierungstest, der die Rotation aus festen Eingaben (Kamerapose, Dragvektor) als
  Quaternion festschreibt. Läuft vor und nach dem Herausziehen von `rotateByDrag`, Ergebnis muss
  bit-identisch sein.
- Browser-Regression mit demselben Messaufbau wie oben (`__DEMO.getCameraState()`): Desktop-Maus-Drag von
  168 px muss weiterhin lng 10 → −14,77 und lat 29,83 liefern, Mausrad-Zoom, Doppelklick-Zoom und
  Rechtsklick-Pan unverändert.
- Gerätematrix: Handy (Touch), Desktop (Maus), Hybrid-Laptop mit Touchscreen (beide Eingaben, getrennt nach
  `pointerType`), iOS Safari (Pointer Events und `touch-action: none` sind dort unterstützt, trotzdem
  Realgerät prüfen: nicht getestet).

**Abnahmekriterien:** 1 Finger zieht den Globus mit dem Finger mit (Punkt unter dem Finger bleibt unter dem
Finger); Pinch zoomt in beide Richtungen innerhalb der Grenzen des Mausrads; Zwei-Finger-Parallelzug ändert
nichts; Ziel (`controls.target`) bleibt (0,0,0); kein Seiten-Scroll; Desktop-Zahlen unverändert.

Nicht Teil dieses Vorschlags: Hover-Tooltips auf Touch, Handy-Layout (HUD-Panels verdecken große Teile des
Canvas und fangen dort die Berührungen ab; das gehört ins Layout-Projekt).

---

## Nebenbefunde

- Im Windows-Temp-Ordner des Owners (`%LOCALAPPDATA%\Temp\gettext.py`, 420 Byte, angelegt 2026-09-29) liegt ein
  Helfer, der eine Seite abruft und das HTML entfernt. Wegen des Namens überdeckt er die Standardbibliothek
  `gettext`: jedes Python-Skript, das aus diesem Ordner startet und `argparse` importiert, versucht beim Import
  eine URL abzurufen und bricht ab. Harmlos im Inhalt (User-Agent „AncientMapRemediation/1.0"), aber falsch
  benannt. Nicht angefasst, Umbenennen empfohlen.
- Der Docstring in `pipeline/lyra/significance_scorer.py:5-6` ist falsch (siehe Abschnitt 2).
- `hooks/globe/useGlobeEvents.ts` ist toter Code (siehe Abschnitt 4).

## Anhang A: zurückgezogene Stories, die Umami gesehen hat (39, davon 29 mit externem Referrer; 17.09.–01.10.)

Stories mit `significance = 1`, Kategorie in Klammern, die Zahl vorn ist die Story-ID.
`unverified` = Verifier-Reject, die übrigen Kategorien kommen vom Scorer. Die Liste enthält alle 39; die
Trennung nach externem Referrer liegt nur in meiner Auswertung, nicht in dieser Liste.

4887 Artificial cranial deformation practice in Pacific Northwest tribes (unverified) · 4889 Global
distribution maps show suppression of elongated skull data (unverified) · 5143 Alexander the Great's Aerial
Encounters… (unverified) · 5342 Templar silver head relic… (general) · 6054 Lost footage from Shaw
Expedition… (excavation) · 6214 Pioneer probes… (general) · 6270 Pre-Dynastic Vases Found in 15,000-Year-Old
Burials (unverified) · 6346 Coordinated destruction in 1798 removed 5 pyramid courses (unverified) · 6755
Hudson Bay ice sheet… (general) · 6874 T-clamp construction technique… Osireion (unverified) · 6937
Mysterious 40m Metallic Object… Hawara (unverified) · 7044 Critique of Old Norse translation biases (theory)
· 7104 Clovis First paradigm… (unverified) · 7115 Texcotzingo site overview… (unverified) · 7118 Rock-cut cave
with carved seat… (unverified) · 7120 Temple of the Sun with Teotihuacan-style Tlaloc carvings (unverified)
· 7187 Nazi swastika dated 1942 found near shaft entrance… (unverified) · 7253 Rockford tablet… (unverified)
· 7260 Geopolymer composition… Atzlan artifacts (unverified) · 7278 Review of Land of Chem hypothesis…
(unverified) · 7284 Lightning strike hypothesis… (unverified) · 7411 Comparison of creation myths… (general)
· 7412 Michael Davis's lidar database… Carolina Bays (unverified) · 7458 Pittsburgh lawyer discovers cipher…
(unverified) · 7462 Henry Clay Frick's esoteric obsessions… (unverified) · 7463 Frick Park Trustees Map…
(unverified) · 7597 Current Egyptian excavation details… Amenemhat III (unverified) · 7645 Excarnation ritual
in Mesoamerica… (unverified) · 7662 Temple of the Feathered Serpent burned and hidden… (unverified) · 7728
Unclassified Lee Penny stone… (unverified) · 7796 54 granite columns at Baalbek… (unverified) · 7881 Azores
microcontinent proposed as Atlantis… (unverified) · 7890 Ayanis Kalesi altar in Van, Turkey… (unverified) ·
7940 Solon's Egyptian travels and Sais… (unverified) · 7959 Northwest excavation area reveals Building H…
(unverified) · 7999 Genetic debate on Denisovan and Neanderthal DNA… (unverified) · 8050 LaCroix creates Lost
Civilizations Database… (unverified) · 8076 Giant skeletons reported at multiple Adena culture mounds
(unverified) · 8468 10,000 BC Kilisik androgynous idol parallels Karahan Tepe… (unverified)

## Anhang B: Wie die Befunde reproduziert wurden

- Befund 1: Playwright (Python), Chromium 1280×900, `service_workers="block"`, Umami/Pulse-Aufrufe
  abgebrochen; alle Karten einzeln auf `/articles.html` geladen und angeklickt, danach `location.hash` und
  Vorhandensein von `.articles-reader`. Die drei Fehlstellen decken sich mit der Menge
  `{Journale mit Nicht-ASCII-Slug}`, berechnet aus `/api/news/articles?limit=50` und `pipeline.utils.slugs.slugify`.
- Befund 2: `curl -I`, `psql` (nur SELECT) in `ancient_nerds_db`, Umami-Datenbank (`website_event`, nur SELECT),
  `scripts/gsc_report.py inspect` und eine Search-Console-Abfrage `searchAnalytics/query` (Dimension `page`,
  Filter `/news-archive/`, 2026-09-02 bis 2026-09-29), Abgleich der Story-IDs gegen `news_items`.
- Befund 3: `psql`-Export der Story- und Journaltexte, Zeichenscan per `unicodedata.name`, Lyra-Log des
  Summarizer-Laufs vom 2026-09-17 (`ancient_nerds_lyra.log`, Zeilen um 13:59:43).
- Befund 4: Playwright, Chromium (headed, `--use-angle=d3d11`, wie `scripts/globe_probe/probe.py`), Pixel 7
  (412×915, DPR 2,625, `has_touch`), `globe.html?demo=1`, Pulse und Mapbox blockiert. Gesten über CDP
  `Input.dispatchTouchEvent`, Zustand über `window.__DEMO.getCameraState()`. Die Skripte lagen nur
  temporär außerhalb des Repos (`%LOCALAPPDATA%\Temp\an_diag\`); bei Bedarf als `scripts/globe_probe`-
  Unterbefehl übernehmen.
