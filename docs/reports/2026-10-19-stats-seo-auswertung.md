# SEO-Auswertung ancientnerds.com auf Basis von stats.ancientnerds.com, 2026-10-19

**Stand:** 19.10.2026, Auswertung zwischen etwa 17:15 und 19:30 UTC. Alles nur lesend: keine Sitemap-Einreichung, kein
IndexNow, keine GSC- oder Bing-Schreibaktion, keine DB-Writes, kein Push, keine Code-Änderung. Lokal liegt keine
Besucher-IP; Crawler-IPs wurden nur auf dem VPS gegen die veröffentlichten Listen geprüft und nur aggregiert abgelegt.

**Grundlage:** acht Teilberichte unter `output/seo-audit-2026-10-19/` (`gsc.md`, `index.md`, `crawl.md`, `traffic.md`,
`cwv.md`, `tech.md`, `bing_geo.md`, `roadmap.md`), jeder mit eigenem adversarischen Abschnitt „## Prüfung“, dazu die
Vollständigkeitskritik `critic.md`. In diesen Bericht gehen nur Befunde ein, die die Prüfung bestätigt oder korrigiert
hat, korrigierte in korrigierter Form. Widerlegte Befunde fehlen; was sich nicht belegen ließ, steht höchstens als offene
Frage da.

**Baseline:** SEO+GEO-Audit vom 08.10. (`docs/reports/2026-10-08-seo-geo-audit.md`, Fahrplan §6, Owner-Entscheidungen §8,
KPI-Rahmen §9.3) und die Nachmessung vom 11.10. (GSC-Stand 08.10.: 28 T. 1.141 Klicks / 80.578 Impr. / Pos. 8,7).

Pfadangaben ohne Präfix sind relativ zu `output/seo-audit-2026-10-19/`.

---

## 1 Kurzfazit

Google bringt deutlich mehr: In den 28 Tagen bis 17.10. stehen 1.489 Klicks und 101.680 Impressionen (Pos. 8,49), also
+30 % Klicks und +26 % Impressionen gegenüber der Nachmessung vom 11.10.; die Non-Brand-Klicks stiegen gegenüber dem
08.10. von ~942 auf 1.459 (+55 %). Getragen wird das von Stories (61 % der Klicks) und von schon indexierten Seiten:
Google arbeitet seit 12.10. den Story-Rückstau vom September ab (347 URLs mit erster Impression am 12.–17.10.), Länder-Hubs
sind zu 31 von 34 indexiert, und der verifizierte Googlebot crawlt +50 % (586 gegen 390 Requests pro Tag). Seit dem 08.10.
stagnieren die Klicks aber auf Tagesniveau (ohne den Langschädel-Cluster 55,6 gegen 55,8 Klicks pro Tag), und die CTR der
Ortsseiten fiel in der letzten Woche auf gleicher Position deutlich. Der größte Hebel ist unverändert der Soft-404-Bestand
der Ortsseiten: In der Zufallsstichprobe stehen 31,5 % (22–43 %) auf Soft 404, darunter 59 der 64 Kopf-Orte, alle zuletzt
im August vor dem Robots-Fix b4690a3 gecrawlt. Google holt diese URLs gezielt nicht ab (0 von 96 gegen 27,7 % Grundrate),
obwohl sie heute inhaltlich wie indexierte Seiten aussehen. Den Neucrawl kann nur der Owner in der GSC-Oberfläche
anstoßen; ob das wirkt, ist nicht gemessen. Daneben stehen: Story-Leser gehen kaum auf Ortsseiten weiter (0 von 170
Story-Landern mit Orts-Chip, und 52 % der Story-Lander kommen auf Stories ohne Ort), die Handy-Origin besteht die Core Web
Vitals knapp nicht (LCP 2.575 ms, INP 273 ms), und KI-Referrals haben sich seit 08./09.10. etwa halbiert.

---

## 2 Kennzahlen

| Kennzahl | Wert | Fenster | Quelle | Vergleich Baseline |
|---|---|---|---|---|
| Google Web: Klicks / Impr. / CTR / Pos. | 1.489 / 101.680 / 1,46 % / 8,49 | 28 T. 20.09.–17.10. | GSC-API `raw/gsc/totals.json` = Dashboard `raw/dashboard/search.json` | 11.10.: 1.141 / 80.578 / Pos. 8,7 → +30,5 % / +26,2 %. 08.10.: 973 / 70.984 (heute neu abgefragt 1.030, GSC hat nachkorrigiert) |
| Google Web 7 T. | 466 / 32.154 / 1,45 % / 8,68 | 11.–17.10. | `raw/gsc/totals.json` | Vorwoche 452 / 25.970 / 1,74 % → Klicks +3 %, Impr. +24 % |
| Non-Brand-Klicks (KPI §9.3) | 1.459 | 28 T. bis 17.10. | `totals.json` − `raw/gsc/brand_total_28.json` (Regex `(?i)ancient[ -]?nerd`) | ~942 → +55 % |
| Brand | 43 Impr. / 30 Klicks | 28 T. bis 17.10. | `raw/gsc/brand_query_28.json` | 41 / 31 → flach |
| Story-Anteil an Klicks | 61,2 % (914, CTR 1,75 %) | 28 T. bis 17.10. | `scratch/gsc/types.txt` | 54,6 % |
| CTR Ortsseiten | 0,89 % (28 T.); 0,80 % (12.–17.10., ohne Shillourokambos) | s. links | `types.txt`, `site_detail_weeks.txt` | 0,98 % (08.10.); Vorwoche 1,19 % |
| Shillourokambos-Schwall | 3.629 Impr. / 0 Klicks | 28 T. | `gsc.md` gsc-3 | neu; ohne ihn Property 97.859 Impr. / CTR 1,52 % |
| Ortsseiten Soft 404 (Zufallsstichprobe KPI 73) | 47 indexiert / 23 Soft 404 / 2 Discovered / 1 unknown (31,5 %, Wilson 22,0–42,9 %) | URL Inspection 19.10. | `index/raw/inspect_out.json`, `analysis.json` | 08.10.: 47 / 23 / 3, jede URL im selben Zustand |
| Soft-404-Ortsseiten von Google geholt | 0 von 96 (Grundrate Sitemap-Ortsseiten 1.359/4.900 = 27,7 %) | nginx 04.10. 22:08 – 19.10. 18:41 UTC | `critic/raw/google_per_url.json` | – |
| Worklist 64 Kopf-Orte | 59 Soft 404, 2 indexiert (Sacsayhuamán, Kutaisi), 2 unknown, 1 Discovered; 62 nicht indexiert | Inspection 19.10. | `index/.../analysis.json`, `raw/roadmap/inspect/worklist_inspect.json` | 08.10.: 64 nicht indexiert |
| Länder-Hubs indexiert | 31 von 34 (England, North Korea, Slovakia unknown) | Inspection 19.10. | `analysis.json` | 15 von 26; gleiche URLs 15/25 → 22/25 |
| Stories ab 01.09. (Baseline-Panel) indexiert | 23 von 36 | Inspection 19.10. | `analysis.json prev_recent_stories` | 2 von 36 |
| URLs mit erster Impression | 347 (12.–17.10.) | GSC 90 T. | `raw/gsc/page_date_90.json` | 08.10.: seit 17.09. keine neue Story |
| Neue Stories (ab 05.10., sig ≥ 2) von Googlebot geholt | 16 von 172 (Median 15 h); Bingbot 152/172 | 05.–19.10. | `raw/crawl/agg.json fresh_stories` | 3 von 103 |
| Neue Paper indexiert | 0 von 10 seit 01.10. | Inspection 19.10. | `index/raw/inspect_out.json` | 0 von 5 |
| Googlebot (IP-verifiziert) Requests/Tag | 585,9 (Inhalte mit 200: 305,4) | 10.–18.10. | `raw/crawl/agg.json` | 390 bzw. 161 → +50 % |
| Googlebot-Anteil 410 / Assets / Legacy-301 / 5xx | 13,8 % / 19,0 % / 6,3 % (alle 3xx 7,1 %) / 0 | 10.–18.10. | `raw/crawl/agg.json` | 20,9 % / 24,9 % / ~7 % |
| Googlebot-Story-Crawl auf 410 | 35,5 % (631/1.775) | 10.–18.10. | `raw/crawl/agg.json` | 50 % |
| Bing Klicks / Impr. / CTR | 98 / 3.964 / 2,47 % (≈15,7 % der Google-Klicks im Fenster) | 09.–17.10. | `raw/bing/GetRankAndTrafficStats.json` | Baseline: keine Bing-Daten |
| Bing InIndex / InLinks | 7.875 / 4 (LinkCounts leer) | Stand 17.10. | `raw/bing/GetCrawlStats.json`, `GetLinkCounts_p0.json` | unbekannt |
| Umami Google-Sitzungen : GSC-Klicks | 1,116 (1,080 vor / 1,162 nach 09.10.) | 28 T. bis 17.10. | `search.json` + `traffic/raw/segments.json` | 1,14 → kein Messverlust |
| Andere Suchmaschinen | 30,0 Sitzungen/Tag, 27,7 % der Suchankünfte | 10.–18.10. | `traffic/raw/segments.json` | ~17/Tag, 20 % |
| KI-Assistenten-Sitzungen | 2,8/Tag (2,1 human) | 10.–18.10. | `traffic/raw/segments.json`, `raw/dashboard/daily.json` | 18.09.–08.10.: 5,4 Sitzungen / 3,3 human pro Tag (gleiche Definition) → etwa halbiert |
| Story-Suchlander → Ortsseite | 0 von 170 (Stories mit Orts-Chip); 285 von 547 Story-Landern ohne Ort | 10.–18.10. | `traffic/raw/crosstab.json` | 1/657 |
| Suchlander mit zweiter URL | Story 7,1 % (39/547), Ortsseite 7,4 % (15/204) | 10.–18.10. | `traffic/raw/crosstab.json` | 4,9 % / 3,1 % (vor der Filteränderung, alle Sitzungen) |
| Mobilanteil Suche | GSC 49,4 % der Klicks | 10.–17.10. | GSC Device-Dimension (traffic-Prüfung) | 50,4 % → unverändert |
| CrUX Handy-Origin LCP / INP / CLS / TTFB p75 | 2.575 ms / 273 ms / 0,02 / 1.005 ms | 28 T. 20.09.–17.10. | `raw/cwv/crux_origin_PHONE.json` | 3.020 / 436 / 0,03 / 1.302 |
| CrUX Desktop-Origin LCP / INP / CLS | 1.727 ms / 95 ms / 0,01 (bestanden) | dto. | `raw/cwv/crux_origin_DESKTOP.json` | 1.706 / 101 / 0,03 |
| CrUX `/globe.html` INP (alle Geräte) | 993 ms | dto. | `raw/cwv/crux_url_globe_ALL.json` | unverändert |
| CrUX `/` LCP / TTFB | 3.510 ms / 2.038 ms | dto. | `raw/cwv/crux_url_home_ALL.json` | LCP 3.611 ms |
| Interne Suche | 192 Suchen / 69 Sessions, 48 ohne Treffer (25 %) | seit 17.09. | Dashboard `content.searches`, `critic/raw/` | nicht ausgewertet |
| Wikidata-QID im Orts-JSON-LD | 27/30 (Stichprobe); 269/298 sameAs+identifier | 19.10. | `raw/geo/qid_sample.json`, `raw/tech/sample300_stats.txt` | 0 |
| Story-Reverify-Abdeckung | 122 von 2.990 öffentlichen Stories (≈4 %), letzter Lauf 17.10. 21:10 UTC | 09.–19.10. | `raw/roadmap/story_reverify/journal.jsonl`, DB | 0 |

---

## 3 Befunde nach Dimension

Schwere wie in den Teilberichten, nach der Prüfung angepasst.

### 3.1 Indexierung

1. **Kritisch: Der Soft-404-Bestand der Ortsseiten aus dem August heilt nicht, und Google lässt ihn gezielt liegen**
   (gsc-1, index-1, tech-1, roadmap-1, critic L1).
   - Stichprobe 73: unverändert 23 Soft 404 (31,5 %, 22–43 %), jede URL im selben Zustand wie am 08.10. Von 97 heute
     inspizierten Soft-404-Ortsseiten wurde seit 09.10. eine neu gecrawlt (Sacsayhuamán, 15.10., jetzt indexiert); dazu
     Kutaisi aus der Worklist (vorher unknown, Crawl 14.10., indexiert). Worklist: 59 von 60 Soft-404-Orten stehen weiter
     so, `lastCrawlTime` maximal 15.08. (`index/.../analysis.json`, `raw/roadmap/inspect/worklist_inspect.json`).
   - Google holt diese URLs gezielt nicht: 0 von 96 Soft-404-URLs unter allen verifizierten Google-UAs, gegen 30 von 65
     indexierten der Stichprobe und 27,7 % Grundrate (p ≈ 3·10⁻¹⁴; nginx 04.10.–19.10., `critic/raw/google_per_url.json`).
     Alle 96 stehen in `sitemap-sites.xml` mit `lastmod` 30.09.–18.10. nach dem letzten Crawl, die Sitemap wurde am
     14.–19.10. geladen. Google ignoriert das `lastmod` dieser URLs.
   - Die Urteile stammen aus der Robots-Panne: 94 der 96 wurden zuletzt vor dem Fix b4690a3 gecrawlt (16.08. 13:27 UTC,
     davor war `/api/sites/` für den Renderer gesperrt), die übrigen zwei am 31.08. Von den indexierten nur 6 von 65.
   - Inhaltlich hält die Seiten heute nichts zurück: Live-GET ohne JS, alle 200, Median 156 gegen 195 Wörter, gleiche
     HTML-Größe, Description-Länge, JSON-LD-Blöcke, kein noindex (`critic/raw/content_compare.json`).
   - Nicht gemessen: ob die Validierung vom 05.09. lief oder nach dem 11.10. neu gestartet wurde, ob Indexierungsanträge
     gestellt wurden, und ob sie wirken würden. Richtig ist „ohne messbare Wirkung oder nicht gestartet“.
   - „0 Impressionen der Soft-404-Orte“ ist fast tautologisch (nicht im Index). 280 der 1.000 Export-URLs sind
     Legacy-URLs, die heute 301 liefern; die Zufallsstichprobe 0/30 (Crawls 11.–28.08.) stammt aus den 1.000
     exportierten Zeilen, nicht aus allen 1.877.
2. **Mittel: Oktober-Paper unindexiert** (index-3, tech-2, crawl-1). 0 von 10 Papern seit 01.10. indexiert (5 unknown,
   5 Discovered); das Hard-Stone-Paper ist „Crawled – currently not indexed“ (Crawl 16.10.). Google lud
   `sitemap-research.xml` am 14.10. mit allen 42 URLs, trotzdem sind 3 von 4 geprüften neuen Papern „unknown to Google“.
   Ob Entdeckung oder Crawl-Nachfrage der Engpass ist, ist offen. Ältere Paper sind sichtbar: 27 Paper und 18 Journals
   mit Impressionen in 28 T. (`page_28.json`), mit demselben Template. Journals: 1 von 4 inspizierten indexiert.
3. **Mittel: England-Hub weiter nicht im Index** (index-4). 31 von 34 Hubs indexiert, neu u. a. China, Russia, Germany,
   Cyprus, Laos, Guatemala, Romania. England, North Korea und Slovakia stehen auf unknown; North Korea wurde am 07.10.
   gecrawlt und steht trotzdem so. Beide kleinen Hubs haben ~28 KB HTML, die Größen-Hypothese für England ist damit
   geschwächt.
4. **Info: Story-Entdeckung erholt sich** (index-2, gsc-6, critic L2). 23 der 36 Baseline-Stories ab 01.09. sind
   indexiert (08.10.: 2). Von 115 Stories mit erster Impression ab 06.10. holte Googlebot 114, davon 97 am 12.–14.10.;
   danach im Median 1 Tag bis zur ersten Impression. Das ist ein Nachholcrawl des Rückstaus vom 11.09.–04.10. Frische
   Stories ab 05.10. holt Googlebot weiter selten (16 von 172). Der Auslöser des Crawl-Schubs am 12.10. (349 → 641
   Abrufe/Tag) ist offen.
5. **Niedrig: Legacy-301 werden verarbeitet** (index-5, gsc-8). 5 von 6 inspizierten Legacy-URLs stehen auf redirect;
   der Legacy-Anteil an den Impressionen fiel auf 0,88 % (7 T. bis 17.10.), das E6-Kriterium (< 1 %) ist erstmals
   erfüllt.
6. **Info: Sitemaps, Canonicals und Story-Filter sauber** (index-6, index-7). 0 Fehler/Warnungen, 12.327 Web-URLs,
   Google-Canonical = User-Canonical bei 264 von 264, 0 Stories mit sig < 2 in der Sitemap, 98/98 Legacy-Ziele 200. Das
   Orts-`lastmod` ist datengetrieben (Remediation-Wellen) und folgt schon der Regel „nur bei inhaltlicher Änderung“. Drei
   statische Seiten (`search.html`, `theo.html`, `library.html`) haben zwei H1.

### 3.2 Google-Leistung (GSC)

1. **Hoch: Klicks stagnieren seit 08.10., Impressionen steigen** (gsc-2, traffic-5). Klicks 08.–11.10.: 83, 84, 76, 85;
   Impressionen 12.–17.10.: 3.975–5.394 pro Tag. Von 149 Klicks des Langschädel-Clusters fallen 146 ab 08.10. an; ohne
   ihn liegen beide Wochen bei 55,6 bzw. 55,8 Klicks pro Tag. KW41 → KW42 Umami −4 %, GSC −9 % (innerhalb des Rauschens).
2. **Mittel: Ortsseiten-CTR fiel in der Woche 12.–17.10. auf gleicher Position** (gsc-5, traffic-6, critic L5). CTR
   1,04 → 1,19 → 0,80 % (ohne Shillourokambos), Pos. 9,45 → 9,69 → 10,14. Im Band Pos. 4–10 halbiert sich die CTR
   (1,32 → 0,71 %) bei gleichem Impressionsanteil (75 %); mit den Vorwochen-CTRs wären 124 statt 78 Klicks zu erwarten
   (p ≈ 6·10⁻⁶). Der Rückgang ist breit (Seiten mit ≥ 1 Klick 100 → 72), Stories kaum betroffen, Titel und Description
   der Ortsseiten haben sich im Code nicht geändert. Ein mehrwöchiger Trend ist das nicht (die Vorwoche lag höher); die
   Ursache auf gleicher Position (AI Overviews, Query-Mix) ist offen.
3. **Hoch (Hypothese zum Hebel): Snippet-Chancen ungenutzt** (gsc-4). Ohne Shillourokambos 59 Seiten mit 19.084
   Impressionen und 77 Klicks auf Seite 1 mit unterdurchschnittlicher CTR; W9 ist nicht umgesetzt. Dass die heutigen
   Snippets die CTR senken, ist eine Hypothese, kein Messergebnis.
4. **Mittel: Shillourokambos-Schwall** (gsc-3). 3.629 Impressionen, 0 Klicks; er verzerrt alle Impressions- und
   CTR-Summen. Ob er automatisiert ist, ist nicht belegt.
5. **Mittel: Keine Zusatzflächen** (gsc-11). Brand-Nachfrage flach (43 / 30), News-Tab 4 Impressionen in 90 T., keine
   Rich-, Video- oder Discover-Auftritte; seit dem VideoObject-Deploy liegen erst 8 finale Tage vor.
6. **Niedrig** (gsc-7, gsc-9, gsc-10, gsc-12): Die 15 neu sichtbaren Paper sind fast nur Off-Topic-Paper (2 Klicks,
   beide Watchers/Nephilim). Headline-Korrekturen ändern Story-Slugs (17 geklickte URLs jetzt 301; Anlass nur für 7278,
   4889, 7104 belegt). Klicks auf heute tote URLs: 25 von 1.493 (1,7 %), seit 10.10. nur 5, alle 410-Stories mit
   significance 1 (gewollt); 7907 existiert nicht mehr in `news_items`, also keine Aktion. Baalbek rankt mit mehreren URLs
   (7 Klicks); eine Kannibalisierung ist damit nicht belegt.

### 3.3 Crawl

1. **Hoch: Googlebot holt neue Stories und Paper kaum, obwohl er mehr crawlt** (crawl-1). 16 von 172 neuen Stories,
   0 von 10 Papern vom 05.–07.10. (Bingbot 152/172, Median 0,4 h). Die Ursache ist offen (s. 3.1.2).
2. **Mittel: 410-Altlast bindet ein Drittel des Story-Crawls** (crawl-2, tech-8). 35,5 % des Googlebot-Story-Crawls
   treffen 410 (Baseline 50 %). Die 410 auf sig < 2 und retirierten Orten sind gewollt (Owner 09.10.); der sinkende
   Anteil geht auch auf die Reinstate-Welle 6f1b923 vom 11.10. zurück.
3. **Mittel: Baiduspider ×8,6 ohne Nutzen** (crawl-6). 149 → 1.288,7 Requests/Tag (05.–09.10. gegen 10.–18.10.),
   0 Referrals; 6.201 `/data/`-Bilder und 2.800 `/api/`-Abrufe im Fenster. Nur `/api/pulse` ist robots-gesperrt.
4. **Niedrig: Last ohne Referral-Nutzen** (crawl-7, crawl-3). PetalBot 1.394,7/Tag (26,7 % Legacy-301), Amazonbot
   1.148/Tag, je 0 Referrals. Ob robots-Begrenzung wirkt, ist nicht belegt (AhrefsBot holt trotz Sperre Bilder).
5. **Niedrig: KI-Crawler** (crawl-8, crawl-5, bing_geo-7). OAI-SearchBot seit 13.10. stabil bei 68–129/Tag (kein
   anhaltendes Sinken); ChatGPT-User ohne `/` ~68/Tag. ClaudeBot holte am 12.10. 12.196 Requests (unverifizierbar, keine
   IP-Liste); erster Inhalts-Crawl seit mindestens 24.09., nicht der erste überhaupt. GPTBot und ClaudeBot holen den
   Sitemap-Index plus die 6 in robots.txt genannten Teile; die Kausalität zum robots-Commit 0ba5d4b ist nur zeitlich.
6. **Niedrig: Impostoren** (crawl-9). 724 Fake-Googlebot-Requests von 9 IPs (266 Secret-Scans) bis 19.10. 17:30 UTC.
7. **Info: Googlebot-Crawl technisch gesund** (crawl-4). +50 % Volumen, 0 × 5xx an Googlebot und Bingbot, ≥ 99 % aus
   192.178.*. Assets 19,0 % (Baseline 24,9 %); ob Bundle-Churn aufgehört hat, ist nicht gezeigt.

### 3.4 Besucher und Verhalten

1. **Hoch: Story-Leser gehen nicht auf Ortsseiten weiter, weil die Hälfte der Stories keinen Ort hat** (traffic-1).
   Von 547 Story-Suchlandern (10.–18.10.) kamen 170 auf eine Story mit Orts-Chip (0 gingen weiter), 92 auf eine mit nur
   Globus-Chip, 285 (52 %) auf eine Story ohne Ort. Die fehlende Ortszuordnung ist der größere Hebel als Verlinkung im
   Fließtext.
2. **Mittel: Klumpenrisiko Langschädel** (traffic-7). 27,9 % der Story-Suchlander (Umami 128/458), 22 % der
   Story-Klicks (GSC 79/355). Keine der drei Stories hat einen Ort; Coffin Rock / Chinook als Ortsseite verstieße gegen
   die Regel Amerika ≤ 1500 AD, es bleiben Links auf verwandte Stories.
3. **Mittel: KI-Referrals etwa halbiert** (traffic-4, bing_geo-2, roadmap-6, critic W4/W5). 5,43 → 2,78 Sitzungen/Tag ab
   08./09.10.; Definition `from_ai` seit 25.09. unverändert, nginx bestätigt, dass Umami nichts verliert. Die Zahlen sind
   klein (25 gegen ~49 erwartet), die Ursache ist nicht gemessen. „ChatGPT-User liest +65 %“ kommt aus einem
   Logquellenwechsel und ist im selben Log flach, also nicht belegt.
4. **Mittel: YouTube, Discord, Social bringen ~0** (traffic-10). Social 4 Sitzungen in 31 T., YouTube 0, Discord 1,
   Creators-Outbound 10 Klicks seit 09.10. 06:42 UTC; 0 von 3.370 Videobeschreibungen nennen ancientnerds.com.
5. **Niedrig/Info** (traffic-11, -12, -13, -14): Nicht-Google-Suche wächst schneller (27,7 % gegen 20 %); Suche ist zu
   ~50 % mobil (unverändert); Umami verliert keine Google-Ankünfte (Verhältnis 1,08–1,16 stabil); Startseite und Hubs
   verteilen gut, 83 % der Story-Lander scrollen, 54 % bis ≥ 75 %, 10,1 % spielen das Video.
6. **Interne Suche** (critic L3). 192 Suchen seit 17.09., 25 % ohne Treffer. Muster: Tippfehler („great zimbawe“),
   natürliche Formulierungen zu Kopf-Orten („valley of kings“ 0 Treffer, „valley of the kings“ Platz 1), nicht-lateinische
   Schrift (Telugu, Arabisch, Persisch), Story-Themen („elongated skulls“ findet nichts). Kleine Fallzahl, Signal auf der
   Seite, kein Ranking-Faktor.
7. **Globus und Konten** (critic L4). 86 % der Aufrufe erreichen den fertigen Globus, mobil 77 %; Median 4,3 s bis
   bereit; 176 Aufrufe vom Handy-Gate angehalten. 7 Mitglieder (2 Founder): Suchverkehr führt nicht zu Anmeldungen.

### 3.5 Core Web Vitals

1. **Hoch: Handy-Origin besteht nicht** (cwv-1). LCP 2.575 ms (74,2 % good statt 75 %), INP 273 ms (37 % über der
   Grenze). Gemessen schlecht ist im Feld nur `/` (LCP 3.510 ms, davon TTFB 2.038 ms); Orts- und Paperseiten haben keine
   CrUX-URL-Daten und gute RUM-LCP (Ortsseite mobil 1.838 ms, n = 106).
2. **Hoch: Globus-INP 993 ms** (cwv-2). CrUX alle Geräte, 35,9 % poor. Dass er den Handy-INP der Origin treibt, ist
   nicht belegt (kein CrUX-Handy-Wert, RUM Desktop 864 ms gegen mobil 428 ms).
3. **Hoch (nur Lab): Paper laden große, nicht skalierte JPEGs ohne lazy und srcset** (cwv-3). PSI Squatter Man mobil
   70 / LCP 14,6 s / 4,71 MB; Feld n = 7.
4. **Mittel** (cwv-4 bis cwv-10): 480-px-Thumbnails sparen Bytes (Göbekli 8.083 → 1.081 KB eigene Galeriebilder),
   nicht Lab-LCP; der Foto-Tab lädt Commons-Bilder (~2,9 MB mobil, meist 960 px) alle auf einmal; Hub-Karten verweisen auf
   Commons-Originale bis 6 MB; das LCP-Element der Ortsseite entsteht erst nach dem Client-Render (Popup-Swap);
   render-blocking CSS kostet LCP nur auf Orts-, Hub- und Journalseiten (0,45–0,75 s Lab). Der 1600-px-Hero (≈412 px
   angezeigt) und das Startseiten-Video sind Owner-Entscheidungen; das Video startet nach `load` und treibt die LCP nicht.
5. **Info: Server schnell, Feld-TTFB hoch** (cwv-13, tech-12). VPS-Loopback Median 0,03–0,19 s je Template
   (`/research/` 0,64 s), CrUX-RTT p75 Phone 314 ms; die Ursache der 2,0 s TTFB auf `/` ist nicht gemessen.

### 3.6 Technik und On-Page

1. **Hoch: Paper und Journals sind Link-Sackgassen** (tech-2, roadmap-9). 0 Links auf Ort, Story oder Paper auf 6 von 6
   Paper-Proben und 4 Journals; Ortsseiten mit Paper-Link 0/298, Stories 0/118. Dass das die Indexierung bremst, ist
   nicht belegt.
2. **Mittel: Meta-Descriptions hart abgeschnitten** (tech-4). 270/298 Orts-Descriptions haben genau 300 Zeichen,
   265/298 enden ohne Satzende, bis zu 215 mitten im Wort (`ancient-nerds-map/src/seo/meta.ts:179 cut()`).
3. **Mittel: Titel** (tech-5). Orte mit DB-Taxonomie-Suffix (z. B. „Pompeii · Italy · City/town/settlement“), 118/298
   über 60 Zeichen; Stories Median 85 (103/118 über 70); Journals 107–151.
4. **Mittel: Neun dünne App-Shells indexiert** (tech-6). Konkurrenz zu SSR-Hubs klein (`articles.html` 51 Impr. gegen
   `/articles/` 26); `articles.html` neben `/articles/` ist eine Produktentscheidung.
5. **Niedrig** (tech-3, tech-7, tech-9, tech-10, tech-11, tech-13, tech-14): VideoObject `uploadDate` ohne Zeitzone
   (GSC: Warnung, Verdict PASS; ~2.861 Story-Seiten); 989 Hero-Dateinamen mit Leerzeichen, 67/298 Seiten mit rohem
   Leerzeichen im `<img src>` (Browser kodieren selbst, Schaden nicht gemessen), 1.092 von 4.900 Orten ohne Hero;
   Spekulations-Tag als Rohwort in der H1 (382 öffentliche Stories); Paper und Startseite ohne `<main>`; HEAD 405,
   kein HSTS, kein ETag; die stats-Subdomain sendet schon `X-Robots-Tag: noindex, nofollow` (ein `Disallow: /` wäre
   kontraproduktiv); Schema-Lücken unterhalb der Fehlerschwelle (WebSite-Schema fehlt).
6. **Positiv** (tech-15): Weiterleitungen alle 1 Hop, Canonicals sauber, 0 UA-Abweichungen (kein Cloaking), 0 JSON-LD-
   Fehler, Wikidata-`sameAs` auf 90 % der Ortsseiten. `llms.txt` nennt weiter „7,300“ URLs bei 7.428 in den Sitemaps.

### 3.7 Bing und GEO

1. **Hoch: Off-Page-Signale fehlen fast vollständig** (bing_geo-1). 0 Bing-Backlinks, 0 enwiki-Links, kein
   Wikidata-Item der Marke, 0 Captures in Common Crawl CC-MAIN-2026-30 und -39 (-34 nicht gemessen).
2. **Mittel: Seite 1 nur bei Nischenfragen und nur mit Stories** (bing_geo-3). Bei 31 gültigen US-SERPs (19.10.
   17:31–17:33 UTC): Desktop 1/20, mobil 2/20 (lathe Pos. 4, Louis de Cordier mobil Pos. 6); AI Overview Desktop 15/20
   (zitiert uns 1 von 7 geprüften), mobil 20/20 (2 von 11). 9 von 40 SERPs gestört, 16 AIOs nur als Token.
3. **Niedrig: `llms.txt` bewirbt `/api/v1/*`, das robots.txt sperrt; 0 Abrufe durch erfasste Crawler** seit 09.10.
   22:15 UTC (bing_geo-4).
4. **Info: Bing wächst** (bing_geo-6). Umami-Bing-Sitzungen KW39–42: 20 / 42 / 53 / 69; Bing-CTR 2,47 % (ohne
   Positionsvergleich). Die Marke steht bei Bing auf Pos. 3–4 (ganzzahlig, Fenster unbekannt).

### 3.8 Inhalt und Datenstand

1. **Mittel: Kopf-Orte ohne Bewegung** (roadmap-5). 0 neue kuratierte Orte seit 08.10. (Bestand 5.004, jüngste Anlage
   24.04.); Göbekli Tepe `period_start` −5000, Baalbek −7000; Kolosseum, Karthago, Ephesos, Ninive, Mohenjo-daro, Chaco
   Canyon fehlen. Kopf-16: 234 Impr. / 0 Klicks in 90 T. (Baseline-Vergleich unbelegbar). „Top-100-Lücke wuchs auf 43“
   ist ein Fenstereffekt (Impressionen der Top 100 +13 % auf 4.950).
2. **Mittel: Story-Bestand kaum nachgeprüft** (roadmap-3, roadmap-4, roadmap-2). Reverify 122 von 2.990 (≈4 %), seit
   17.10. 21:10 UTC keine Welle. Vier bekannte Junk-Stories (7858, 5608, 4747, 4755) sind mit significance 2 öffentlich
   und liefern 200. 6 Reinstate-IDs vom 12.10. scheiterten (5× Reasoning-Budget, 1× MiniMax-429) und wurden nicht
   nachgeholt. Die 53 Reinstated: 45 statt ~15 Impressionen pro Tag, Klicks gleich (~1/Tag).

---

## 4 Was das Dashboard selbst falsch oder nicht misst

| # | Panel | Problem | Beleg | Vorschlag |
|---|---|---|---|---|
| D1 | overview, daily, countries | „human“ lässt CN/SG/HK-Scraper durch: 160 von 327 Direkt-Humans (10.–18.10.) sind „human“ nur über ≥ 2 URLs, 0 Interaktionen; der Direkt-Schwall ist breiter (SG, CN, US, VN, HK, MX; 97,5 % Desktop) | traffic-2, `traffic/raw/crosstab.json` | ≥ 2 URLs nur mit Interaktion (Scroll, Klick) als human werten; Direkt-Desktop ohne Scroll gesondert ausweisen |
| D2 | daily, overview | Bruchkante 09.10. (Scroll-Capture): etwa die Hälfte des Anstiegs 21 → 129 human/Tag ist Messänderung (~56/Tag), ~18/Tag Scraper, der Rest echt. Der Filter wird beim Lesen angewandt, gilt also rückwirkend; die Scroll-Daten fehlen vor 09.10. | traffic-3 | Bruchkante im Panel markieren; Wochenvergleiche über die Kante nur mit „alle Sitzungen“ |
| D3 | devices, map, overview (all) | zählen alle Sitzungen inkl. Scraper: Devices 15,4 % mobil gegen ~50 % in der Suche; countries ist human-gefiltert, aber verzerrt (CN+SG+HK 11,8 % d30, 20,5 % d7) | traffic-9 | Gerätesplit je Segment (Suche, human) zeigen |
| D4 | problems | zählt Bot-Vitals mit; die Globus-LCP-Zeile (5.228 ms roh, 1.283 Samples) ist ein Artefakt des Bot-Schwalls 15./16.10. (796 Samples bei 800×600); bereinigt 1.268 ms mobil / 1.996 ms Desktop | cwv-11, `raw/cwv/rum_globe_split.json` | Vitals nur aus human-Sitzungen, Viewport-Plausibilität |
| D5 | sources | liest nur das letzte 1 MiB von `referrals.log` (`MAX_TAIL_BYTES`), deckt damit ~5,3 Tage ab, obwohl das Log bis 17.09. reicht; 28/34-T.-Summen sind wegen `LIMIT 40` Untergrenzen | traffic-15, bing_geo-2 | Log ab `covered_from` vollständig lesen bzw. voraggregieren; Limit-Hinweis im Panel |
| D6 | crawlers | ohne Assets/Daten-Aufschlüsselung; Daten erst ab 09.10. 22:15 UTC; ClaudeBot u. a. nicht verifizierbar, das Panel trennt verifiziert/unverifiziert nicht sichtbar genug | crawl-10, crawl-5 | Typ-Spalten (Inhalt, Asset, Bild, API, 3xx/410) und Verifikationsstatus je Familie |
| D7 | journeys | `moving` zählt ≥ 2 Seitenaufrufe statt anderer URL (Reload = moving), anders als `Session.human` | roadmap-12, `pipeline/stats_analysis.py:938–944` | auf `len(urls) >= 2` umstellen |
| D8 | search | Sitemaps-API-Feld `indexed` ist immer 0; keine Indexierungs- oder Soft-404-Sicht | index | Indexstand aus einer festen Inspection-Stichprobe (Seed) wöchentlich zeigen |
| D9 | – | KPI „Story → Ortsseite“, „Weiterklick nach Sucheinstieg“, Video-Abspielquote fehlen als Panel (nur aus Rohdaten gemessen) | roadmap §5, traffic | Lander-Panel nach Seitentyp mit zweiter URL, Ziel-Typ, Video-Play |
| D10 | – | Keine Bing-Sicht im Dashboard (die Bing-Zahlen dieser Auswertung kommen aus der BWT-API) | bing_geo | BWT-Tageswerte als Zeile neben GSC |
| D11 | content.searches | Null-Treffer-Suchen werden gezählt, aber nicht als Muster gezeigt | critic L3 | Null-Treffer-Liste mit Häufigkeit |
| D12 | – | nicht messbar: Verweildauer/Pogo-Sticking, Conversion Sucheinstieg → Anmeldung (kein verbindendes Event), Discord-Klicks über die Landing (lädt kein Analytics), Founder-Besuche nicht filterbar, KI-/YouTube-Apps ohne Referrer zählen als direct | traffic, critic | Signup-Event mit Einstiegs-Segment; Founder-Ausschluss per Cookie |

---

## 5 Maßnahmenplan

Sortiert nach Hebel/Aufwand. Hebelangaben sind Einschätzungen, wo nicht anders vermerkt.

### 5a Code, autonom machbar

| # | Maßnahme | Hebel | Aufwand | Befund |
|---|---|---|---|---|
| A1 | Dashboard-Messung reparieren: human-Regel (D1), Vitals nur human (D4), Sources ohne 1-MiB-Grenze (D5), `moving` (D7); Bruchkante markieren (D2). Vor dem Review ~26.10. | hoch (alle weiteren Entscheidungen hängen an der Messung) | klein–mittel | traffic-2/3/15, cwv-11, roadmap-12 |
| A2 | Interne Verlinkung: Ortsseite ↔ Paper (Paper zitieren Orte), Paper/Journal → Orte und Stories, Journale → eigene Stories (W4-Rest). Ohne neue Designelemente nur als Links im bestehenden Text/Block; neue Blöcke sind Owner-Vorschlag | mittel (Wirkung auf Indexierung nicht belegt) | mittel | tech-2, roadmap-9 |
| A3 | Meta-Description am Satz- bzw. Wortende kürzen statt bei 300 Codepoints (`meta.ts:179`) | mittel (CTR-Hypothese) | klein | tech-4, gsc-4 |
| A4 | Interne Suche: Stoppwort-/Artikel-Toleranz („valley of kings“), Tippfehler-Toleranz, Story-Treffer, Namen in nicht-lateinischer Schrift | mittel (Onsite) | mittel | critic L3 |
| A5 | Paper-Bilder: skaliert, `loading=lazy` außer Hero, `srcset`; Hub-Karten auf Thumbnails statt Commons-Originale; Foto-Tab gestaffelt/lazy laden | mittel (Lab; Feld n klein) | mittel | cwv-3, cwv-5, cwv-8 |
| A6 | TTFB auf `/` (CrUX 2.038 ms) aufklären: nginx `request_time` auswerten, Redirect-Anteil prüfen; erst messen, dann fixen | mittel (Handy-Origin LCP fehlt 75 ms) | klein | cwv-1, cwv-13, tech-12 |
| A7 | Globus-INP profilieren (993 ms) | mittel | mittel–groß | cwv-2 |
| A8 | Kleine Korrekturen ohne Designwirkung: VideoObject `uploadDate` mit Zeitzone; `<main>` auf Paper und Startseite; WebSite-Schema; doppelte H1 in `search.html`, `theo.html`, `library.html`; `<img src>` segmentweise kodieren (gemeinsamer Helfer); `llms.txt` nicht auf robots-gesperrte `/api/v1/*` verweisen und URL-Zahl aktualisieren; openapi „750K+“, license, contact | niedrig je Punkt | klein | tech-3/7/10/14/15, index-6, bing_geo-4, roadmap-8 |
| A9 | Titel-Suffix der Orte: Rohtyp „City/town/settlement“ durch lesbares Label ersetzen (W9) | Hypothese | klein, aber sichtbarer Text → mit Owner abstimmen | tech-5, gsc-4 |

### 5b Owner-Aufgaben

| # | Aufgabe | Befund |
|---|---|---|
| B1 | **GSC-Oberfläche, Seitenindexierung → Soft 404:** Validierungsstatus ablesen (lief nach dem 05.09. überhaupt eine?), Validierung neu starten. Danach „Indexierung beantragen“ für die Kopf-Orte der Worklist (`output/seo-audit-2026-10-08/scratch/final/request_indexing_worklist.csv`, ~10 pro Tag), dazu `/sites/england` und das Hard-Stone-Paper sowie die Oktober-Paper. Nach 14 T. mit `scripts/idx_inspect_run.py` / `scripts/roadmap_inspect.py` nachmessen. Wirkung ist nicht belegt; es ist der einzige Hebel, der den Crawl-Ausschluss direkt adressiert | gsc-1, index-1, critic L1 |
| B2 | **GSC-Exporte** ablegen (z. B. `output/seo-audit-2026-10-19/owner/`): Crawling-Statistik (Zweck, Antwort, Dateityp), Seitenindexierung mit absoluten Zahlen und allen Gründen, Core-Web-Vitals-Bericht, Links, manuelle Maßnahmen | not_measured aller Teilberichte |
| B3 | **Entscheidungen zu Design/Text:** Titel-Label (A9); 1600-px-Hero auf Handy (cwv-6); neue Link-Blöcke Story → Hub / Ort ↔ Paper (traffic-14, A2); Baalbek-Verlinkung (gsc-12); Label-Map für `speculative_tag` in der H1 (tech-9); `articles.html` vs. `/articles/` (tech-6); About-/Methodik-Seite und Atom-Feed (W6/W13) | – |
| B4 | **Freigabe für Produktions-Writes** in einer dafür freigegebenen Session: Reinstate der 6 gescheiterten IDs (6270, 7196, 7458, 7462, 7667, 8047), Rückzug der 4 Junk-Stories (S10), Takt der Reverify-Wellen unter der MiniMax-Wochengrenze | roadmap-2/3/4 |
| B5 | **Off-Page:** Wikidata-Item der Marke, Erwähnungen/Backlinks (0 Bing-Backlinks, 0 enwiki-Links); YouTube-About und Lumen/DMCA prüfen; eigener YouTube-Kanal (T3, OAuth offen) | bing_geo-1, roadmap-11 |
| B6 | **Mess-Budget:** SerpApi-Kontingent im November für SERP-Schnappschüsse der Ortsseiten-Queries (Ursache CTR-Rückgang, AIO-Zitate) | critic L5, bing_geo-8 |

### 5c Inhalt und DB

| # | Maßnahme | Befund |
|---|---|---|
| C1 | Ortszuordnung der Stories ausbauen: 52 % der Story-Suchlander landen auf Stories ohne Ort; Matcher-Toleranz und Umhängen (W2) | traffic-1 |
| C2 | Kopf-Orte: Datierungen Göbekli Tepe und Baalbek korrigieren, fehlende gefragte Orte im Scope (Kolosseum, Karthago, Ephesos, Ninive, Mohenjo-daro, Chaco Canyon) über den db-final-Prozess | roadmap-5 |
| C3 | Verwandte-Story-Links für den Langschädel-Cluster (keine Ortsseite, Scope-Regel) | traffic-7 |
| C4 | Reverify, Reinstate-Rest und Junk-Rückzug (Writes, siehe B4) | roadmap-2/3/4 |

---

## 6 Umsetzungsstand des Fahrplans vom 08.10.

Quelle: `roadmap.md` §2–3 samt Prüfung; Commits per `git log` auf `origin/main`, Live-Checks am 19.10.

| Punkt | Stand | Beleg / Wirkung |
|---|---|---|
| S1 Soft-404-Validierung, Indexierung beantragen | offen bzw. ohne messbare Wirkung | 59 von 60 Worklist-Soft-404 unverändert; ob beantragt wurde, nicht messbar |
| S2 Dashboard-Messfehler | umgesetzt (179cf78, deployt mit 2556cc4) | Rest: `moving` (D7); neue Lücken D1–D5 |
| S3 robots.txt Teil-Sitemaps | umgesetzt (0ba5d4b) | GPTBot/ClaudeBot holen Teil-Sitemaps (66/651), Kausalität nur zeitlich |
| S4 llms.txt | umgesetzt (0ba5d4b) | 0 Abrufe durch erfasste Crawler; verweist auf gesperrte `/api/v1/*` |
| S5 Entitäts- und Bild-Schema | teilweise (449a42b) | QID 27/30; WebSite-Schema fehlt |
| S6 Bild-URLs kodieren | teilweise | og:image/JSON-LD kodiert, `<img src>` nicht; 1.002 Hero-Zeilen mit Leerzeichen |
| S7 Öffentliche API | weitgehend (3635daf, 361574c) | Suche liefert den kuratierten Ort auf Platz 1 (ohne `url`/`wikidata`); openapi „750K+“, license/contact fehlen |
| S8 Paper-Seiten | teilweise (8ac93f5, b4a00ce) | `<main>` fehlt |
| S9 VideoObject, nocookie | umgesetzt (2556cc4) | `uploadDate` ohne Zeitzone (Warnung) |
| S10 Junk-Stories, Label-Map, Lyra-OFFLINE | offen | 4 Junk-Stories liefern 200 |
| S11 Härtung | offen | kein HSTS, `server_tokens` aus; stats-Subdomain hat schon `X-Robots-Tag: noindex` (kein `Disallow` nötig) |
| W1 Story-Verifier + Bestand | teilweise | 122 von 2.990 geprüft |
| W2 Datenhygiene Kopf-Orte | offen | Göbekli −5000, Baalbek −7000 |
| W3 Debatten-Dossiers | offen | Kopf-16 234 / 0 (90 T.) |
| W4 Silos verbinden | teilweise (8b87ab1, 8ac93f5) | Ort ↔ Paper fehlt |
| W5 Weiterklick auf Story-Seiten | umgesetzt (8ac93f5) | Story → Ortsseite 0/170 |
| W6 Vertrauensseiten, Marke, Lizenz | teilweise (d05ba72, eb678c4, a613add) | `/about`, `/methodology` 404 |
| W7 Fehlende Orte | offen (an db-final) | 0 neue Orte |
| W8 Live-Tracker | offen | – |
| W9 Titel/Description-Experiment | offen | – |
| W10 Einheitliche Suche | offen | interne Suche 25 % Null-Treffer |
| W11 KI-Ortstexte ohne Quelle | offen im SEO-Strang | nicht geprüft |
| W12 Paper-Bibliothek | teilweise / entschieden (Off-Topic bleibt) | – |
| W13 Atom-Feed | offen | `/feed.xml` usw. 404 |
| T1, T3–T7 | offen | T3: 3 gerenderte, 0 veröffentlichte Folgen |
| T2 Creator-Rückkanal | verworfen (Owner 09.10.) | – |
| E1–E13 | E1, E2, E10, E12, E13 entschieden; E3, E4, E6, E11 umgesetzt; E5 geändert (sig ≥ 2, Reinstate-Welle 12.10.); E7, E9 teilweise; E8 an db-final, Wirkung 0 | `roadmap.md` §3 |
| Owner-Aufgaben §7 | Bing WMT erledigt (verifiziert), Medium-Canonicals und Datenschutz erledigt (laut Memory), GitHub-Profil erledigt (Memory); Soft-404-Validierung und Anträge nicht als wirksam erkennbar; GSC-Exporte bis auf den Soft-404-Export fehlen; YouTube-About und Lumen nicht geprüft | `roadmap.md` §3 |

Außerhalb des Fahrplans: Journal-Hub zusammengelegt (5d8f1b8 u. a., 12.–17.10.).

---

## 7 Nicht gemessen

- **Nur in der GSC-Oberfläche:** Crawling-Statistik, Status der Soft-404-Validierung, Seitenindexierung absolut und nach
  Gründen (letzter Stand 1.877 Soft 404 am 04.10. aus dem UI-Export), Core-Web-Vitals-Bericht, Rich-Result-/Video-
  Erkennung, Links, manuelle Maßnahmen; ob Indexierungsanträge gestellt wurden.
- **Ursachen:** CTR-Rückgang der Ortsseiten auf gleicher Position (braucht SERP-Schnappschüsse, Budget aufgebraucht);
  Crawl-Schub am 12.10.; KI-Referral-Einbruch am 08./09.10.; Shillourokambos-Schwall; Feld-TTFB auf `/`; Globus-INP.
- **GSC:** Daten ab 18.10. nicht final; 87 % der Klicks hinter anonymisierten Queries (Query-Aussagen decken 13 % der
  Klicks); AI Overviews/AI Mode nicht von Web trennbar; HTTP-Status von URLs ohne Klick.
- **Crawl:** Zeitraum vor 05.10. (nginx-Rotation 14 T.); Echtheit von ClaudeBot, ExaSearchBot, SEO-Tool-Bots; Nutzen
  von Amazonbot/Applebot; Googlebot-Image nur gezählt.
- **Verhalten:** Verweildauer, Pogo-Sticking, Rückkehrer je Monat, Discord-Klicks über die Landing, Conversion
  Sucheinstieg → Anmeldung, Founder-Besuche.
- **CWV:** CrUX-URL-Daten für Orts-, Hub-, Story-, Paper-, Journalseiten (404, zu wenig Traffic); Globus mit GPU im Lab;
  RUM für Paper/Journal (n ≤ 8).
- **GEO/Bing:** echte Antworten von ChatGPT, Perplexity, Gemini, Copilot, Claude; Bing-SERPs; Bing-Verlauf vor 09.10.;
  Common Crawl CC-MAIN-2026-34 (504); Vollzählung der QIDs.
- **Inhalt:** Story-Defektquote (judge40); Prosa-/Claim-Status-Form der neu geprüften Stories im Live-HTML; Duplikate
  über alle 4.900 Orte (nur Stichprobe 298).
- **Unbelegte Deutungen aus den Teilberichten** (nicht übernommen): „viral“ beim Langschädel-Cluster, „automatisiert“
  beim Shillourokambos-Schwall, „Crawl-Nachfrage statt Entdeckung“ bei den Papern, „Indexierungsanträge wirken“.

---

## 8 Methodik und Reproduktion

- **Dashboard-Rohdump:** `raw/dashboard/*.json` (`scripts/dump_dashboard.py`; Token per `mint_stats_token`, Abruf über
  `localhost:8000/api/stats/<endpoint>` auf dem VPS).
- **GSC:** `raw/gsc/` (`scratch/gsc/pull.py`, `a_types.py`, `a_weeks.py`, `a_queries.py`; Nachrechnung
  `scratch/gsc_pruefung/*.py`); URL Inspection `scripts/idx_build_sample.py`, `idx_inspect_run.py` (Seed wie 08.10.),
  `idx_analyze.py`, `roadmap_inspect.py`, `roadmap_inspect_soft404.py` (Seed 20261019), `tech/inspect_batch.py`;
  Sitemaps `idx_gsc_sitemaps.py`; Story-Kohorten `idx_gsc_story_cohorts.py`.
- **Crawl:** nginx `access.log*` und `crawlers.log` auf dem VPS, IP-Verifikation gegen Googles vier Listen, OpenAI- und
  Bing-Listen; Aggregate `raw/crawl/agg.json`, `drill.json` (`scripts/crawl_agg.py`, `crawl_drill.py`); je URL
  `critic/scripts/google_per_url.py` → `critic/raw/google_per_url.json`.
- **Traffic:** Umami-DB lesend, Dashboard-SQL nachgebaut (`traffic/scripts/segment_sessions.py`, `crosstab.py`,
  `gsc_types_pages.py`; Prüfung `traffic/verify/*.py`).
- **CWV:** CrUX- und PSI-API (`scripts/cwv_readout.py`, `cwv_summarize.py`, `psi_table.py`), RUM aus Umami
  (`rum_vitals.py`, `rum_clean.py`, `rum_globe_split.py`, `rum_site_ttfb.py`), Rohdaten `raw/cwv/`.
- **Technik:** Live-Abrufe ohne JS (`scripts/tech/onpage.py`, `sample_stats.py`, `summarize.py`, `ttfb_stats.py`),
  Stichproben 298 Orte / 118 Stories, `raw/tech/`; Inhaltsvergleich Soft-404 gegen indexiert
  `critic/scripts/compare_content.py`.
- **Bing/GEO:** BWT-API `scripts/bing_dump.py` → `raw/bing/`; SerpApi `scripts/serp_rerun.py`, `serp_validity.py` →
  `raw/serp/`; `raw/geo/`.
- **Roadmap/KPI:** `scripts/roadmap_kpi.py`, `roadmap_top100.py` (Methode `summary.py` vom 08.10.), `raw/roadmap/`.
- **DB:** nur lesend über `ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c '…'"`.
- **Prüfung:** Jeder Teilbericht hat einen Abschnitt „## Prüfung“ mit Urteil je Befund (bestätigt / korrigiert /
  widerlegt) und Nachrechnung der Kennzahlen; `critic.md` prüft die Abdeckung aller 19 Dashboard-Endpunkte und löst die
  Widersprüche W1–W8 auf.
- **Zeitfenster:** GSC final bis 17.10.; nginx bis 19.10. ~18:41 UTC; Inspection und Live-Abrufe 19.10. ~17:15–19:30 UTC.
