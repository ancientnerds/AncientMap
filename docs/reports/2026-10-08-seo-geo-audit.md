# SEO- und GEO-Audit ancientnerds.com – Endbericht

Stand 08.10.2026. Ziel des Owners: ancientnerds.com wird **die** Adresse für alles rund um Archäologie, für die
Zuschauer der 39 Kanäle, die Lyra liest (`pipeline/lyra/channels.json`). Dazu gehören Alt-History-Kanäle (UnchartedX,
Bright Insight, Ancient Architects, Brien Foerster, Ancient Builders Project, Curious Being, Matthew LaCroix,
PraveenMohan …) und Mainstream-Kanäle (Stefan Milo, toldinstone, Ed Barnhart, The Prehistory Guys …).

**Grundlage.** Acht Sammler (GSC, Umami, Crawler-Logs, Technik, GEO, Publikum, Inhalt, Off-Page), ein Kritiker und
sechs gegenprüfende Verifier (Index, Messung, Qualität, Technik, Chancen, Nachfrage). Jeder Befund steht hier nur in
seiner geprüften Form: Korrigierte Aussagen ersetzen die ursprünglichen, Widerlegtes steht in Anhang A. Was kein
Verifier geprüft hat, trägt den Zusatz „ungeprüft“ und das ursprüngliche Vertrauen (gemessen, starke Folgerung,
Hypothese). Alle Arbeiten liefen read-only: keine DB-Schreibzugriffe, keine GSC-Anträge, kein IndexNow, kein Deploy.

**Fenster, wenn nicht anders angegeben:**
- GSC: 28 Tage bis 06.10. (dataState final).
- nginx-Log: 24.09.–08.10. (14,85 Tage). Googlebot gilt nur als verifiziert, wenn die IP in Googles veröffentlichten
  Bereichen liegt.
- Umami: 17.09.–08.10. (21,3 Tage, die ganze Tracker-Historie).
- Produktions-DB: Stand 08.10.

Befund-IDs (z. B. `gsc-04`, `idx-01`) verweisen auf die Teilberichte (Anhang B). Bereiche: **[SEO]** Google und Bing,
**[GEO]** KI-Assistenten, **[Publikum]** Zielgruppe und Verbreitung, **[Messung]**.

Nicht als Defekt gewertet werden die Owner-Entscheidungen: `/sites/united-kingdom` antwortet 404 (aufgeteilt in England,
Scotland, Wales und Nordirland), zurückgezogene Hubs antworten 404, Stories mit niedriger Signifikanz antworten 410,
Konto-, DB-, Lyra-Ops- und Rechtsseiten tragen noindex, und Mittelalter liegt außerhalb des Scopes (Amerika und
Ozeanien bis 1500 n. Chr.). Designänderungen stehen hier nur als Vorschläge.

---

## 1 Kurzfassung

1. **Die Google-Suche wächst, und bestehende Seiten werden nicht abgewertet.** In 28 Tagen kamen 973 Klicks und 70.984
   Impressionen bei Ø-Position 8,8, das sind +53 % Klicks gegenüber dem Stand vom 15.09. Alle Seitentypen wuchsen bis
   zur Woche ab 28.09. 97 % des Verkehrs ist Non-Brand. Nach „ancient nerds“ sucht kaum jemand (41 Impressionen in 28
   Tagen).
2. **Der Engpass: Google crawlt neue URLs nicht mehr.** Von den Stories, die ab dem ~11.09. erschienen, bekam nur eine
   von 204 eine Impression. Seit dem 17.09. bekam keine neue Story mehr eine erste Impression. Von 103 Stories seit dem
   25.09. holte Googlebot nur 3, die zehn Paper vom 05.–07.10. gar keine.
   - Am Entdecken liegt es nicht: 95–99 % der neuen Stories standen auf Seiten, die Googlebot nach ihrem Erscheinen
     abrief, und die Startseite verlinkt alle 91 Länder-Hubs.
   - Am Server liegt es auch nicht: 1 × 503 in 5.795 Requests, kein Rate-Limit, keine Sperre.
   - Was Google crawlt, indexiert es fast immer.
   - Der Abriss fällt zeitlich mit einer Welle von Ausschuss-Signalen zusammen: ~770 bis dahin indexierbare Stories auf
     410 (11.09.), Bundle-Churn (08.–12.09.), 4.900 Legacy-301 (15.09.) und ~1.500 stehende Soft-404-Urteile.
   - Ob Qualität, fehlende Popularität oder diese Umbausignale den Ausschlag geben, zeigt nur die GSC-Crawling-Statistik
     in der Oberfläche (Owner).
3. **Ein Drittel der Ortsseiten hängt im Soft-404-Urteil vom August, und Google holt sie nicht von selbst neu.**
   - Gepoolt sind es 31,5 % (95 %-Intervall 22–43 %, ≈1.080–2.100 Seiten), alle zuletzt am 10.–14.08. gecrawlt.
   - Von 23 solcher URLs holte Googlebot in 14 Tagen keine einzige, von 47 indexierten 12.
   - Betroffen sind 35 der 100 gefragtesten kuratierten Orte, darunter Pompeji, Hadrianswall, Great Sphinx,
     Derinkuyu, Nazca, Tal der Könige, Knossos, Lascaux, Cahokia, Sacsayhuamán und Puma Punku.
   - Die Seiten bestehen den Render-Test heute. Das ist der billigste große Hebel, und er liegt allein beim Owner in
     der GSC-Oberfläche.
4. **Unsere Sichtbarkeit hat mit der Nachfrage nichts zu tun.**
   - Über 4.285 kuratierte Orte korrelieren Wikipedia-Aufrufe und GSC-Impressionen nur mit ρ = 0,11.
   - Auch indexierte Kopf-Orte bringen nichts. Troja hatte 1,23 Mio. Wikipedia-Aufrufe im Quartal und bei uns 2
     Impressionen in 90 Tagen.
   - Die Ortsseiten sind Wikipedia-Auszüge (2.782 von 4.900 Texten wörtlich). Sie beantworten die Fragen der
     Zielgruppe nicht; Angaben zum Besuch fehlen auf 15 von 15 geprüften Seiten.
   - 38 gefragte Orte im Scope fehlen ganz (2,72 Mio. Aufrufe im Quartal, darunter Kolosseum, Karthago, Ephesos,
     Ninive, Çatalhöyük und Nan Madol). 11 davon liegen seit dem 15.09. als Vorschlag in der Prospector-Queue.
5. **Die Stories sind der Traffic-Motor und zugleich das größte Qualitätsrisiko.**
   - Sie bringen 55 % der Klicks. Behauptungs-Stories werden doppelt so oft geklickt.
   - In einer Zufallsstichprobe (n = 40) geben 27,5 % (16–43 %, ≈600 Seiten) eine umstrittene Creator-Behauptung als
     Tatsache aus. 32,5 % (≈710) haben einen belegten Sachfehler oder einen Widerspruch zwischen Überschrift, Text und
     Key facts.
   - Die Ursache ist eine Code-Stelle: Der Web-Verifier korrigiert nur den Fließtext, und dieser Text ist ein
     generierter Tweet (`pipeline/lyra/tweet_verifier.py:533–542`, `tweet_generator.py:186`).
   - Das Risiko einer künftigen Abwertung durch einen Klassifikator schätzen die Prüfer auf mittel bis hoch, das einer
     manuellen Maßnahme wegen „scaled content“ auf mittel.
6. **Die Inhalte kennen sich nicht.**
   - 0 von 41 Papern verlinken eine Ortsseite oder Story, 0 von 29 Ortsseiten ein Paper.
   - Seit dem 10.09. verlinkt die Startseite kein Paper mehr.
   - Nur 4,9 % der Story- und 3,1 % der Ortsseiten-Einstiege aus der Suche klicken intern weiter. Von 657
     Story-Einstiegen ging ein einziger zur Ortsseite.
7. **[GEO] KI-Assistenten nutzen uns als Werkzeug, nicht als Quelle.**
   - ChatGPT-User liest organisch ~40 Seiten pro Tag. KI-Assistenten schicken ~6 Menschen pro Tag (zu ~90 % von
     ChatGPT), ohne Wachstum; rund 80 % davon landen auf Startseite oder Globus.
   - Die KI-Suchcrawler holen ~420 Inhaltsseiten pro Tag, 2,6-mal so viel wie Googlebot.
   - Die Trainings-Crawler GPTBot und ClaudeBot sind fast verschwunden, ohne dass wir sie sperren. Sie holen nur noch
     den Sitemap-Index, nie eine Teil-Sitemap. Common Crawl hat die Domain 2026 nie erfasst.
   - Gefragt nach der Verlässlichkeit, rät eine Such-KI ausdrücklich vom Zitieren ab: DAO/NFT-Spuren, „questioning the
     mainstream narrative“, keine About-Seite (n = 4, nur ein Werkzeug).
8. **[Publikum] Auf den Plattformen der Zielgruppe existieren wir nicht.**
   - In drei Wochen kam kein Besucher über YouTube (der einzige Treffer war ein Eigentest) und keiner von einer fremden
     Website.
   - Nur 1 von 3.268 Videobeschreibungen der Kanäle nennt uns.
   - Der eigene YouTube-Kanal ruht seit 06.02.2024 als „AI Art Community“, im Studio liegt eine gerenderte, nicht
     veröffentlichte Episode.
   - Bindung: 2,4 % Rückkehrer, 6 Konten, ~1,7 echte Discord-Klicks pro Tag.
9. **[Messung] Umami ist verlässlich, das Dashboard an vier Stellen nicht.**
   - Die „43 % Abdeckung“ war ein Artefakt eines Scrapers aus 47.79.0.0/16. Bereinigt stimmen Umami, nginx und GSC
     überein (Umami/GSC 1,14).
   - Falsch sind aber genau die SEO-Kennzahlen:
     - „human“ ist seit 04.10. um ~40 % zu hoch.
     - Die Scrolltiefe auf Story- und Ortsseiten ist tot.
     - „Outbound youtube.com“ zählt eingebettete Wiedergaben.
     - Der nginx-Block im Sources-Panel ist ~5-fach zu hoch.
   - Vor dem 30-Tage-Review (~26.10.) beheben.
10. **Die fünf wichtigsten Schritte:**
    1. Owner: die Soft-404-Validierung prüfen bzw. neu starten und „Indexierung beantragen“ nach der Nachfrageliste
       (§7).
    2. Den Story-Verifier reparieren und den Bestand in Wellen nachziehen (§6 W1).
    3. Die vier Dashboard-Fehler beheben (§6 S2).
    4. Kopf-Ortsseiten zu Debatten-Dossiers ausbauen. Vorher Verknüpfung und Datierung bereinigen (§6 W2, W3).
    5. Vertrauens- und Entitätssignale setzen: About- und Methodik-Seite, DAO-Spuren entfernen, eine einheitliche Lizenz,
       sameAs aus den ≈4.441 eindeutigen Wikidata-IDs (§6 S5, W6).

---

## 2 Zahlenlage

| Bereich | Kennzahl | Wert | Fenster | Quelle |
|---|---|---|---|---|
| Google | Klicks / Impressionen / CTR / Ø-Position | 973 / 70.984 / 1,37 % / 8,8 | 28 T. bis 06.10. | GSC API (gsc-01) |
| Google | Klicks / Impressionen | 1.633 / 115.115 | 90 T. | GSC API |
| Google | Veränderung Klicks | +53 % (635 → 973) | 28 T. bis 15.09. gegen bis 06.10. | GSC API |
| Google | Brand „ancient nerds“ | 41 Impr. / 31 Klicks (3,2 % der Klicks) | 28 T. | GSC, Regex (gsc-09, ungeprüft) |
| Google | Anteil Stories an den Klicks | 532 Klicks = 55 % | 28 T. | GSC page (gsc-06, aud-01) |
| Google | sichtbare (nicht anonymisierte) Queries | 15 % der Klicks, 23 % der Impressionen | 28 T. | GSC |
| Google | Bildersuche | 1.970 Impr., 0 Klicks, Pos. 43,8 | 28 T. | GSC type=image |
| Google | Video, Discover, Google News | 0 Impressionen | 90 T. | GSC |
| Google | Legacy `/site.html?id=` | 1.216 Impr. = 5,1 % (28 T.: 8,75 %), fallend | Woche 30.09.–06.10. | GSC (gsc-08) |
| Google | Hawara-Cluster | 72 Klicks / 2.130 Impr. = 4,4 % aller Klicks | 90 T. | GSC (aud-06) |
| Google | 16 Kopf-Ortsseiten gegen ihre Stories | 426 Impr. / 1 Klick gegen 8.207 / 168 | 90 T. | GSC (verify-opportunity) |
| Google | Nachfrage gegen Sichtbarkeit | Spearman ρ = 0,11 (n = 4.285 Orte) | Wikipedia Jul.–Sep., GSC 90 T. | demand-01 |
| Index | Ortsseiten mit Soft 404 | 23/73 = 31,5 % (22–43 %), ≈1.080–2.100 Seiten | Inspektion 08.10. | URL Inspection, drei Zufallsstichproben gepoolt (idx-01) |
| Index | davon von Googlebot neu geholt | 0 von 23 (indexierte: 12 von 47) | 24.09.–08.10. | nginx |
| Index | Top 100 Orte nach Nachfrage | 35 Soft 404, 64 indexiert, 1 unbekannt; 40 ohne Impression | 08.10. / 90 T. | Inspection + GSC (demand-01) |
| Index | Länder-Hubs ohne Impression | 38 von 91 | 90 T. | GSC (gsc-02) |
| Index | Länder-Hubs nicht indexiert | 11 von 26 inspizierten (42 %) | 08.10. | URL Inspection |
| Index | beworbene Stories ab 01.09. von Googlebot geholt | 29/274; ab 15.09.: 5/169; ab 25.09.: 3/103 | 24.09.–08.10. | nginx × DB (gsc-03, crw-01) |
| Index | neue Stories indexiert | 2 von 36 inspizierten | 08.10. | URL Inspection |
| Index | Stories mit Impression nach Erstelldatum | 15.–31.08. 85 %; 01.–10.09. 43 %; 11.–20.09. 1 %; ab 21.09. 0 % | 90 T. | GSC × DB (content-02) |
| Index | Paper vom 05.–07.10. von Googlebot geholt | 0 von 10 | 14 T. | nginx |
| Crawl | verifizierter Googlebot | 5.795 Requests ≈ 390/Tag; HTML mit 200: 140–180/Tag | 14,85 T. | nginx (tech-06) |
| Crawl | Googlebot auf 410-Seiten | 1.211 = 20,9 % aller Requests; Story-Crawl 1.148 von 2.285 (50 %) auf 224 IDs | 14,85 T. | nginx (crw-02) |
| Crawl | Googlebot auf Assets / Legacy-301 | 24,5 % / ~7 % | 14,85 T. | nginx |
| Crawl | Stories im 410-Zustand | 893 | 08.10. | DB (gsc-14) |
| Crawl | Herkunft Googlebot | seit 27.09. ≥ 99 % aus 192.178.*; 66.249.* nur 23,6 % des Fensters | 14,85 T. | nginx + rDNS (crw-03) |
| Bing | Inhaltsseiten pro Tag | bingbot 281 gegen alle Google-Crawler 164 | 24.09.–07.10. | nginx (crw-04) |
| Bing | IndexNow | 44.784 URLs gemeldet, 100 % HTTP 200 | seit 24.09. | Lyra-Log (offpage-10, gemessen, ungeprüft) |
| Bing | Suchbesuche nicht von Google | 20,0 % (251/1.257); nginx bereinigt 23,4 % | 17.09.–08.10. | Umami (stats-07) |
| GEO | ChatGPT-User-Abrufe | 943 (IP-verifiziert); davon 358 stündlich auf „/“; organisch 585 auf 381 URLs ≈ 40/Tag | 14,8 T. | nginx (geo-01, crw-12) |
| GEO | KI-Suchcrawler (OAI-SearchBot, PerplexityBot, Applebot, Exa) | 5.893 Inhaltsseiten ≈ 421/Tag | 14 T. | nginx (crw-05) |
| GEO | GPTBot / ClaudeBot (echt) | 169 Requests, HTML nur „/“ + 4 Hubs / 208 Requests, 0 Inhaltsseiten | 14 T. | nginx (crw-08) |
| GEO | Common Crawl | 0 Captures in 9 Crawls 2026 | CC-MAIN-2026-04 bis -39 | CC-Index (geo-08) |
| GEO | Menschen von KI-Assistenten | 121 = 5,7/Tag; 89 % ChatGPT; flach (+8 % KW39 → KW40) | 21,3 T. | Umami (stats-06) |
| GEO | Einstiege der KI-Besucher | Startseite 60, Globus 35, Story 16, Paper 4, Ortsseite 2 | 21,3 T. | Umami |
| GEO | llms.txt-Abrufe durch KI-Crawler | 0 von 25 | 14,8 T. | nginx (crw-10) |
| GEO | Wikidata-IDs im Markup | 0 von 4.539 (≈4.441 eindeutig) | 08.10. | DB + Live-JSON-LD (geo-06) |
| GEO | Links aus en.wikipedia | 0 | 08.10. | exturlusage |
| Publikum | echte Besuche | 2.261 (≈106/Tag), davon 639 engagiert; inkl. nicht filterbarer Gründer-Besuche | 21,3 T. | Umami |
| Publikum | Google-Besuche gegen GSC-Klicks | 606 gegen 530 (1,14×); nginx bereinigt 588 | 26.09.–06.10. | Umami, GSC, nginx (stats-01) |
| Publikum | Suchbesucher pro Tag | ~53 Google + ~17 andere Suchmaschinen | 26.09.–06.10. | Umami, nginx bereinigt |
| Publikum | interner Weiterklick nach Sucheinstieg | Story 4,9 % (32/657), Ortsseite 3,1 % (12/381), Länder-Hub 30 %, Startseite 63 % | 17.09.–08.10. | Umami (stats-04, measure-04) |
| Publikum | Story → Ortsseite | 1 von 657 | 17.09.–08.10. | Umami |
| Publikum | Video-Abspielquote | 7,9 % der Story-Sucheinstiege | 17.09.–08.10. | Umami media_play (measure-03) |
| Publikum | Besuche über YouTube / von fremden Websites | 0 (1 Eigentest) / 0 | 21 T. / 25.09.–08.10. | Umami, nginx bereinigt (stats-08, offpage-01) |
| Publikum | Rückkehrer | 2,4 % (14/583); September 3,1 % (Monats-Salt deckelt) | 21,3 T. | Umami (stats-12) |
| Publikum | Konten / echte Discord-Klicks | 6 (2 Gründer), letzter Login 04.10. / ~1,7 pro Tag | 08.10. / 14,8 T. | Members-Panel, nginx mit JS-Nachweis |
| Publikum | Videobeschreibungen der Kanäle mit Link auf uns | 1 von 3.268 | ganzer Ingest | DB (offpage-02) |
| Publikum | eigener YouTube-Kanal | 2,11 Tsd. Abos, letzter Upload 06.02.2024 | 08.10. | live (aud-11) |
| Publikum | Impressionen außerhalb US/GB/CA/AU/NZ/IE | 41,2 % (ohne englischsprachige Länder ~35 %); deutschsprachige Queries ≈ 0 | 28 T. | GSC (content-18, stats-15) |
| Inhalt | indexierbares Inventar | 4.900 Orte, 2.182 Stories, 41 Paper, 27 Journale, 91 Hubs | 08.10. | Sitemaps, DB |
| Inhalt | Texte der Ortsseiten | 2.782 wörtlich Wikipedia (57 %); 2.080 KI-Paraphrasen, davon 706 ohne Quellenmarke; keiner ≥ 1.500 Zeichen | 08.10. | DB (content-01, qual-02) |
| Inhalt | Stories pro Video | 2,91 (2.182 aus 751 Videos), Median 375 Zeichen | 08.10. | DB (content-03) |
| Inhalt | Story-Defekte | 27,5 % Fringe als Tatsache; 32,5 % Fehler oder Widerspruch; 57,5 % irgendein Defekt | n = 40, Seed fest | Stichprobe (verify-quality) |
| Inhalt | Paper-Themendrift | 17 ohne Archäologie (+5 Grenzfälle), 7 der 10 neuesten; 5 Recherchen „for a novel“ | 08.10. | geo-15, opp-03 |
| Inhalt | Theo-Paper-Befunde reparaturbedürftig | 71,4 % (1.503 von 2.105) | 04.10. | `docs/reports/theo-paper-defects-2026-10-04.md` |
| Inhalt | Ortsseiten ohne Bild / kaputte Hero-URLs | 1.092 / 989 mit Leerzeichen | 08.10. | DB (tech-11) |
| Technik | Feld-Vitals p75 | Story LCP 1,9 s, INP 48 ms, CLS 0,00; Ortsseite 1,9 s, 72 ms, 0,023; Paper-CLS mobil 0,259 (n = 12) | 21–28 T. | Umami-RUM (stats-05, tech-09) |
| Technik | Renderzeit am Origin / RUM-TTFB | 14–130 ms (Research 346 ms) / ≈1 s | 08.10. | curl lokal, RUM (tech-16) |

---

## 3 Was gut ist

- **[SEO] Wachstum ohne Abwertung.** +53 % Klicks in 28 Tagen. Die Position stieg von ~36 (Mitte August) auf ~8,6.
  Wöchentlich wuchsen Ortsseiten von 5.194 auf 9.088 und Stories von 6.314 auf 12.991 Impressionen (KW ab 14.09. bis
  KW ab 28.09.). Nach dem Massen-Rewrite der Ortstexte am 25.09. gab es keinen Einbruch. (gsc-01 ungeprüft, gemessen;
  qual-05)
- **[SEO][Publikum] Stories treffen den Long-Tail nach dem Video.** Rund 73 % der Story-URLs haben Impressionen. Alt-History-
  und Mainstream-Stories leisten pro Story gleich viel (0,16 gegen 0,18 Klicks in 28 Tagen). Behauptungs-Kategorien
  werden doppelt so oft geklickt: unverified 3,1 %, theory 2,0 %, general 1,2 % CTR. Spitzen sind Hawara/Louis de
  Cordier, Drechselsäulen und Rampentheorien auf Position 6–9. (gsc-06, content-07, aud-01, stats-09; gemessen, ungeprüft)
- **[SEO][GEO] Die technische Basis ist sauber.**
  - Vollständiges SSR mit byte-identischem HTML für Googlebot, GPTBot und Chrome (43 URLs × 3 UAs).
  - Ein Redirect-Hop, echte 404/410, Sitemaps ohne Fehl-URLs.
  - Feld-Vitals der Story- und Ortsseiten im grünen Bereich, Origin-Renderzeit 14–130 ms.
  - Das Asset-Leck vom September bleibt behoben (Googlebot-Assets 25 % statt 67 %).
  - Es gibt keine selbst verursachte Crawler-Sperre: robots, nginx, ufw und iptables sind geprüft, 0 × 403/429/444 an
    GPTBot, ClaudeBot und CCBot.
  - (tech-01 bis tech-04, crw-15, stats-05 ungeprüft, gemessen; tech-v06)
- **[SEO] IndexNow wirkt bei Bing.** bingbot holt 1,7-mal so viele Inhaltsseiten wie alle Google-Crawler zusammen, an
  allen 14 Tagen. Neue Stories holt er im Median binnen einer Stunde, obwohl er die Story-Sitemap nur einmal am Tag
  abruft. (crw-04)
- **[GEO] Die KI-Suche liest uns.** OAI-SearchBot, PerplexityBot, Applebot und Exa holen ~421 Inhaltsseiten pro Tag.
  ChatGPT-User liest organisch ~40 Seiten pro Tag. Pro URL fragt ChatGPT die Theo-Paper zu den Debatten der
  Zielgruppe am stärksten nach (Stargate 17, hard-stone 14, Weltzeitalter 11, Flut/Younger Dryas 9). Bei der Suche nach einer
  Karte mit den meisten Orten empfiehlt die Such-KI uns an erster Stelle (Anekdote, n = 1). (crw-05, geo-01, crw-06
  ungeprüft, gemessen; offpage-09 ungeprüft)
- **[GEO] Provenienz und KI-Kennzeichnung der Ortstexte sind vorbildlich.** 4.862 von 4.900 Beschreibungen tragen
  maschinenlesbare Herkunft, die Wikipedia-Attribution ist sichtbar und steht im JSON-LD, Stories und Paper tragen
  `digitalSourceType`. Einschränkung: Die „Sources“ der Stories sind oft schwache Blogs (Baalbek: 4 von 5).
  (content-17 ungeprüft, gemessen; Kritiker)
- **[SEO] Interne Verlinkung für Stories und Hubs existiert schon.** Story-Seiten verlinken die 5 neuesten Stories
  desselben Orts, Ortsseiten die 10 neuesten. Die Startseite verlinkt alle 91 Hubs (am 08.10. nachgezählt). (idx-02)
- **[SEO] noindex für spekulative Stories kostet wenig.** Selbst bei voller Indexierung wären höchstens ~3.700
  Impressionen und ~40 Klicks pro 28 Tage zu holen. (aud-17, gsc-10 korrigiert)
- **[Messung] Umami deckt die echten Besucher ab** (Umami/GSC 1,14, Umami/nginx bereinigt 1,03). Eine UTM-Konvention für
  Discord-Bot, Shorts und Studio-Episoden existiert bereits. (stats-01 korrigiert, stats-14 widerlegt)
- **[Publikum] Das eingebettete Video wird genutzt.** Die Klick-Fassade existiert seit 21.08. 7,9 % der
  Story-Sucheinstiege starten das Video; das ist die häufigste echte Interaktion auf Story-Seiten. (measure-03)

---

## 4 Was schlecht ist

### 4.1 [SEO] Google

- **Neue URLs werden nicht gecrawlt** (Zahlen in §2). Stories und Hubs sind verlinkt und stehen in der Sitemap; Google
  ruft sie nur nicht ab. Den Papern fehlt der Link tatsächlich: Seit Commit `1df1aa0` (10.09.) verlinkt die Startseite
  kein Paper mehr. Paper-Seiten verlinken weder andere Paper noch Orte oder Stories, und `/research/` holte Googlebot in
  14 Tagen einmal. (gsc-03, crw-01, content-02, idx-03 starke Folgerung, idx-04)
- **Soft-404-Altlast.** ≈31 % der Ortsseiten, 35 der 100 gefragtesten Orte, 9 von 18 Kopfthemen des Publikums
  (Sacsayhuamán, Puma Punku, Sphinx, Derinkuyu, Nazca, Carnac, Ħaġar Qim, Tarxien, Ħal Saflieni). Google crawlt diese
  URLs von selbst nicht nach (0/23 gegen 12/47, p ≈ 0,014). Laut Memory hat der Owner am 05.09. eine Validierung
  gestartet; seither wurde keine Soft-404-URL der Stichproben neu gecrawlt. (gsc-04, tech-05, idx-01, aud-02, demand-01)
- **Kopf-Orte sind unsichtbar, auch wenn sie indexiert sind.** 13 indexierte Flaggschiffe der Zielgruppe hatten in
  28 Tagen 0 Klicks und meist 0–22 Impressionen (Göbekli 30 Impressionen in 90 Tagen auf Pos. 37, Karahan Tepe 0,
  Tiwanaku 0). Unter den Top 50 „hohe Nachfrage, ≤ 10 Impressionen“ sind 23 indexiert (Troja, Sparta, Mykene, Petra,
  Ur, Herculaneum, Karahan Tepe). Ursache ist der fehlende Informationsgewinn gegenüber Wikipedia: 71 von 72 geprüften
  Sätzen sind wörtlich übernommen, 141–268 Wörter stehen im `<main>`. „Wer hat es gebaut“ und „Wie alt wirklich“ fehlen
  oft, der Besuch fehlt immer. Google indexiert die Auszüge (6 von 8), sie ranken nur nicht.
  (gsc-05, content-01, aud-02, aud-03 ungeprüft, demand-01)
- **Die Qualität der Story-Masse ist ein Abwertungsrisiko** (§1 Punkt 5).
  - Fringe-Rahmung kommt fast nur aus Alt-Kanälen (10 von 25 gegen 1 von 15). Fehler entstehen in beiden Lagern
    (9 von 25 und 4 von 15), weil die Pipeline sie erzeugt.
  - Korpus: 38 % der Texte haben Emojis. Nur 17 % der Key-facts-Listen enthalten ein Zuschreibungswort („argues“,
    „the video“).
  - Junk ist weiter live und indexierbar (Stories 7858, 5608, 4747, 4755).
  - Die noindex-Regel greift nur bei `news_category = 'speculative'`. Falsch eingeordnete Fringe-Stories fängt sie
    nicht: Baalbek 6609 steht unter „architecture“, Osireion 6189 unter „theory“.
  - (content-03, geo-03, qual-01, aud-17)
- **410-Ausschuss bindet die Hälfte des Story-Crawls.** 1.148 von 2.285 Story-Abrufen trafen 224 zurückgezogene
  Stories, ohne Abklingen. Keine Seite und keine Sitemap verweist mehr auf sie; Google holt sie aus alter
  Sitemap-Erinnerung. 116 dieser 224 hatten in 28 Tagen noch 2.167 Impressionen. Das ist ein Beitrag zur schwachen
  Crawl-Nachfrage, nicht die Hauptursache, denn der Crawl ist nicht kapazitätsgebunden. (crw-02, gsc-14, tech-06)
- **Themen zersplittern auf viele URLs, keine gewinnt den Kopfbegriff.** 196 Queries treffen ≥ 2 eigene Seiten.
  Baalbek: Ortsseite Pos. 30,7, Story Pos. 15,8, Paper Pos. 7,1. Hawara verteilt sich auf 27 URLs, Giza auf
  9 Ortsdatensätze. (gsc-11 gemessen, ungeprüft; aud-04)
- **Fehlverknüpfungen und Datenfehler an den Kopf-Orten.**
  - Nur 49 % der Ortsnennungen in Stories landen auf einer kuratierten Seite.
  - 218 Stories liegen ≤ 2 km neben einem kuratierten Datensatz (65 Ziele), etwa „Great Pyramid“ (Wikidata) mit 54
    Stories.
  - ≥ 30 Stories hängen an offensichtlich falschen Datensätzen: „EGYPT“ in Aberdeenshire, „Monteverde“ in Rom statt
    Monte Verde in Chile, Rumi Gate. Der kuratierte Barabar-Datensatz heißt „Cavernas de Marabar“.
  - `period_start` ist bei Flaggschiffen falsch und vererbt sich als Perioden-Badge auf jede Story der Site: Göbekli
    −5000 bei eigenem Text 9500 v. Chr., Baalbek −7000 (deshalb zeigt die Fringe-Story „< 4500 BC“), Sacsayhuamán 900,
    Maltravieso −10000.
  - (content-06, aud-09, opp-02, qual-04, geo-05)
- **Erfundenes in KI-Ortstexten.** 706 generierte Texte haben keine Quellenmarke. In der Stichprobe enthalten 2 von 7
  erfundene Angaben (Greater Ridgeway als „major route in Roman Britain“, Kunturmarka „1000–1500 AD, Wari/Inca“), und
  einer übernimmt einen Wikipedia-Fehler (Vauban 1546). (qual-02, starke Folgerung)
- **Doppelte kuratierte Seiten für denselben Artikel** teilen die Signale: 43 Artikel auf 98 Seiten (Knossos 2,
  Pergamon 2, Abu Simbel 3, Ollantaytambo 2). (demand-04, starke Folgerung)
- **Klickrate an guten Positionen niedrig.** 74 % der Impressionen liegen auf Pos. 5,5–10,5, wo Ortsseiten 0,7–1,2 %
  CTR haben. Der Titel formuliert die DB-Taxonomie („· City/town/settlement“ bei 1.130 Orten), ist aber nicht zu lang
  (Median 58 Zeichen). Die Description ist der abgeschnittene Wikipedia-Lead. Ein Teil der Lücke ist Position (Ortsseiten
  9,6 gegen Stories 8,2). (gsc-07 gemessen, ungeprüft; tech-12 korrigiert)
- **Bildersuche ohne Wirkung.** 1.970 Impressionen, 0 Klicks, Pos. 43,8. 989 Hero-URLs mit Leerzeichen brechen
  (Amazonbot 1.005 × 404); sie entstehen an 9 Stellen im Code. Es gibt keine Bild-Sitemap und kein srcset. Die
  Lizenzdaten liegen für alle 3.808 Heros in der DB, nur nicht maschinenlesbar im Markup. (tech-11, crw-13)
- **Paper-Seiten:** CLS mobil 0,259 (Hero ohne reservierte Höhe, kein `<main>`). Die Bibliothek zeigt „0 sources“ bei
  den 9 neuesten Papern, die 28–147 Belege haben, und unplausible 1.880–4.056 „sources“ bei den älteren. (tech-09,
  geo-14)
- **Länder-Hubs sind nackte Listen.** Englands Hub hat 1,5 MB HTML (394 KB gzip) und 1.044 Links. Die Größe erklärt
  das Nicht-Crawlen aber nicht, kleine Hubs sind genauso betroffen. (content-09 ungeprüft; tech-08 korrigiert)

### 4.2 [GEO] KI-Assistenten

- **Werkzeug statt Quelle.** Rund 80 % der KI-Besucher landen auf Startseite oder Globus (Umami 95 von 121, nginx
  bereinigt 82 %). Bei gleichem Einstieg
  verhalten sie sich wie Suchbesucher; „bester Traffic“ war ein Effekt der Einstiegsseite. Bei 25 Publikumsfragen
  erscheinen wir 2-mal im Ergebnis, und zwar im WebSearch-Werkzeug, einem fremden Index. (geo-02 ungeprüft, stats-06)
- **Marke und Vertrauen arbeiten gegen das Zitieren.**
  - Jede Seite trägt `twitter:site @AncientNerdsDAO`, das Organization-`sameAs` zeigt auf das DAO-Medium.
  - YouTube-About: „Ancient History and AI Art Community“ mit OpenSea-Link. GitHub-Profil „ANCIΞNT NΞRDS“.
    README: „750,000+ sites“, „18+ YouTube channels“. 7 der 10 neuesten Medium-Beiträge enthalten NFT- oder
    Krypto-Wortlaut.
  - Der Startseitentext „questioning the mainstream narrative … ‚copper chisels‘“ steht doppelt im HTML (am 08.10.
    live bestätigt).
  - `/about`, `/methodology` und `/contact` antworten 404. Das Impressum (noindex, Owner-Entscheid) sagt nur „published
    without prior human editorial review“.
  - Die Such-KI urteilt „lean toward alternative history … Don't cite it“ (n = 4).
  - (offpage-03, aud-13, offpage-05 ungeprüft)
- **llms.txt sagt KI-Systemen Falsches.**
  - Sie ist seit 10.08. unverändert; die Zahlen 5.012/98/3.001/7.412 stehen gegen tatsächlich 4.900/91/2.182/7.298.
  - Falsch sind „paraphrased, not copied“ (2.782 Texte sind wörtlich) und „author is an organisation“ (7 Paper haben
    Personen-Autoren).
  - „Speculative claims are labelled“ stimmt nur für noindex-Stories.
  - Kein KI-Crawler liest die Datei. Es geht also um Konsistenz und Recht, nicht um Reichweite.
  - (geo-09, tech-18, qual-03, crw-10)
- **Mindestens sechs widersprüchliche Lizenzangaben.** llms.txt nennt CC BY 4.0, das Dataset-JSON-LD, terms.html und
  imprint.html CC BY-NC-SA, das Paper-JSON-LD CC BY, die Beschreibungen CC BY-SA, openapi keine. Rechtlich zwingend ist:
  Die 2.782 Wikipedia-Texte bleiben CC BY-SA. (geo-10)
- **Keine Entitäts-Verankerung.** Keine der 4.539 QIDs steht im Markup, es gibt kein Wikidata-Item und 0 Links aus
  en.wikipedia. Common Crawl hat die Domain 2026 nie erfasst. Achtung: 43 QIDs hängen an 98 Orten, darunter
  Klassen-QIDs wie „mortuary temple“ an drei verschiedenen Tempeln. Ein ungefiltertes sameAs wäre falsch. (geo-06,
  offpage-04, tech-v02, geo-07, geo-08)
- **Trainings-Crawler holen nur den Sitemap-Index.** GPTBot (15×) und ClaudeBot (~54×) laden `/sitemap.xml`, aber nie
  eine Teil-Sitemap; bingbot holt alle 7 Teile. Bis 17.08. war die Sitemap eine flache Liste mit 7.394 URLs. Als
  Mechanismus ist das plausibel, bewiesen ist es nicht. (tech-v01, crw-08)
- **Öffentliche API halb brauchbar.** `/api/v1/stats` antwortet 500 (am 08.10. abends erneut geprüft; Ursache
  `public_v1.py:1031`). In der Suche steht der kuratierte Sacsayhuamán-Datensatz auf Platz 19 hinter 18 OSM-Dubletten.
  Die Ergebnisse haben kein `url`-Feld, openapi nennt „750K+“, und `/api/v1/research` gibt den Auftragstext „For a
  cosmological novel …“ aus. (geo-11)
- **Die Paper-Bibliothek driftet.** 17 Paper sind eindeutig ohne Archäologie (+5 Grenzfälle), darunter 7 der 10
  neuesten. 5 öffentliche Paper sind Recherche-Briefings „for a (cosmological) novel“ (index, follow, in der Sitemap).
  Zielkonflikt: In Google tragen Off-Topic-Paper 32 % der Research-Impressionen, aber 1 von 24 Klicks; bei ChatGPT-User
  machen sie 38 % der Paper-Abrufe aus. (geo-15, content-11, gsc-16, opp-03)
- **Rauschen im ausgelieferten Text.** „OFFLINE“ (Lyra-Status) steht neben jeder H1, die Quellen der De-Cordier-Story
  sind Auktionsportale, und Speculative-Stories zeigen das rohe Tag „lost_civilization“. (geo-18 gemessen, ungeprüft;
  tech-v07)

### 4.3 [Publikum] Zielgruppe und Verbreitung

- **Kein Rückkanal von YouTube.**
  - 0 echte Ankünfte über YouTube und 0 von fremden Websites in drei Wochen; Social bringt 6 Ankünfte.
  - 1 von 3.268 Videobeschreibungen nennt uns (Curious Being, seit 08.04. keine mehr).
  - Wir schicken den Kanälen auch keine „80 Klicks“: Das sind ~77 eingebettete Wiedergaben auf unserer Seite. Echte
    Klicks nach YouTube gab es 6 in 21 Tagen.
  - (stats-08, offpage-01, offpage-02, aud-10)
- **Eigene Kanäle ruhen.** YouTube seit 06.02.2024 (2,11 Tsd. Abos, off-brand), Pinterest seit 18.10.2023 (3.164
  Follower). Im Studio ist eine Episode (`baalbek-c5`) dreimal gerendert und nicht veröffentlicht. (aud-11, offpage-13)
- **Suchbesucher sehen eine Seite.** Nur 4,9 % der Story- und 3,1 % der Ortsseiten-Einstiege erreichen per internem
  Klick eine andere URL. Die Bausteine dafür existieren („Site mentioned“, „Show on the globe“, „Related stories“),
  stehen aber unter den Key facts bzw. am Seitenende. Paper-Einstiege: 1 von 31. (stats-04, measure-04, stats-10)
- **Die interne Suche findet nur Orte.** 24 von 88 Suchbegriffen liefen ins Leere, darunter „elongated skulls“ (4×),
  „the valley of kings, egypt“ (3×) und „ancient japan“. (stats-11 gemessen, ungeprüft)
- **Keine Bindung.** 2,4 % Rückkehrer, 6 Konten, ~1,7 echte Discord-Klicks pro Tag, Discord-Server 223 Mitglieder.
  (stats-12, offpage-15 ungeprüft)
- **Das Debatten-Format ist nicht mehr frei.** Ancient World Atlas bietet „Both sides, honestly told“ mit „Debate
  meter“ auf 293 Ortsseiten. Atlas Anatolia hat 354 Dossiers in 13 Sprachen, Evidenz-Labels und eine GEO-llms.txt.
  Keiner der beiden verknüpft Videos oder Creator; das bleibt unser Alleinstellungsmerkmal. (aud-05, aud-07)

### 4.4 [Messung]

- Vier Dashboard-Fehler treffen genau die SEO-Kennzahlen:
  - „human“ ist seit 04.10. um ~150 von 378 Sitzungen (~40 %) überhöht. Ursache: `story_open` und `paper_open` mit
    `method=landing`.
  - Die Scrolltiefe und `shallow_exit` sind auf Story- und Ortsseiten tot. Im Browser belegt: window-Listener, der
    Container scrollt.
  - `outbound_click youtube.com` zählt Inline-Wiedergaben, weil `defaultPrevented` nicht geprüft wird.
  - Der nginx-Block im Sources-Panel ist ~5-fach zu hoch, weil der Scraper 47.79/16 nicht herausgerechnet wird.
  - Dazu zählt „≥ 2 Seiten“ Reloads und erneute SERP-Klicks auf dieselbe URL mit; bei Story-Sucheinstiegen ist die
    Hälfte der zweiten Seitenaufrufe dieselbe Story.
  - Die Landing lädt kein `boot`, ihre Discord-CTAs sind blind, und dort fallen die meisten echten Discord-Klicks an
    (14 von 26).
  - (stats-02, stats-03, measure-01, measure-02, measure-04, stats-13)
- Mehrere Mess-Rezepte in Memory und Repo sind veraltet (§9.1). (gsc-13, crw-03, measure-05)

---

## 5 Was wir noch nicht nutzen

- **[SEO] Die Nachfrageliste als Arbeitsreihenfolge.** `scratch/demand/` enthält für alle 4.900 Orte Wikipedia-Nachfrage,
  GSC und Indexstatus. Daraus folgen der Recrawl (Soft-404-Seiten), die Dossiers (indexierte Null-Seiten) und die
  fehlenden Orte. (demand-01, demand-02)
- **[SEO] Die Prospector-Queue.** 11 der 38 fehlenden Orte im Scope liegen seit 15.09. als „new“ in der Queue, der
  Pantheon als „needs_decision“. Chaco Canyon steht fälschlich auf `out_of_scope`, weil `period_start` 1980 das
  Ausweisungsdatum des Parks ist. Choquequirao (P571 1536) und vermutlich Comalcalco fallen durch dieselbe Lücke.
  (demand-02, demand-03)
- **[SEO][GEO] Das Lyra-Material als Debatten-Dossier.**
  - 220 kuratierte Orte haben ≥ 1 indexierbare Story, 37 haben ≥ 5 und 16 haben ≥ 10.
  - Themen mit ≥ 25 Stories in der Überschrift: Giza 92–105, Göbekli/Taş Tepeler 66, Sphinx 38, Steinvasen/Präzision
    31, Hawara 29, Younger Dryas 26; knapp darunter Stonehenge, Sacsayhuamán und Osiris-Schacht.
  - Kein Wettbewerber verknüpft Behauptung, Video-Minute und Beleg.
  - (geo-04, content-05, aud-04)
- **[Publikum][SEO] Live-Tracker** für laufende Kontroversen. Das Material reicht für 2–3: Taş Tepeler, Hawara und ggf.
  die Giza-Scans. Die Nachfrage ist ereignisgetrieben (Karahan-Tepe-Spitze 5.259 Aufrufe/Tag gegen Median 278).
  (aud-06)
- **[GEO] Daten, die schon in der DB liegen:**
  - 4.539 QIDs für sameAs und identifier (≈4.441 eindeutig).
  - Lizenz, Autor und Maße für 3.808 Hero-Bilder, für ImageObject.
  - `youtube_url`, Kanal und Zeitmarke für VideoObject. Video-Rich-Results sind bei Zusammenfassungen fraglich, weil
    das Video nicht der Hauptinhalt ist.
  - (geo-06, tech-11, tech-14)
- **[SEO][GEO] Bing Webmaster Tools.** Auf der Seite liegt kein Bing-Token (BingSiteAuth.xml 404, kein msvalidate, im
  DNS nur google-site-verification). 20–23 % der Suchbesuche kommen nicht von Google, und ChatGPT-Suche wie Copilot
  stützen sich auf Bing. BWT ist die einzige kostenlose Backlink-Sicht. (stats-07, geo-16, offpage-10)
- **[SEO] Ereignisspitzen.** Troja hatte im Juli 737.331 Wikipedia-Aufrufe statt 88.634 im Juni, vermutlich wegen
  Nolans „The Odyssey“. Unsere indexierte Troja-Seite: 2 Impressionen in 90 Tagen. (demand-05, starke Folgerung)
- **[GEO] Kurze Antwortblöcke** (wer, wann, wie datiert, was ist belegt, was ist umstritten). Für 168 Fragen-Queries gab
  es 0 Klicks; Operator-Queries von Recherche-Agenten stehen auf Ø-Pos. 5,8. (gsc-15, starke Folgerung, ungeprüft)
- **[GEO] Datensatz-Listung.** Der Datensatz steht auf keiner Plattform (HF, Zenodo, OpenAlex 0), und das
  Dataset-JSON-LD hat keine `distribution`. Ein stabiles ID-Schema für eine Wikidata-Property existiert schon
  (8-Hex-Präfix, `/sites/x/{id}` → 301). (offpage-06, geo-12, offpage-07, geo-07)
- **[Publikum] Creator-Ökosystem.** 837 Videos mit Stories und Zeitmarken. Creator verlinken Patreon und Touranbieter,
  aber praktisch nie Referenzseiten; selbst der Megalithic Portal steht in nur 6 von 3.268 Beschreibungen. Erst nach dem
  Owner-Entscheid zu Erlaubnis und Video-Frames angehen (§8 E2). (offpage-02, aud-12, aud-08, opp-01)
- **[Publikum] Der eigene YouTube-Kanal** mit 2,11 Tsd. Abos und einer fertigen Studio-Pipeline. (aud-11, offpage-13)
- **[SEO] Feeds.** Es gibt kein RSS/Atom (10 Pfade liefern 404). Das ist billig, behebt aber kein Crawl-Nachfrageproblem.
  (crw-09, tech-17, offpage-11)
- Niedrig priorisiert:
  - Typ-Hubs nach Normalisierung der 86 `site_type`-Werte und Regionen nur für England und Peru, erst wenn die
    Länder-Hubs indexiert sind (content-08, aud-15).
  - Eine Seite „For teachers“ (offpage-16, Hypothese).
  - MCP-Server (geo-13, keine Nachfragemessung).
  - Personen-Seiten (offpage-12, content-10): nur „Louis de Cordier“ hat messbare Nachfrage (624 Impr./90 T.), und es
    geht um lebende Personen.

---

## 6 Potenzial und Fahrplan

Aufwand: **XS** < 1 h, **S** ≤ 1 Tag, **M** bis ~2 Wochen, **L** länger. Wer: **Code**, **Owner-UI**, **Inhalt**,
**Owner-Entscheidung**.
Gemeinsame Bremse: Google crawlt neue URLs kaum. Deshalb gilt überall: **bestehende, indexierte URLs aufwerten,
neue URLs nur anlegen, wo kein Ort passt.**

### 6.1 Sofort (je ≤ 1 Tag)

**S1 · Soft-404-Validierung und Indexierungsanträge** · [SEO] · Wirkung hoch · Aufwand S · Wer: Owner-UI
· gsc-04, tech-05, idx-01, aud-02, demand-01, gsc-02, gsc-08, idx-04
- **Was:** in der GSC die Validierung vom 05.09. prüfen und bei Bedarf neu starten. Danach „Indexierung beantragen“,
  ~10 pro Tag, nach der Arbeitsliste (Details in §7).
- **Warum:** ≈1.080–2.100 Ortsseiten und 35 der Top 100 nach Nachfrage sind nicht im Index. Google holt sie von selbst
  nicht nach (0 von 23 in 14 Tagen). Die Seiten bestehen den Render-Test.
- **Grenze:** Die Indexierung ist Voraussetzung, kein Traffic. 13 indexierte Flaggschiffe bringen trotzdem 0 Klicks
  (dafür W3). Einzelanträge bewegen einzelne URLs, nicht die Crawl-Nachfrage der Site.
- **Nachmessen:** nach 2–3 Wochen mit `scratch/index/idx_inspect_run.py` (gleicher Seed).

**S2 · Dashboard-Fehler beheben, vor dem Review ~26.10.** · [Messung] · Wirkung hoch für alle Entscheidungen · Aufwand S
· Wer: Code · stats-02, stats-03, measure-01, measure-02, measure-04, stats-01, stats-13
- **Was:**
  - `method=landing` wie `AUTO_SITE_OPEN_CONTEXT` behandeln (`pipeline/stats_analysis.py`, `Session.human`).
  - Scroll-Listener als Capture-Listener auf `document`, gemessen am `event.target` (im Browser als wirksam geprüft).
  - In `installOutboundClicks` (`analytics/boot.ts`) `if (event.defaultPrevented) return`.
  - `$server_protocol` ins `referral`-Logformat; Google-Referer über HTTP/1.x nicht als Ankunft zählen. Das trennt den
    Scraper zu 100 % bei 26 Fehltreffern unter 699 echten Ankünften.
  - `data-umami-event` auf die zwei Discord-CTAs der Landing.
  - Engagement als „andere URL per internem Klick“ statt „≥ 2 Seitenaufrufe“.
- **Warum:** Ohne diese Fixes misst das 30-Tage-Review 40 % Scheinmenschen, keine Lesetiefe und falsche
  YouTube-Abgänge.

**S3 · robots.txt: Teil-Sitemaps nennen** · [GEO] · Wirkung mittel (Test) · Aufwand XS · Wer: Code
· tech-v01, crw-08, geo-08, crw-14
- **Was:** in `ancient-nerds-map/public/robots.txt` die sechs Inhalts-Teil-Sitemaps (static, sites, countries,
  stories, research, articles) als eigene `Sitemap:`-Zeilen ergänzen. Den veralteten Kommentar „GPTBot fetched 13,017 URLs
  … more than Googlebot“ entfernen. `Disallow: /globe.html?` ergänzen. Sonst nichts sperren.
- **Warum:**
  - GPTBot und ClaudeBot holen nur den Index, nie die Teile.
  - bingbot, DotBot und Perplexity crawlen 1.885 `/globe.html?focus=`-URLs.
  - Eine Umstellung auf `#focus=` würde der dokumentierten Entscheidung in `constants/brand.ts:202–204` widersprechen.
- **Nachmessen:** zwei Wochen lang im nginx-Log zählen, ob 74.7.* und 216.73.* Teil-Sitemaps und Seiten abrufen.

**S4 · llms.txt korrigieren** · [GEO] · Wirkung niedrig bis mittel (Vertrauen, Recht) · Aufwand XS · Wer: Code
· geo-09, tech-18, qual-03
- **Was:**
  - Die Zahlen aktualisieren (4.900 Orte, 91 Länder, 2.182 Stories, 7.298 URLs).
  - Ehrlich angeben: „2.782 Beschreibungen sind wörtliche Wikipedia-Auswahl (CC BY-SA)“.
  - Die Autorenangabe korrigieren.
  - Die Story-Grenzen ehrlich benennen.
  - Die Lizenzzeile erst nach E3 anpassen.
  - Den API-Link auf openapi.json setzen.
  - Optional die Datei aus der DB generieren (S).

**S5 · Entitäts- und Bild-Schema** · [GEO][SEO] · Wirkung mittel · Aufwand S · Wer: Code · geo-06, offpage-04, tech-v02,
tech-10, tech-11
- **Was:**
  - Im Place-JSON-LD `sameAs` (Wikidata-URL und enwiki-Artikel aus `enwiki_title`, nicht die oldid-Revisions-URL) und
    `identifier` setzen, **nur für eindeutige QIDs (≈4.441)**. Die 43 geteilten QIDs (98 Orte) bleiben draußen.
  - `image` als ImageObject mit `license`, `creator`, `creditText`, `acquireLicensePage` und Maßen (Daten in
    `route.image`).
  - Auf der Startseite ein WebSite-Schema, das Organization-Logo als PNG.
  - `alternateName` auf wenige Hauptnamen deckeln (bis 251 Aliase pro Ort).
- **Orte im Code:** `api/routes/sites_html.py:327–341` und `:380–402`, `src/types/anRoute.ts:131`,
  `src/seo/meta.ts:270–283` und `:283`, `index.html:72` und nach `:102`.

**S6 · Bild-URLs kodieren** · [SEO] · Wirkung mittel · Aufwand S · Wer: Code · crw-13, tech-11
- **Was:** ein Kodier-Helfer in `pipeline/`, genutzt von allen 9 Erzeugern (`sites_html.py:184/:430`,
  `wiki_images.py:89/:305–306`, `lyra_tools.py:1273`, `static_exporter.py:599/:813`, `wiki_image_downloader.py:1225`).
  Dazu `thumbnail_url` in der API.
- **Warum:** 989 Hero-URLs mit Leerzeichen brechen in og:image, JSON-LD und `<img src>`.

**S7 · Öffentliche API** · [GEO] · Wirkung niedrig bis mittel · Aufwand XS–S · Wer: Code · geo-11
- **Was:**
  - `/api/v1/stats` reparieren: `public_v1.py:1031` liest `dict(result.tuples())`, richtig ist
    `{r.source_id: r.count for r in result}`.
  - In der Suche kuratierte Orte zuerst (`public_v1.py:559–562`), mit Feldern `url` und `wikidata`.
  - Im openapi-Text 1,76 Mio. statt „750K+“, dazu `license` und `contact` nach E3.
  - Ob `question` öffentlich bleibt, entscheidet der Owner (E11).

**S8 · Paper-Seiten** · [SEO][GEO] · Wirkung niedrig bis mittel · Aufwand S · Wer: Code · tech-09, geo-14
- **Was:** die Hero-Höhe reservieren (`PaperArticle.tsx:88–93`, `paper-article.css:99–105`) und den Artikel in
  `<main>` setzen (`ResearchPaperPage.tsx:141`). In der Bibliothek die Zahl der zitierten Referenzen statt „0“ bzw.
  „4.056 sources“ zeigen.

**S9 · VideoObject und nocookie** · [SEO] · Wirkung niedrig bis mittel · Aufwand S · Wer: Code · tech-14, aud-16,
content-10, gsc-12
- **Was:** ein VideoObject auf Story-Seiten (`meta.ts:206–238`, die Daten liegen im Payload) und `youtube-nocookie.com`
  (`InlineVideo.tsx:75`, `LyraChatModal.tsx:166–167`). Den Creator in Meta- und og:description nennen, nicht in den
  `<title>`.
- **Grenze:** Video-Rich-Results verlangen das Video als Hauptinhalt; bei Zusammenfassungen ist das fraglich.

**S10 · Ausschuss und Rauschen** · [SEO][GEO] · Wirkung niedrig · Aufwand XS · Wer: Inhalt und Code
· content-03, tech-v07, geo-18
- **Was:**
  - Die bekannten Junk-Stories über das bestehende Gate zurückziehen: 7858 „no substantive narration“, 5608
    „Monetization scheme“ sowie die Luke-Caverns-Dubletten 4747 und 4755 (Überschrift über die Creator-Biografie).
  - Eine Label-Map für `speculative_tag` (`StoryArticle.tsx:113`).
  - Die Lyra-Statusanzeige „OFFLINE“ erst nach der Hydrierung rendern.

**S11 · Härtung** · keine SEO-Wirkung · Aufwand XS–S · Wer: Code (nginx) · tech-v05, tech-v03
- **Was:**
  - `stats.ancientnerds.com`: eigene `robots.txt` (`Disallow: /`) und eigenes `access_log`. ClaudeBot fragt dort alle
    ~2 h ab und verfälscht die Bot-Statistik.
  - `server_tokens off`, HSTS ohne preload, CSP zuerst als Report-Only.
  - **Falle:** Jede Location mit eigenem `add_header` erbt die Server-Header nicht (Zeilen 111, 119, 130 … 412 der
    nginx-Konfiguration).

### 6.2 Wochen (2–8 Wochen)

**W1 · Story-Verifier reparieren und Bestand nachziehen** · [SEO][GEO] · Wirkung hoch · Aufwand M · Wer: Code (+ Inhalt
für die Abnahme) · qual-01, geo-03, content-03, aud-17, aud-01
- **Was:**
  - Der Verifier gibt Überschrift, Key facts und Text als Einheit zurück und übernimmt sie gemeinsam.
  - Key facts werden zu „Claims in the video“ mit Status (belegt, umstritten, widerlegt) und Zuschreibung („<Kanal>
    says“).
  - Der Text ist Prosa statt Tweet, ohne Emojis und ohne doppelte Faktenliste.
  - Den Bestand in Wellen mit Journal neu verarbeiten. Zuerst die indexierten Alt-Kanal-Stories und die von ChatGPT
    geholten.
- **Warum:** 27,5 % Fringe als Tatsache, 32,5 % Fehler oder Widerspruch. In einem Fall (Story 5878) führte die Korrektur
  den Fehler erst ein. KI-Suchen zitieren uns als Ausreißer („Ancient Nerds says 900 tons“).
- **Beide Lager:** Die Claim-Check-Rahmung („X says Y – what is established“) passt zu beiden Lagern. Behauptungs-Stories
  haben ohnehin die doppelte CTR (unverified 3,1 %, theory 2,0 %, general 1,2 %). Die Fringe-Nachfrage wird bedient,
  ohne Vertrauen bei KI-Assistenten zu kosten.

**W2 · Datenhygiene der Kopf-Orte (Schritt 0 für Dossiers)** · [SEO][GEO] · Wirkung hoch · Aufwand M · Wer: Inhalt (+
Code für den Matcher) · qual-04, geo-05, aud-09, opp-02, content-06, demand-04, content-16
- **Was:**
  - `period_start` und die Datierung der ~50 Zielorte einzeln prüfen (Wert, Methode, Quelle). Baalbek bekommt die
    römische Bauzeit, die Tell-Besiedlung als eigene Angabe.
  - Die 218 Stories auf 65 kuratierte Ziele (≤ 2 km) umhängen und die ≥ 30 Fehlzuordnungen lösen, journalisiert und nach
    ENRICHMENT_AUDIT.
  - „Cavernas de Marabar“ auf den gängigen Namen umbenennen.
  - Im Matcher eine Ähnlichkeitstoleranz zugunsten kuratierter Datensätze einführen (`site_identifier.py:857–862`,
    bisher nur Tiebreaker).
  - Die Doppelseiten (Knossos, Olympia, Pergamon, Abu Simbel …) nach E9 behandeln.
- **Warum:** Ohne diesen Schritt würden die Dossiers falsche Perioden zeigen und die Stories auf Dubletten verteilen.
  Erst danach das genaue `period_start` im HTML und im JSON-LD ausgeben.

**W3 · Debatten-Dossiers auf den bestehenden Kopf-Ortsseiten** · [SEO][GEO][Publikum] · Wirkung hoch · Aufwand M–L ·
Wer: Code + Inhalt (menschliche Abnahme je Seite) · aud-03, aud-04, aud-05, geo-04, content-01, content-05, content-14,
gsc-05, gsc-11, gsc-15, demand-01
- **Was:** Auf der bestehenden Orts-URL, nicht unter neuen `/topics/`-URLs, entstehen folgende Blöcke:
  - Kurzantwort oben: wer, wann, wie datiert, was belegt, was umstritten.
  - „Wie alt?“ mit Datierung, Methode und Quelle.
  - „Wer hat es gebaut?“
  - „Was sagen die Videos?“: Behauptungen mit Zeitmarke, Kanal und Status.
  - „Besuch“.
  - Alle Stories (paginiert statt 10) und die passenden Paper.
- **Reihenfolge:** Hawara, Göbekli Tepe/Karahan Tepe, Giza (Great Pyramid, Sphinx), Baalbek, Puma Punku/Tiwanaku,
  Sacsayhuamán. Danach nach der Nachfrageliste unter den indexierten Null-Seiten (Troja, Petra, Mykene). Höchstens die
  ~16–37 Orte mit ≥ 5 Stories, sonst entstehen dünne Seiten. Eigene Themen-URLs nur für ortslose Themen (Younger Dryas,
  Steinvasen/Präzision).
- **Warum:**
  - Die 16 Kopf-Ortsseiten bringen 426 Impressionen und 1 Klick, ihre Stories 8.207 und 168 (90 T.).
  - Wikipedia-Nachfrage je Ort 2.000–94.000 Aufrufe pro Monat.
  - Autocomplete: „is gobekli tepe real“, „how old is X really“, „who built X“.
  - Wettbewerber haben das Format, aber keine Videos und keine Frische.
- **Grenzen:** FAQ-Blöcke bringen kein Rich Result (seit 2023 nur Behörden und Gesundheit); sie dienen Lesern und GEO.
  Soft-404-Orte profitieren erst nach dem Recrawl (S1).
- **Nachmessen:** Klicks und Impressionen der Dossier-URLs, Position für „who built / how old / is X real“, Anteil der
  Cluster-Impressionen auf der Orts-URL.

**W4 · Silos verbinden** · [SEO][Publikum] · Wirkung mittel · Aufwand S–M · Wer: Code (+ Owner-Entscheidung für die
Startseite) · content-04, content-12, stats-10, idx-04, crw-01
- **Was:**
  - Ortsseiten verlinken ihre Paper.
  - Paper verlinken ihre Orte, Stories und verwandte Paper.
  - Journale verlinken ihre eigenen Stories.
  - Related stories nach gemeinsamem Ort statt nach Kategorie (`articles_html._related_stories`).
  - **Vorschlag:** die neuesten 3–6 archäologischen Paper wieder von einer oft gecrawlten Seite verlinken (Startseite
    oder Ortsseiten).
- **Warum:** 0 von 41 Papern verlinken Orte oder Stories, 0 von 29 Ortsseiten ein Paper. Paper sind der einzige
  Inhaltstyp, bei dem tatsächlich Links fehlen; seit dem 10.09. hängen sie nur noch an `/research/`. Story 7650
  (De Cordier, 1.103 Impressionen) zeigt als verwandt Puma Punku, Troja, Dinosaurier, Hopi und Wikinger.

**W5 · Weiterklick auf Story-Seiten** (Designvorschlag) · [Publikum] · Wirkung mittel · Aufwand S · Wer:
Owner-Entscheidung, dann Code · stats-04, measure-04
- **Was:** die vorhandenen Chips „Site mentioned“ und „Show on the globe“ sowie die verwandten Stories nahe ans Video
  bzw. über den Falz rücken.
- **Warum:** Story → Ortsseite liegt bei 1 von 657. Gemessen wird als interner Klick auf eine andere URL.

**W6 · Vertrauensseiten, Marke, Lizenz** · [GEO] · Wirkung hoch · Aufwand S–M · Wer: Owner-Entscheidung + Code + Owner-UI
· offpage-03, aud-13, offpage-05, geo-10, qual-03, content-17
- **Was:**
  - Eine indexierbare About-Seite und eine Methodik-Seite: Pipeline, Prüfschritte, gemessene Fehlerquoten,
    Korrekturweg, Gründer. Das Impressum bleibt noindex.
  - Das KI-Label behalten (Art. 50(4) KI-VO), aber erklären.
  - DAO-Spuren entfernen: `twitter:site`, Organization-`sameAs` auf das DAO-Medium.
  - README und openapi auf 1,76 Mio. bzw. 4.900 kuratiert angleichen, das GitHub-Profil bereinigen.
  - Eine Lizenzmatrix je Inhaltsart (E3) überall identisch ausgeben.
  - Den Startseitentext (E4) als Vorschlag behandeln.
- **Warum:** Such-KI: „Don't cite it“. Sechs widersprüchliche Lizenzflächen. Die Theo-Korrekturprotokolle sind ein echtes
  Transparenzsignal, aber nirgends erklärt.

**W7 · Fehlende gefragte Orte kuratieren** · [SEO] · Wirkung hoch · Aufwand M · Wer: Owner-Entscheidung + Inhalt
· demand-02, demand-03
- **Was:**
  - Die Prospector-Queue nach Wikipedia-Nachfrage abarbeiten (`scratch/demand/proposals_by_demand.csv`,
    `agg_inscope_candidates.csv`), jeden Ort einzeln nach ENRICHMENT_AUDIT.
  - Mit den 38 im Scope beginnen. Davon sind 11 schon „new“: Kolosseum, Karthago, Ephesos, Ninive, Mohenjo-daro,
    L'Anse aux Meadows, Çatalhöyük, KV62, Sanxingdui, Nan Madol, Mesa Verde.
  - Chaco Canyon, Choquequirao und Comalcalco neu bewerten.
  - Den Scope-Guard so ändern, dass bei P31 „archaeological site“ ein P571 nach 1500 kein Belegungsdatum ist.
  - Den Dedupe-Fehler beheben: „Troy“ steht als „new“ in der Queue, obwohl Q22647 kuratiert ist.
- **Warum:** 2,72 Mio. Wikipedia-Aufrufe pro Quartal ohne eigene Seite. Die Mittelalter-Regel bleibt unberührt
  (Hagia Sophia, Angkor, Great Zimbabwe bleiben draußen).

**W8 · 2–3 Live-Tracker** · [Publikum][SEO] · Wirkung mittel · Aufwand S–M · Wer: Code + Inhalt · aud-06
- **Was:** Taş Tepeler (66 Stories), Hawara (29) und ggf. die Giza-Scans (Khafre/Biondi + Osiris-Schacht), als datierte
  Chronik-Abschnitte der jeweiligen Ortsseite oder als indexierbare Archiv-Filteransicht mit `dateModified`. Nichts unter
  ~20 Stories anlegen (Gunung Padang 2, Steinvasen 6).
- **Warum:** Der Hawara-Cluster ist unser größter Themen-Cluster (4,4 % aller Klicks in 90 T.). Eine stabile URL sammelt
  die Signale, statt sie auf 27 kaum gecrawlte URLs zu verteilen.

**W9 · Titel- und Description-Experiment** · [SEO] · Wirkung mittel · Aufwand S · Wer: Code · gsc-07, tech-12, aud-01
- **Was:** lesbare Typ-Labels im Ortstitel (Label-Map für `meta.ts:311`), Story-Titel ≤ 65 Zeichen mit dem Kernbegriff
  vorn und in Claim-Check-Form, Descriptions ≤ 155 Zeichen mit eigener Leistung (Karte, Datierung, verknüpfte Videos).
  Mit den 25 Striking-Distance-Paaren aus `gsc.md` §5.2 beginnen und nach 4 Wochen die CTR vergleichen. Es ist ein
  Experiment, kein belegter Defekt.

**W10 · Einheitliche Suche** · [Publikum] · Wirkung mittel · Aufwand M · Wer: Code · stats-11
- **Was:** über Orte, Stories, Paper und Länder-Hubs suchen (Ländername führt zum Hub), mit Tippfehler-Toleranz für
  Mehrwortnamen. Die Null-Treffer-Begriffe monatlich als Inhaltslücken auswerten.

**W11 · KI-Ortstexte ohne Quelle prüfen** · [SEO][GEO] · Wirkung mittel · Aufwand M · Wer: Inhalt · qual-02
- **Was:** die 706 generierten Texte ohne Quellenmarke einzeln nach ENRICHMENT_AUDIT prüfen und unbelegte Sätze
  streichen. Neue Regel: jeder generierte Satz braucht eine Quelle.

**W12 · Paper-Bibliothek ordnen** · [GEO][SEO] · Wirkung mittel · Aufwand S · Wer: Owner-Entscheidung + Code + Owner-UI
· geo-15, content-11, opp-03, aud-14, offpage-14
- **Was:** eine eigene Rubrik für Paper ohne Archäologiebezug (E1). Die Roman-Briefings bekommen noindex oder eine
  eigene Rubrik. Bei den zwei Medium-Kopien den Canonical auf ancientnerds.com setzen (Owner, §7).

**W13 · Atom-Feed** · [SEO] · Wirkung niedrig · Aufwand S–M · Wer: Code · crw-09, tech-17, offpage-11
- **Was:** ein Feed der letzten 50 Stories, Paper und Journale mit `<link rel=alternate>`. Billig, nützlich für
  Aggregatoren und Discord; die Crawl-Nachfrage behebt er nicht.

### 6.3 Strategisch (Quartal)

**T1 · Crawl-Nachfrage-Experiment** · [SEO] · Wirkung hoch (Erkenntnis) · Aufwand M · Wer: Code + Owner-UI · idx-03
- **Was:** drei Gruppen mit festem Seed. 20 Kopfseiten werden aufgewertet und beantragt, 20 nur beantragt, 20 bleiben
  ohne Maßnahme. Nach 3 Wochen Index und Crawl vergleichen (Inspection + nginx).
- **Warum:** Nur so trennt man Qualität von Popularität als Ursache der Crawl-Bremse. Dazu kommt die GSC-Crawling-Statistik
  (§7).

**T2 · Creator-Rückkanal** (erst nach E2) · [Publikum] · Wirkung mittel, Ertrag unsicher · Aufwand M · Wer:
Owner-Entscheidung + Code · offpage-02, aud-12, aud-08, opp-01
- **Was:** Video-Begleitseiten als `noindex, follow`-Linkziele (keine 837 neuen Indexseiten) und eine UTM-Konvention für
  Creator-Links. Zuerst quellenaffine Kanäle ansprechen (Michael Button, Ancient Architects, The Prehistory Guys, Ed
  Barnhart, DeDunking).
- **Erwartung:** niedrig. Selbst der Megalithic Portal steht nur in 6 von 3.268 Beschreibungen. Mit „Karten nach
  Creator“ ehrlich bleiben: „Orte aus X' Videos seit <Datum>“, weil der Ingest nur neuere Videos erfasst (UnchartedX 20
  Videos, 13 Orte).

**T3 · Eigener YouTube-Kanal** · [Publikum] · Wirkung mittel · Aufwand M · Wer: Owner (Release-Gate) · aud-11,
offpage-13, gsc-09
- **Was:** das About bereinigen (§7), die Baalbek-Episode freigeben, ancientnerds.com mit `utm_source=youtube`
  konsequent verlinken.
- **Warum:** Die Zielgruppe ist per Definition auf YouTube, und Brand-Nachfrage gibt es kaum (41 Impressionen in 28 T.).

**T4 · Datensatz und Wikidata** · [GEO] · Wirkung mittel · Aufwand M · Wer: Owner-Entscheidung + Code · offpage-06,
geo-12, offpage-07, geo-07, offpage-08
- **Reihenfolge:**
  1. Lizenzmatrix (E3).
  2. Zenodo-DOI des kuratierten Datensatzes (GeoJSON existiert) mit `distribution` und `identifier` im Dataset-JSON-LD.
  3. Wikidata-Item mit offengelegtem Interessenkonflikt.
  4. Property-Vorschlag (Formatter `https://ancientnerds.com/sites/x/$1`).
- **Wirkung:** Entitätserkennung in Knowledge-Graph- und LLM-Pipelines, keine Wikipedia-Links. Theo-Paper nicht per DOI
  oder Scholar streuen, solange 71,4 % der Befunde reparaturbedürftig sind.

**T5 · Typ- und Regions-Hubs** · [SEO] · Wirkung niedrig bis mittel · Aufwand M · Wer: Code + Inhalt · content-08,
aud-15, content-09
- **Was:** erst `site_type` normalisieren, dann Typ-Hubs. Regionen nur für England (Grafschaften) und Peru (Cusco), per
  Punkt-in-Polygon, und erst wenn die Länder-Hubs indexiert sind. Die Nachfrage ist nur über Autocomplete und Wikipedia
  belegt, GSC bisher 151 Impressionen und 0 Klicks.

**T6 · Ereignis-Monitor** (Vorschlag) · [SEO][Publikum] · Aufwand S · Wer: Owner-Entscheidung + Code · demand-05
- **Was:** ein wöchentlicher Pageview-Lauf über die kuratierten QIDs. Sprünge über das Doppelte lösen eine Story oder ein
  Update der Ortsseite aus (`scratch/demand/pv_rest.py`).

**T7 · KI-Fragenpanel** · [GEO][Messung] · Aufwand S je Monat · Wer: Owner oder Session mit UI-Zugang
· Kritiker-Lücke, geo-13
- **Was:** 30 Publikumsfragen (`scratch/audience/ac.json`) monatlich in ChatGPT, Perplexity, Gemini und Claude sowie im
  Google AI Mode stellen und die zitierten Domains protokollieren. Ein MCP-Server erst, wenn dort Nachfrage sichtbar
  wird.

---

## 7 Aufgaben nur für den Owner

1. **GSC → Indexierung → Seiten → „Soft 404“.** Den Status der am 05.09. gestarteten Validierung ablesen. Steht sie auf
   „Fehlgeschlagen“ oder hängt sie, „Fehlerbehebung überprüfen“ neu starten. Auf dem Bucket „Seite mit Weiterleitung“
   **keine** Validierung starten, sie kann nicht bestehen.
2. **„Indexierung beantragen“**, ~10 pro Tag über ~10 Tage, in dieser Reihenfolge:
   1. `output/seo-audit-2026-10-08/scratch/final/request_indexing_worklist.csv`: 64 nicht indexierte kuratierte Orte,
      sortiert nach Wikipedia-Nachfrage. Pompeji, Osterinsel, Hadrianswall, Derinkuyu, Cahokia, Nazca, Uruk, Sphinx,
      Knossos, Pergamon … Zeilen mit Stadtartikeln (Sevilla, Pamplona, Córdoba, Kutaisi) nach hinten.
   2. Die Hubs Egypt, Italy, England, Türkiye, Germany, China und Russia.
   3. Archäologische Paper, die nicht indexiert sind (z. B. `the-egyptian-hard-stone-precision-debate`, das ChatGPT 14×
      holte).
   4. Die 3–5 Legacy-URLs mit den meisten Impressionen (z. B. `/site.html?id=493a3926…`, zuletzt gecrawlt 09.09.).
3. **GSC-Exporte (~10 min), ablegen unter `output/seo-audit-2026-10-08/owner/`:**
   - Crawling-Statistik 90 Tage, nach Zweck, nach Antwort und nach Dateityp.
   - Seitenindexierung mit allen Gründen als CSV.
   - Manuelle Maßnahmen, Sicherheitsprobleme, Entfernungen, Links-Bericht.
   - Diese Berichte datieren den Abriss vom 11.–17.09. und schließen eine Maßnahme wegen „scaled content“ aus oder ein.
4. **Bing Webmaster Tools:** prüfen, ob ein Konto per DNS oder GSC-Import besteht (auf der Seite liegt kein Token). Wenn
   nicht, per GSC-Import einrichten (Minuten). Danach Sitemap, Indexabdeckung, Backlinks und IndexNow-Statistik ansehen.
5. **Medium:** bei „Bosnian Pyramid“ und „Global Flood Myths“ in den Story-Einstellungen den Canonical auf
   ancientnerds.com setzen.
6. **Profile bereinigen:**
   - YouTube-About: „AI Art Community“ und den OpenSea-Link entfernen, auf ancientnerds.com verlinken, den
     Discord-Invite vereinheitlichen (Website `8bAjKKCue4`, YouTube `BAkFvbfpFZ`).
   - GitHub-Profil (Name mit „Ξ“, `twitter_username`).
   - Pinterest nur bei Bedarf (Domain unverifiziert, ruht seit 10/2023).
7. **DMCA-Lage:** in der Lumen-Datenbank im normalen Browser nach ancientnerds.com suchen und den GSC-Bericht
   „Entfernungen“ ansehen. Beides ist Voraussetzung für E2.
8. **SERP-Wahrheit:** 10 Kopfbegriffe inkognito auf google.com (US) mit AI Overview prüfen und notieren, wer rankt und
   wer zitiert wird: Göbekli Tepe, Puma Punku, Baalbek stones, Hawara labyrinth, Sacsayhuamán, Derinkuyu, Nazca Lines,
   Great Sphinx, Younger Dryas, Louis de Cordier.
9. **Datenschutz:** erledigt am 08.10. Die beiden lokalen Log-Kopien mit Besucher-IPs
   (`scratch/crawlers/logs/access_all.gz`, `scratch/crawlers/records.pkl`) sind gelöscht. Was bleibt, sind
   Googlebot-IPs und aggregierte Zählungen. Die Container-`/tmp` sind sauber.

---

## 8 Entscheidungen für den Owner

| # | Frage | Zahlen zur Abwägung | Empfehlung |
|---|---|---|---|
| E1 | Paper ohne Archäologiebezug (17 eindeutig, 5 Grenzfälle) und 5 Roman-Briefings | Google: Off-Topic-Paper tragen 660 von 2.085 Research-Impressionen (32 %), aber 1 von 24 Klicks, also 0,9 % der Impressionen und 0,1 % der Klicks der Domain (28 T.). ChatGPT-User: 34 von 89 Paper-Abrufen (38 %), Stargate führt mit 17. Die Such-KI nennt die Drift als Vorbehalt. | Eigene Rubrik statt noindex. noindex brächte in Google fast nichts, nähme die Seiten aber auch aus dem Bing-Index, aus dem die ChatGPT-Suche schöpft; der Gewinn an Themenautorität ist eine Hypothese. Roman-Briefings: noindex oder klar als Auftragsrecherche kennzeichnen. Bis dahin keine DOI-Streuung. |
| E2 | Creator-Politik: Erlaubnis oder Fair-Use-Haltung, Video-Frames als Seitenbild | 2.674 von 2.679 Story-Seiten zeigen einen 1280×720-Frame aus dem Video als Hero und og:image. `docs/creator-outreach-template.md` bittet um Erlaubnis, sagt „we never reproduce your … creative expression“ und regelt: „If a Creator Declines or Doesn't Respond → remove their channel“. Erwartbarer Linkertrag niedrig (Megalithic Portal: 6 von 3.268 Beschreibungen). Lumen nicht prüfbar. | Vor jeder Ansprache entscheiden und die Vorlage passend umschreiben (Link-Angebot statt Erlaubnisbitte oder umgekehrt); einen Opt-out-Weg festlegen. Sonst kann Outreach nach der eigenen Regel den Story-Bestand verkleinern. |
| E3 | Lizenzmatrix je Inhaltsart | Sechs widersprüchliche Flächen (llms.txt CC BY, Dataset und terms/imprint CC BY-NC-SA, Paper CC BY, Beschreibungen CC BY-SA, openapi keine). Die 2.782 Wikipedia-Texte müssen CC BY-SA bleiben; NC verträgt sich nicht mit ShareAlike. | Je eine Aussage für Wikipedia-Texte (BY-SA, zwingend), eigene Daten (Koordinaten, Metadaten), Stories und Paper; überall gleich ausgeben (S4, S7, W6, T4). |
| E4 | Markenauftritt: DAO-Handles und Startseitentext | `twitter:site @AncientNerdsDAO` auf jeder Seite, sameAs auf das DAO-Medium, YouTube „AI Art Community“, Startseite „questioning the mainstream narrative … copper chisels“. Such-KI: „Don't cite it“ (n = 4). Das Alt-History-Publikum ist aber unser stärkster Story-Traffic (71 % der Story-Klicks aus Alt-Kanälen). | Die DAO/NFT-Spuren entfernen (X-Handle umbenennen oder aus dem Markup nehmen). Den Startseitentext als Vorschlag neutral-neugierig fassen („we check the claims from both sides“). Das bedient beide Lager und kostet kein KI-Vertrauen. |
| E5 | Größe und Zeitpunkt des 410-Gates | 893 Stories antworten 410, die Owner-Angabe war 65. Sie binden 50 % des Googlebot-Story-Crawls (1.148 von 2.285) und 20,9 % aller Googlebot-Requests. 306 zurückgezogene Stories hatten in 28 T. noch 3.374 Impressionen. Begründungen: 460 inhaltlich, 366 leer, 67 Scope, 0 Dublette. | Die Gate-Größe bestätigen (kein Defekt). Das Gate künftig vor Veröffentlichung, Sitemap und IndexNow anwenden, damit keine neuen 410-URLs entstehen (im September 108). Keine weiteren Massenrückzüge bereits indexierter URLs ohne vorherigen GSC-Impressions-Check. 404 statt 410 bringt nichts. |
| E6 | Entfernkriterium `sitemap-legacy.xml` | Letzte volle Woche 1.216 Impressionen (5,1 %), fallend. Googlebot holt ~17 Legacy-URLs pro Tag, ein Volllauf dauert ~290 Tage. „Eine Woche 0“ ist erst in Monaten erreichbar. | Behalten. Als neues Kriterium etwa „Wochenanteil < 1 %“. |
| E7 | Designvorschläge | Startseite: 0 Paper-Links seit 10.09. Story → Ortsseite 0,15 %. /globe.html ist mobil als Phone-Gate indexiert (35 Wörter, keine H1). Die Navigation führt Journal und Research auf App-Shells statt auf die SSR-Hubs. Die Alias-Wand steht auf Ortsseiten vor dem ersten Satz. | Vorschläge, kein Muss: Paper-Block auf der Startseite (W4), Chips nahe ans Video (W5), H1 und zwei Sätze im Phone-Gate (`PhoneGate.tsx:12–16`), Nav-Ziele `/articles/` und `/research/` (`HamburgerNav.tsx:11,13`), Aliase hinter die Beschreibung. |
| E8 | Freigaben aus der Prospector-Queue | 38 Orte im Scope (2,72 Mio. Aufrufe im Quartal), 11 davon „new“, Pantheon „needs_decision“, 16 zweifelhaft (Große Mauer überwiegend Ming, Konstantinopel, Weltwunder ohne Ort u. a.). Chaco Canyon (24.846 Aufrufe) fälschlich `out_of_scope`. | Einzeln nach ENRICHMENT_AUDIT freigeben, mit den 38 beginnen. Die 16 zweifelhaften nach der geltenden Regel entscheiden. Chaco Canyon freigeben. |
| E9 | Doppelte kuratierte Seiten | 43 Artikel auf 98 Seiten. Bei Ollantaytambo hat eine Seite 266 Impressionen auf Pos. 54,5, die andere 13 auf Pos. 3,8. | Je Paar entscheiden: zusammenführen (301 + Alias) oder als Teilort abgrenzen, mit eigenem Titel und Link auf den Hauptort. Kein Massen-Merge. |
| E10 | Spekulative Stories indizieren? | Potenzial höchstens ~3.700 Impressionen und ~40 Klicks pro 28 T., und nur bei voller Indexierung, die nicht stattfindet. Schon die nicht spekulativen Stories zeigen 27,5 % unbelegte Fringe-Rahmung. | noindex beibehalten. Die Nachfrage über Dossiers abholen (W3). |
| E11 | Feld `question` in `/api/v1/research` | Gibt Auftragstexte wie „For a cosmological novel …“ aus; die Paperseite zeigt sie nicht. | Aus der öffentlichen Antwort nehmen. |
| E12 | Personen-Seiten | Nur „Louis de Cordier“ hat Nachfrage (624 Impressionen in 90 T.). Lebende Personen, KI-Text, 2–11 Stories je Person. | Nicht anlegen, oder höchstens 1–3 mit menschlicher Abnahme. |
| E13 | Übersetzungen | DACH 4,1 % der Klicks, deutschsprachige Queries ≈ 0; die 58 deutschen Umami-Besuche enthalten Gründer-Besuche. | Nicht übersetzen. |

---

## 9 Messung

### 9.1 Falsche oder veraltete Rezepte

| Rezept (wo) | Was falsch ist | Was gilt |
|---|---|---|
| „Umami sieht nur 43 %, alle Dashboard-Zahlen sind untere Schranken“ (MEMORY.md-Indexzeile; Kommentar zu `log_format referral` in `ancientnerds-nginx-config`) | Die Lücke war der Scraper 47.79.0.0/16 (seit 26.09., am 08.10. 511 von ~640 Google-Zeilen). | Umami/GSC 1,14, Umami/nginx bereinigt 1,03. Besucherzahlen aus Umami bzw. GSC nehmen. |
| Googlebot per `^66.249.` filtern (Memory `project-seo-soft404-popup-swap`, Indexzeile zu `project-crawl-budget-bundle-churn`) | Seit 27.09. kommt Googlebot zu ≥ 99 % aus 192.178.*; der Filter verfehlt 76 %. | Gegen `googlebot.json` (mit Abrufdatum) oder per rDNS verifizieren. |
| Menschen-Zahl aus `referral_report.py` (Memory `reference-referral-log`) | Sie enthält den Scraper (Chrome-UA). Für Google ist sie seit 26.09. 4–6-fach zu hoch; das Sources-Panel (nginx-Block) ist ~5-fach zu hoch. | Google-Referer über HTTP/1.x ausschließen (`$server_protocol` ins Format). |
| Menschliche Ankünfte aus dem `access.log` zählen | Googles Private Prefetch Proxy (1.329 Zeilen, `Sec-Purpose: prefetch`) sieht dort wie Menschen ohne JS aus. | Geofeed-Netze ausschließen oder mit `referrals.log` (`purpose`) verknüpfen. |
| „≥ 2 Seiten“ als Engagement und `Session.human` | Zählt Reloads und erneute SERP-Klicks; bei Story-Sucheinstiegen ist die Hälfte der zweiten Aufrufe dieselbe URL. | „Andere URL, per internem Klick erreicht“. |
| `outbound_click youtube.com` als Abgang zu den Kanälen | 77 von 83 sind Inline-Wiedergaben (Median-Abstand 7 ms zu `media_play`). | Nach dem Fix S2 ist es ein echter Abgang. Ältere Daten umdeuten. |
| Discord-Klicks aus dem API-Log (`bot=0`) | 114 von 140 `/goto/discord`-Abrufen sind Link-Crawler mit Browser-UA. | Mit JS-Nachweis ~1,7 echte Klicks pro Tag; Umami `discord_click` nach dem Landing-Fix. |
| ChatGPT-User-Abrufe als Lesenachfrage | 358 von 943 (37 %) sind ein stündlicher Startseitenabruf (315 IPs, nie < 1 min Abstand). | Organisch ohne „/“: ~40 pro Tag. |
| Bot-Statistik aus dem gemeinsamen `access.log` | `stats.ancientnerds.com` schreibt ohne `$host` ins selbe Log; die Hälfte der ClaudeBot-Abrufe gehört dorthin. | Nach Host trennen (S11). |
| URL Inspection: „unknown“ = nie gesehen, „Discovered“ = bekannt | `/sites/cyprus` wurde am 06.10. viermal mit 200 geholt und steht trotzdem auf „unknown“; Osterinsel und das hard-stone-Paper wechselten binnen Stunden. | Beide als „nicht gecrawlt/nicht indexiert“ zusammenfassen; Crawl-Aussagen mit nginx gegenprüfen. |
| Rückkehrerquote über Monatsgrenzen | Das Umami-Session-Salt rotiert monatlich (0 Session-IDs in September und Oktober). | Nur je Kalendermonat auswerten. |
| Wikipedia-Pageviews über Redirect-Titel | „Puma_Punku“ misst 453 statt 50.702 Aufrufe in 6 Monaten. | Den Artikeltitel aus den Wikidata-Sitelinks nehmen („Pumapunku“). |
| robots.txt-Kommentar „GPTBot fetched 13,017 URLs … more than Googlebot“ | Echter GPTBot: 169 Requests in 14 T., bingbot holt mehr Inhalte als Google. | Kommentar entfernen (S3). |

### 9.2 Vor dem 30-Tage-Review (~26.10.)

- Die Fixes aus S2 deployen und das Deploy-Datum im Review als Bruchkante führen.
- Werte vor dem Fix umdeuten:
  - „human“ seit 04.10. ~40 % zu hoch.
  - Reading-Panel und `shallow_exit` auf Story- und Ortsseiten wertlos.
  - Outbound youtube.com = Wiedergaben.
  - nginx-Sources ~5-fach zu hoch.
- Die Gründer-Besuche bleiben unfilterbar. Die kleinen Zahlen (Direkt-Einstiege, deutsche Locale) deshalb nicht
  überinterpretieren.

### 9.3 KPI-Rahmen für „go-to“

Monatlich mit fester Methode und festem Seed. Die Baselines stammen aus diesem Audit.

| Bereich | KPI | Baseline (Fenster) | Messweg |
|---|---|---|---|
| SEO | Non-Brand-Klicks Google | ~942 (973 − 31 Brand; 28 T.) | GSC final |
| SEO | Brand-Impressionen „ancient nerds“ | 41 (28 T.) | GSC Regex `(?i)ancient ?nerd` |
| SEO | Indexanteil Ortsseiten (Zufallsstichprobe) | 47/73 indexiert, 23/73 Soft 404 | `scratch/index/idx_inspect_run.py`, gleicher Seed |
| SEO | Top 100 Orte nach Nachfrage: Impressionen bzw. Anteil ohne Impression | 40 von 100 ohne Impression (90 T.) | `scratch/demand/` (`gsc_join.py`, `summary.py`) |
| SEO | neue Stories: in 14 T. von Googlebot geholt | 3 von 103 | nginx × DB, Googlebot gegen `googlebot.json` |
| SEO | 16 Kopf-Ortsseiten bzw. Dossiers | 426 Impr. / 1 Klick (90 T.) | GSC page |
| SEO | Bing: Indexabdeckung, Referring Domains | unbekannt | BWT, ab Einrichtung |
| GEO | ChatGPT-User organisch (ohne „/“) | ~40 Abrufe pro Tag | nginx, `chatgpt-user.json` |
| GEO | Menschen von KI-Assistenten | 5,7 pro Tag | Umami |
| GEO | Zitate im Fragenpanel (30 Fragen, 4 Assistenten + AI Mode) | noch keine; Proxy 2 von 25 im WebSearch-Werkzeug | T7 |
| GEO | Teil-Sitemap-Abrufe von GPTBot und ClaudeBot | 0 (14 T.) | nginx, 2 Wochen nach S3 |
| Publikum | interner Weiterklick nach Sucheinstieg | Story 4,9 %, Ortsseite 3,1 % | Umami, neue Definition |
| Publikum | Story → Ortsseite | 0,15 % (1/657) | Umami |
| Publikum | Video-Abspielquote der Story-Sucheinstiege | 7,9 % | Umami `media_play` |
| Publikum | Besuche über YouTube und `utm_source=youtube` | 0 (21 T.) | Umami |
| Publikum | Videobeschreibungen mit ancientnerds.com | 1 von 3.268 | SQL auf `news_videos.description` |
| Publikum | Rückkehrer je Kalendermonat | September 3,1 % | Umami |
| Publikum | echte Discord-Klicks / Konten | ~1,7 pro Tag / 6 | Umami nach dem Fix / Members-Panel |
| Qualität | Story-Defektquote (feste Stichprobe 40) | 32,5 % Fehler/Widerspruch, 27,5 % Fringe als Tatsache | Methode `scratch/quality/judge40.py`, quartalsweise |

---

## 10 Nicht geprüft

- **GSC-Berichte nur in der Oberfläche:** Crawling-Statistik nach Zweck, Seitenindexierung mit absoluten Zahlen,
  manuelle Maßnahmen, Sicherheitsprobleme, Entfernungen, Links, Core Web Vitals. Ebenso der Status der Soft-404-Validierung
  vom 05.09. (§7).
- **Ursache der Crawl-Bremse:** Qualität, Popularität und Umbausignale lassen sich mit API-Daten nicht trennen (T1).
- **Google AI Overviews / AI Mode** und echte Antworten von ChatGPT, Perplexity, Gemini, Copilot und Claude. Die
  GEO-Aussagen zu Zitaten beruhen auf dem WebSearch-Werkzeug (fremder Index, n = 1–4 je Frage).
- **Google-SERPs** für die Kopfbegriffe und die Rankings der Wettbewerber und der Medium-Kopien: curl ist blockiert, und
  WebSearch nutzt einen anderen Index. „Wikipedia gewinnt“ ist gefolgert.
- **Bing:** Indexstand, ob BWT per DNS oder GSC-Import schon existiert, Bing-Backlinks.
- **Reddit** (403), **X** (402), **Megalithic Portal** (403), **Lumen** (Anubis), kostenpflichtige Backlink-Indizes.
- **Augustvergleich der Crawler:** Die Logs vor dem 24.09. sind rotiert. Der Augustwert für GPTBot war UA-basiert und
  nannte mal 10, mal 15 Tage. Common-Crawl-Index CC-MAIN-2025-51 antwortete 502.
- **Suchvolumina:** Es gab kein Keyword-Tool. Wikipedia-Aufrufe und Autocomplete sind Proxys; 1,6 Mio. aggregierte
  Datensätze ohne QID und die Plätze 201–450 der Lückenliste sind ohne Handprüfung.
- **PageSpeed Insights und CrUX** (Kontingent bzw. API nicht aktiv). Die Feldwerte stammen aus Umami-RUM, die Paper-Werte
  aus kleinen Fallzahlen (n = 12 bzw. 24).
- **Barrierefreiheit** (Lighthouse/axe), **iOS-Safari-Scrollen** (nur Chromium getestet).
- **Qualität der Story-Quellen** als Domainklassifikation über 50 Stories (nur der Baalbek-Einzelfall).
- Wer den **stündlichen ChatGPT-User-Abruf** der Startseite auslöst; netzseitige Filter bei Contabo.
- Paper-Badge „Platinum/98“ und Aggregat 61,7 % (geo-14); Kanalzahlen der 497 spekulativen Stories (gsc-10).
- Ob es außerhalb des Repos Erlaubnis-E-Mails von Creators gibt.

---

## Anhang A · Verworfen und wesentlich korrigiert

**Verworfen**

| ID | Ursprüngliche Aussage | Befund |
|---|---|---|
| stats-14 | Eigene Kanäle tragen keine UTM. | Widerlegt. Discord-Bot (`api/services/discord_bot.py:52`), Shorts (`pipeline/video/shorts_render.py:456`) und Studio-Episoden (`pipeline/studio/package.py:49`) setzen UTM. Es fehlt der Verkehr, nicht die Markierung. |

**Widerlegte Teilaussagen und wesentliche Korrekturen**

| ID | Ursprünglich | Was gilt |
|---|---|---|
| gsc-02, tech-08 | Egypt, Italy, England, Türkiye „unknown to Google“; Hubs von der Startseite verlinken; England zu groß | Meist „Discovered“, „unknown“ ist unzuverlässig (Cyprus). Die Startseite verlinkt alle 91 Hubs bereits. Kleine Hubs sind genauso betroffen, die Größe ist nicht die Ursache. |
| gsc-03, crw-01 | Neue Stories „kaum entdeckt“; von Ortsseiten verlinken | 95–99 % sind von gecrawlten Seiten verlinkt, Ortsseiten listen die 10 neuesten Stories. Nicht Entdeckung, sondern Crawl-Nachfrage. Nur bei Papern fehlen Links. 29 von 274 beworbenen (nicht 369) Stories geholt. |
| gsc-04, tech-05 | ≈35 % Soft 404, Validierung starten | 31,5 % (22–43 %). Die Validierung läuft seit 05.09.: Status prüfen und neu starten. Google crawlt diese URLs nicht von selbst nach. |
| aud-02 | 5 + 1 Kopf-URLs beantragen | 9 Soft 404 unter den Kopfthemen, 35 unter den Top 100. Auch 13 indexierte Flaggschiffe bringen 0 Klicks, der größere Teil ist ein Ranking- und Qualitätsproblem. |
| content-01, gsc-05 | Null-Sichtbarkeit wegen Wikipedia-Texts | Bei 7 von 9 genannten Null-Seiten ist die Ursache Soft 404. Nur bei indexierten Seiten (Karahan, Tiwanaku, Troja …) ist der Text die plausible Ursache. Nan Madol liegt als Vorschlag vor. |
| crw-02 | 410-URLs aus Links und Sitemap entfernen; Dubletten-301 | Es gibt keine Verweise mehr. Keine der 893 Stories ist als Dublette ausgewiesen. Wirkung mittel statt hoch. |
| tech-07 | Legacy 8,9 %, Google-Canonical bleibt Legacy; lastmod auf Legacy setzen | Letzte Woche 5,1 %, fallend. Der Canonical springt beim Recrawl um. Die Wirkung von lastmod auf 301-Einträgen ist fraglich. |
| stats-01 | Zweite Nicht-JS-Population | Das ist Googles Prefetch-Proxy, kein zweiter Scraper. |
| stats-04 | 11 % der Sucheinstiege sehen eine zweite Seite | Interner Weiterklick auf eine andere URL: Story 4,9 %, Ortsseite 3,1 %. Die Bausteine existieren bereits. |
| stats-06, geo-01 | KI schickt den besten Traffic; +48 % KI-Ankünfte; 67 ChatGPT-Abrufe pro Tag | Effekt der Einstiegsseite; Umami +8 %; organisch ~40 pro Tag. |
| stats-08, offpage-01 (Zusatz) | Wir schicken den Kanälen 80 Klicks | ~77 Inline-Wiedergaben, 6 echte Klicks in 21 T. |
| stats-12, stats-13 | ~3 Discord-Klicks pro Tag; discord_click feuert fast nie (4 gegen 64) | ~1,7 pro Tag, die Lücke sind Crawler. `discord_click` funktioniert, blind ist nur die Landing. |
| crw-04, crw-05 | bingbot hat Googlebot überholt; KI-Crawler sind die größte Klasse | Gilt für Inhaltsseiten (281 gegen 164 pro Tag); bei den Requests liegen die Google-UAs knapp vorn. „Größte Klasse“ gilt nur nach Requests (YouBot, Amazonbot). Der belastbare Kern sind ~421 Inhaltsseiten pro Tag der echten KI-Suchcrawler. |
| crw-08, geo-08 | ClaudeBot 265; Common-Crawl-Rückgang; robots.txt nicht ändern; Bravebot minimal | ClaudeBot: die Hälfte gehört zum Stats-Host. Common Crawl hatte die Domain 2026 nie. Sitemap-Zeilen ergänzen (S3). „Bravebot“ sind überwiegend Scanner. |
| geo-03 | ≥ 124 Fringe-Stories; Periode aus der Site übernehmen | ≈600 (27,5 %). Die Periode kommt schon aus der Site; falsch ist der Site-Datensatz (Baalbek −7000). |
| geo-05 | period_start sichtbar machen | Bei den Flaggschiffen ist period_start selbst falsch: erst prüfen (W2), dann zeigen. |
| geo-09, tech-18 | Jeder KI-Bot holte llms.txt; 12.198 Sitemap-URLs | 0 Abrufe durch KI-Crawler; 7.298 Inhalts-URLs (die 12.198 enthalten 4.900 Legacy-301). |
| geo-10, tech-10 | Vier Lizenzangaben; ai_generated:false widerspricht „Claude Opus“; Organization ohne sameAs | Sechs Flächen. „selected“ heißt: Wikipedia-Text, von einem Modell ausgewählt, also kein Widerspruch. Die Organization hat sameAs, Place nicht. |
| geo-06, offpage-04 | sameAs aus 4.539 QIDs; Pleiades wo vorhanden | Nur ≈4.441 eindeutige QIDs (43 geteilt, teils Klassen-QIDs). Pleiades-IDs liegen nicht in `site_external_ids`. |
| tech-11 | Heros ≈570 KB; 1.717 kaputte URLs; keine Lizenzdaten | 18–616 KB, Median ≈240 KB. Kaputt sind 989 URLs mit Leerzeichen. Die Lizenzdaten liegen vollständig in der DB. |
| tech-12 | Site-Titel zu lang | Median 58 Zeichen; das Problem ist die Taxonomie-Formulierung. Die CTR-Lücke ist teils Position. |
| tech-14, aud-16 | Video nicht eingebettet, Lite-Embed bauen; Creator in den Title | Die Klick-Fassade existiert seit 21.08., der Creator steht sichtbar auf der Seite. Offen sind VideoObject, nocookie und der Creator in der Description (nicht im Title). |
| tech-15 | /news-archive/ nur im Footer; Shells leer | `/news-archive/` steht in der Navigation. Die Shells haben 85–158 Wörter im noscript-Block. Nur Journal und Research führen an den SSR-Hubs vorbei. |
| crw-14 | SiteCard auf #focus= umstellen | Widerspricht `constants/brand.ts:202–204`. Stattdessen `Disallow: /globe.html?`. |
| tech-16, crw-11 | CDN, Brotli, ETag, HEAD als Hebel | Die Origin-Renderzeit liegt bei 14–130 ms, kein Bot sendet HEAD. Ein CDN beschädigt die IP-basierte Bot-Messung. Niedrige Priorität. |
| gsc-10 | Spekulative Stories indexieren: ~5.600 Impressionen | Höchstens ~3.700 Impressionen und ~40 Klicks, nur bei voller Indexierung. noindex behalten. |
| geo-14 | „0 sources“ bei 9 Papern | Das trifft genau die 9 neuesten, die 28–147 Belege haben. Die älteren zeigen unplausible 1.880–4.056. |
| content-14 | Das Hawara-Paper belegt, dass das ausgewogene Format funktioniert | Das Hawara-Paper hat 0 Impressionen. Belegt ist das Format nur durch Baalbek (273) und Enuma Elish (424). |
| aud-05, aud-07 | Die neutrale Mitte ist frei; neue Atlanten sind KI-gebaut | Ancient World Atlas besetzt „both sides“ auf 293 Orten. KI-Herstellung ist nur für Atlas Anatolia belegt. |
| aud-06, content-05, geo-04 | Hawara = bester Traffic; 5–10 Tracker; 12–15 Hubs; 226 Orte; Giza 197 | Größter Themen-Cluster (4,4 % der Klicks). 2–3 Tracker, 6–9 Themen, 220 Orte (37 mit ≥ 5 Stories), Giza 92–105 Stories in der Überschrift. Barabar hängt an Wikidata („Cavernas de Marabar“). |
| aud-08, content-10, offpage-12 | Creator-Karten und Personen-Seiten | Die Direktnachfrage ist ≈ 0. „Alle Orte aus den Videos“ ist nicht lieferbar. Personen-Seiten wären dünn und betreffen lebende Personen. |
| aud-09 | Die Hälfte der Ortsnennungen umhängen | Umhängbar sind nur 218 Stories (65 Ziele), ≥ 30 sind falsch zugeordnet. Der Matcher bevorzugt kuratierte Datensätze bereits als Tiebreaker. |
| aud-10 | Suche 4.520, Bing 6,4 %, KI 3,3 % | Die Zahlen sind vom Scraper verzerrt. Umami: Discord 5, Facebook 2, YouTube 1 (Eigentest), Reddit 0. |
| aud-11, offpage-13 | 0 von 3 Studio-Episoden veröffentlicht | Eine Episode, dreimal gerendert. Pinterest hat 3.164 Follower. |
| aud-15, content-08 | Regionen und „near me“; Typ-Nachfrage aus GSC | „near me“ ist standortpersonalisiert, und es gibt nur 26 US-Orte. Die Typ-Nachfrage ist nur über Autocomplete und Wikipedia belegt. |
| offpage-02, offpage-06, geo-07, geo-13 | Creator-Rückkanal, Datensatz und Wikidata hoch; ID-Schema fehlt | Ertrag niedrig bzw. mittel. Das ID-Schema existiert. Wikidata erzeugt keine Wikipedia-Links. MCP ist ungemessen. |
| stats-15 | Deutsch ist Sprache Nr. 3, übersetzen | Gründer-Besuche sind enthalten, deutschsprachige Queries ≈ 0. Nicht übersetzen. |
| Kritiker-Lücke | Black Pyramid fehlt | Die Seite existiert und ist indexiert (39 Impressionen). |
| idx-06 (eingeordnet) | Site-lastmod entwertet (3.989 Änderungen am 04.–07.10.) | Die Änderungen waren echt (Hero-Bilder, Perioden; content-15). Ob Google lastmod deshalb abwertet, ist eine Hypothese; kein Sofort-Hebel. |

---

## Anhang B · Quellen

Alle unter `C:/PythonProjects/AncientMap/output/seo-audit-2026-10-08/`:

- Sammler: `gsc.md`, `stats.md`, `crawlers.md`, `technical.md`, `geo.md`, `audience.md`, `content.md`, `offpage.md`;
  Kritiker `critic.md`.
- Verifier: `verify-index.md`, `verify-measure.md`, `verify-quality.md`, `verify-tech.md`, `verify-opportunity.md`,
  `verify-demand.md`.
- Strukturierte Ergebnisse von Workflow 1: `scratch/main/wf1.json`.
- Rohdaten und Skripte: `scratch/<key>/`. Wichtig für Nachmessungen:
  - `scratch/index/idx_inspect_run.py` und `build_sample.py` (Index-Stichprobe mit festem Seed), `exposure.py`
    (Verlinkung neuer Stories).
  - `scratch/demand/curated_demand_all.csv`, `curated_top50_high_demand_low_visibility.csv`,
    `agg_inscope_candidates.csv`, `proposals_by_demand.csv` (Nachfrageliste).
  - `scratch/measure/` (Scraper- und Prefetch-Trennung, Weiterklick, Video-Quote, `scroll_probe.py`).
  - `scratch/quality/stories40_judgement.json`, `judge40.py`, `linkcheck.py` (Story-Stichprobe, Silos).
  - `scratch/tech/` (Bot-Status, mobiles Rendering, QID-Abfragen).
  - `scratch/final/request_indexing_worklist.csv` (Arbeitsliste „Indexierung beantragen“, erzeugt von
    `request_indexing_list.py` aus den Demand-Daten).
- Weitere Repo-Berichte: `docs/reports/2026-08-09-seo-audit.md` (Augustwerte), `docs/reports/theo-paper-defects-2026-10-04.md`.
