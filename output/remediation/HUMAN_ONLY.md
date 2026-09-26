# Was nur ein Mensch tun kann

Stand: 2026-09-25 (angelegt 2026-09-21). Auftrag: **alle 5.004 `ancient_nerds`-Sites prüfen und vom
Modell korrigieren lassen, mit Quellen und Belegen an jeder Korrektur** — seit deiner Anweisung vom
2026-09-23 („no DeepSeek any more - everything with Opus“) beantworten **Opus-Agenten** jede
Modellfrage über den Handoff; bis dahin war es deepseek-v4.1-flash. Diese Tabelle listet alles auf,
was davon **nicht** durch einen Agenten erledigt werden kann — mit Menge, Beleg und der Frage, die du
beantworten musst. Seit deinem Auftrag vom 2026-09-25 („keine Fragen mehr, autonom Empfehlungen
umsetzen“) setzt der Orchestrator den empfohlenen Weg ohne Rückfrage um; was hier offen steht, ist,
was auch dieser Auftrag nicht entscheiden kann.

**Stand des Schreibens (2026-09-25)** — alles in der Produktionsdatenbank, jede Schreibung mit
Journaleintrag, geprobter Anwendung und geprobter Rücknahme (Belege: `HANDOVER.md` Abschnitt 2,
`AUDIT_LOG.md`):

* **Phase 3** (2026-09-21/22): **994 Zeilen an 952 Sites** (596 `site_type`, 389 `period_start`,
  9 `country`; die erste Fassung dieses Absatzes nannte 1.022 Sites — das ist die *geplante* Zahl).
  Die **Opus-Nachprüfung** (2026-09-24/25, vier Runden, Regeln vor dem ersten Urteil versiegelt) hat
  die 934 von DeepSeek entschiedenen Zeilen neu beurteilt: **481 behalten, 453 zurückgenommen**
  (`journal-reversal-3`: 488 Zellen an 435 Sites), danach 13 Sites mit wörtlich belegtem richtigem
  Wert korrigiert (`wrong-both`, 17 Zellen). Abnahme heute: von den 994 tragen 499 noch den
  Phase-3-Wert, 495 sind durch spätere Lanes ersetzt, 80 geplante stehen unverändert — **0
  Abweichungen**.
* **Phase 4**: **984 Defekt-Sites** tragen eine neue Beschreibung aus einer festgenagelten
  Wikipedia-Revision mit Quellenzeile (986 geschrieben, 2 nach der Prüfung zurückgenommen; 1.968
  Zeilen, **0 Abweichungen**; `phase4_runner/MASS_RESULT.md` auf `wip/p4-pilot`). **Lane L** (die
  KI-Kennzeichnung der März-Texte, 4.003 Zeilen) wird gerade geschrieben.
* Weitere Lanes: Lücken-Lauf 17 Zeilen, Koordinaten 39 Zeilen an 13 Sites, ID-Reparaturen, Bild-Lanes,
  Scope-Entscheidungen 218 Zellen an 109 Sites (78 ausgeblendet, davon 19 Dubletten).
* **Live**: Push #1 (`8a957b4`, 2026-09-23).

Vor der ersten Welle: Sicherung `backups/2026-09-21_pre-write/` (655 MB) mit bestandenem Restore-Test
(`unified_sites` 1.759.676 = 1.759.676). Zu jeder Schreibung liegt eine Zeile im Journal
`remediation_change_log` mit altem und neuem Wert, und daneben je Chunk eine `ROLLBACK.sql`, die die
Umkehrung in einer Transaktion ausführt, prüft, dass jede Zeile wieder auf dem alten Wert steht, und
dann `ROLLBACK;` setzt — sie beweist die Umkehrbarkeit, statt sie auszuführen.

Belege: `snapshot/unified_sites.jsonl.gz` (eigene Zählung heute), `phase3_pilot/COST.md:141`,
`AUDIT_LOG.md` (Routing-Messung, mypy-Zählung, VLM-Kompetenz), `git log`.

## A. Entscheidungen, die den Lauf oder das Ausliefern freigeben

| # | Was nur du kannst | Warum kein Agent | Umfang | Was ich von dir brauche | Blockiert |
|---|---|---|---|---|---|
| A1 | **Push nach `main`** | Ein Push ist ein Live-Deploy (`ci.yml`). Unumkehrbar nach außen. | ~~97 Commits lokal~~ | **erledigt / freigegeben**: `122249d` und Push #1 `8a957b4` sind seit 2026-09-23 live; Push #2 (D5) ist durch deinen Auftrag vom 2026-09-25 freigegeben | - |
| A2 | **Die korrigierten Daten auf den Globus bringen** | Der Globus liest die DB live (`/api/sites/all`), jede Korrektur ist dort sofort sichtbar. Veraltet sind nur die statischen Dateien unter `/data/sites/` (Stand 2026-08-18, ausgeblendete Sites noch darin): sie erneuert der Export auf dem VPS (Phase-6-Runbook Schritt 3, vor Push #2). | 5.004 Sites betroffen | **nichts mehr** - der Orchestrator fährt den Export (AUDIT_LOG 2026-09-25, „Phase 6 follow-through prepared“, Item 3) | - |
| A3 | **Web-Recherche: Suchanbieter + Key** | Im Code existiert **keine** Suchroute (geprüft: kein `*SEARCH*`/`SERP`/`TAVILY`-Zugriff). Ein kostenpflichtiger Key ist Zugang **und** Kosten — beides deine Sache. | betrifft alle 5.004 Sites | ~~entschieden 2026-09-22: MiniMax~~ — **überholt**: seit 2026-09-23 alles mit Opus; die Remediation sucht nicht (Phase 4 läuft mit `--searches-off`, kein MiniMax-Client). Such-Pilot (2026-09-23) und Sitelink-Pilot (2026-09-24) sind an ihren versiegelten Schwellen gescheitert: die **7.761 unbelegbaren Felder bleiben unbelegbar**, bis es eine vertrauenswürdigere Quelle gibt (Denkmallisten, Grabungsberichte; nicht gebaut) | - |
| A4 | **Cron-Mailadresse (`MAILTO`)** | Der Aufräum-Cron hat kein `MAILTO`; ein fehlgeschlagenes Backup meldet sich niemandem. | 1 Zeile Crontab | deine Adresse | kein Lauf, aber Sicherheit |
| A5 | **Offsite-Kopie** | Das Repo (`.git` = 35 G) liegt auf derselben Maschine. Ein Ausfall der Maschine nimmt Code **und** Verlauf mit. | 1 Entscheidung | wohin kopieren (Ziel/Medium) | Sicherheit |
| A6 | **`video-assets/prod-db.env`** | Unbekannte Zugangsdatei; Inhalt kann ich nicht lesen (Policy) und darf es nicht. | 1 Datei | sagen, ob sie für den Lauf gebraucht wird — der Remediation-Lauf braucht sie nicht; gebraucht wird sie für den Nachtrag der 16 alten Shorts ins Ledger (B1/B2 Punkt 11) | Shorts-Ledger |
| A7 | **`mypy api/` Altbestand** | 93 Typfehler waren **vorbestehend**, nicht aus dieser Arbeit. ~~CI-Gate kann dadurch rot sein.~~ Das stimmte nie: CI prüft ohne die Projekt-Abhängigkeiten (`ci.yml:118,136`) und endet mit Exit 0, vorher wie nachher. | ~~93 Fehler~~ → 0 | **erledigt 2026-09-26 (WE2, Branch `wip/we2`)**: mit dem Repo-venv (mypy 1.19.1) 93 → 0, auch mit mypy 2.3.1 0; dabei zwei echte Fehler behoben (remove-image: 500 nach erfolgter Entfernung, `52d37fa`; `/ask` in Thread oder Sprachkanal: Fehlermeldung statt Antwort, `c6b58ff`) und der Discord-Mock der Testsuite entfernt (`7e6d0e5`). Runbook: `docs/procedures/CODE_AUDIT.md`, „Type check: `mypy api/` in two configurations“. Offen als Folgeschritt (braucht dein Go, weil Gate/CI): den abhängigkeitsbewussten Lauf in den Pre-Push-Hook oder in CI heben; bis dahin nach jedem Merge, der `api/` berührt, das Runbook fahren. Beleg: AUDIT_LOG 2026-09-26 „A7“ | - |

## B. Sites, bei denen der Lauf dir eine Entscheidung vorlegt (Menge kommt aus dem Lauf)

| # | Was nur du kannst | Warum kein Agent | Umfang (gemessen) | Was ich von dir brauche |
|---|---|---|---|---|
| B1 | **Namens-/Koordinaten-Fälle** | Ein Wikidata-Name ≠ gespeicherter Name kann ein **Alias** sein — das ist eine Projekt- und Sprachfrage, keine Faktenfrage. | ~~285 Sites~~ — die 285 aus `COST.md:141` sind **reine Koordinatenfälle**; die Alias-Frage betrifft **631 Namensbefunde** (T01). Stand 2026-09-23: siehe Abschnitt „B1/B2 — was die Daten entschieden haben“ | **fast alles mechanisch entschieden** — offen: 46 Namen lesen, ~~1 Freigabe (9 Koordinaten)~~ (geschrieben 2026-09-23, dazu Welle 2 mit 4 Sites), 5 verdächtige Links hinter passenden Namen, Einzelfälle unten |
| B2 | **Land bei grenzwertiger Lage** | `lat/lon` außerhalb des beanspruchten Landes: Grenzfluss, Insel, Gebietsreform — topologisch richtig, inhaltlich falsch. | **117 Sites** (T02), mechanisch eingeteilt: siehe Abschnitt „B1/B2 — was die Daten entschieden haben“ | offen: 2 Länder (Weg: mechanische Lane), ~~1 Umkehr~~ (erledigt 2026-09-23, `journal-reversal-1`), `Baltic Sea`, ~15 Koordinaten ohne zweiten Zeugen |
| B3 | **Quelle für Sites ohne Textroute** | Braucht eine Quelle, die kein automatischer Endpunkt liefert. | **17 Sites** ohne Wikipedia/Prosa-Route; 385 ohne enwiki, davon 368 über `source_url` erreichbar; **42 Sites ohne `source_url`** | Quelle nennen oder „keine Quelle möglich" |
| B4 | **Foto-Auswahl (Stichprobe)** | Der Bildprüfer ist **über-inklusiv** bei `site_photo` (gemessen) — nur Augen entscheiden, ob ein Foto die Site zeigt. **2026-09-25: die Opus-Kalibrierung C1 (939 Fragen, Schwellen vorher versiegelt) hat keinen Auslöser bestanden** — T-kind Nicht-Foto-Präzision 0,836 (< 0,90), T-X1 Präzision 0,515 (< 0,85), T-X2 0,125, T-X3 0,47; T-strict nicht auswertbar, weil die Augen-Labels `vlm_pilot/LABELS.jsonl` **fehlen** (nur `LABELS.template.jsonl`). Damit schreibt keine Vision-Stufe; die schon angewandten Bild-Korrekturen bleiben. Beleg: AUDIT_LOG 2026-09-25 „gallery calibration C1 with Opus“, `gallery_audit/calibration-2026-09-25-opus/ADMISSION.json` | Stichprobe der 200 geprüften Bilder + Neuzugänge | die Augen-Labels (`vlm_pilot/LABELS.jsonl`, deine 40-Kachel-Stichprobe) — ohne sie bleibt die Vision-Stufe zu |
| B5 | **Stil-/Rubrikgrenzfälle** | „Legend says …", „among the most famous" — Fehler oder erlaubter Ton? Das ist eine Redaktionsfrage. | 3–4 Fälle je Prüfrunde | Regel: Fehler oder nicht |
| B6 | **Löschungen** | Der Plan verbietet `DELETE`. Wenn eine Site ganz weg soll, ist das deine Entscheidung. | unbekannt; **ausgeblendet** (kein `DELETE`, `scope_status = retired`): 78 Sites per scope-e4, davon 19 Dubletten, angewandt 2026-09-25 (`be5d6c5`) | Einzelfall-Freigabe — die 19 Dubletten sind unter deinem Auftrag vom 2026-09-25 ausgeblendet; offen: Banias / Caesarea Philippi (B1/B2 Punkt 2) |
| B7 | **72 zurückgehaltene Zeilen** | Der Prüfer hat sie freigegeben, aber seine eigene Begründung trägt die Korrektur nicht (z. B. „der gespeicherte Wert ist nicht widerlegt", „der gröbere Typ widerlegt den feineren nicht"). Ich schreibe sie **nicht** — lieber eine Zeile zu wenig als eine unbelegte Zeile in der DB. | **72 von 481** geplanten Zeilen, Liste mit Zitat: `logs/_write_apply/HOLDS.md` | **entschieden 2026-09-21: weglassen** |
| B8 | **4 Zeilen, die die Grenzprüfung abgelehnt hat** | Der Name passt zu einem anderen Ort derselben Schreibweise, die Koordinaten liegen woanders: Lamay (`Mexico→Peru`), San Claudio (`Mexico→Spain`), Soura (`Türkiye→India`) — und Jaffa Gate (`Israel→Palestine`), eine politische Linie, die die Koordinaten nicht entscheiden. | 4 Zeilen | **entschieden 2026-09-21: keine davon schreiben** |
| B9 | **Schreibweise Nordirland** | Die DB hält 1.052 `England` + 118 `Wales` + 83 `Scotland` + **4 `Northern Ireland`** gegen **genau ein** `United Kingdom` — die Konvention des Datensatzes ist das Landesteil. Der Prüfer schrieb 3 Zeilen auf `United Kingdom`; geografisch richtig, aber eine zweite Schreibweise für denselben Ort. | **26 Zeilen** (3 geschrieben, 22 aus dem Zensus, 1 weiterer Treffer) | **entschieden 2026-09-21: `Northern Ireland`** — meine erste Vorlage war falsch begründet, mit der Messung erneut gefragt |
| B10 | **Politische Grenzfälle aus dem Zensus** | Zypern 14, Krim 9, Kosovo 2, Golan 2, Palästina 2 — die Datei `countries.geojson` sagt etwas anderes als der Datensatz, und die Datei ist keine politische Instanz. | **29 Zeilen**, Liste: `logs/_country_mismatches.txt` | **entschieden 2026-09-21: so lassen** |
| B11 | **Geschriebene Zeilen, die die Regeln vom 23.09. heute nicht schrieben** | Zwei neue Schreiber-Regeln (nach dem gescheiterten Such-Pilot) auf die 994 schon geschriebenen Zeilen angewandt, nur gemessen, nichts geändert: (1) Die **Widerspruchsregel** — der Prüfer schrieb `REFUTED: NO`, seine eigene Begründung nennt aber eine scheiternde Hälfte — hielte **77** Zeilen zurück. Nach drei Lesungen sagen davon 60–62 wirklich „gespeicherter Wert nicht widerlegt" oder „Vorschlag widerlegt", also dieselbe Klasse wie B7 (dort: weglassen); rund 10 sind Fehlalarme, deren Satz weiter unten für die Schreibung argumentiert (Presa-Tusiu, Annaghmare, Chacamarca, La Almoloya, Apollonia, Ashley, Court Hill, Erebuni, Asclepieion of Athens, Pen Dinas); 5–8 sagen beides. (2) Die **Bucket-Regel** — eine `period_start`-Änderung innerhalb des Buckets des alten Werts ist kein Fehler — hätte **170 der 389** geschriebenen `period_start`-Zeilen nicht geschrieben. Beide Gruppen stehen unverändert in der DB. | **77 + 170 Zeilen**, je mit Schlüssel, altem/neuem Wert und Prüfer-Begründung: `logs/review_holds/WRITTEN_HELD_BY_PHRASE.md` und `logs/review_holds/WRITTEN_SAME_BUCKET.md` (erzeugt mit `tools/measure_review_holds.py`, Befehl im Kopf des Skripts) | ~~je Gruppe oder je Zeile: behalten oder zurücknehmen~~ **erledigt**: die 77 hat das Re-Review entschieden (45 zurückgenommen, 32 behalten; `journal-reversal-2`, angewandt 2026-09-23); von den 170 sind 12 unter diesen 77 und 158 unter den 934 Zeilen der Opus-Nachprüfung (entschieden, Rücknahmen in `journal-reversal-3`, angewandt 2026-09-25) |
| B12 | **Zurückhaltungen durch vier Formulierungen, die sich nachweislich geirrt haben** | Die Widerspruchsregel hält künftig (Gap- und Suchlauf) jede Zeile zurück, deren Prüfer-Begründung eine scheiternde Hälfte nennt. Vier ihrer 18 Formulierungen haben auf den geschriebenen Zeilen Fehlalarme gezeigt: „neither half holds" **4 von 7**, „the stored value is not contradicted" **4 von 9**, „the reason fails" 1 von 4, „does not show the stored value wrong" 1 von 10. Solche Zeilen werden nicht geschrieben, aber ihre Ablehnung trägt den Vermerk `hand-read before it counts as refused (HUMAN_ONLY.md B12)` — sie sind keine erledigte Ablehnung. | je Lauf: die Ablehnungen `reviewer-why-names-a-failing-half` mit diesem Vermerk | Regel bestätigen: Handlesung, und geschrieben wird eine solche Zeile nur mit deiner Freigabe |
| B13 | **Die 21 „beide falsch“-Zeilen ohne Beleg** | Die Opus-Nachprüfung hat bei 42 Zeilen gesagt: gespeicherter und geschriebener Wert falsch, mit einem Vorschlag. Geschrieben wird ein Vorschlag nur, wenn ein maschinell gefundenes wörtliches Zitat über diese Site ihn nennt: **13** sind so korrigiert (`wrong-both`, 17 Zellen, angewandt 2026-09-25). Von den **29 gelisteten** sind 8 schon anders erledigt (Wichqana und Sidi Said endgültig behalten; die fünf Nordirland-Zeilen und Witham Shield von einer anderen Lane) — **21 bleiben für dich**, ihre Zellen tragen heute den Wert vor Phase 3. | **21 Zeilen**: 8 Richter uneinig (Nine Stones, Chanhudaro, Altar of Athena Polias, South Stoa I, Alvastra Pile-Dwelling, Choquequirao, Península de Kola, Pampas Gramalote); 8 ohne Zitat, das den Wert wörtlich nennt (Holyhead Mountain Hut Circles, Aquae Calidae, Carteia, Lalibela, Cave of Aurignac, Palaestra at Delphi, Stoa Poikile, Cnidian Treasury); 5 nur in Text über etwas anderes belegt (Nine Ladies Stone Circle, Gårdstånga, Maa Palaeokastro, Argura, Boeotian Treasury). Liste mit Grund und Vorschlag: `output/remediation/mechanical_wrong_both/SKIPPED.jsonl`; AUDIT_LOG 2026-09-25 „the wrong-both correction lane“ | je Zeile: den richtigen Wert mit Quelle nennen, oder „so lassen“ |

## B1/B2 — was die Daten entschieden haben (2026-09-23)

Auftrag: „die Empfehlungen umsetzen“ (Block „B - owner cases“ der Restarbeitskarte vom 2026-09-22).
Umgesetzt als deterministischer Klassifikator `scripts/remediation/bcases/` mit Beleg je Site
(`output/remediation/bcases/*.jsonl`, Zählung in `COUNTS.json`). **In die Produktion wurde nichts
geschrieben**; alles Schreibbare liegt als geprüfter Plan bereit. Grundlage: frischer Nur-Lese-Export
der 5.004 Sites, Wikidata-Namen aller 4.515 verlinkten Objekte, Wikidata-`P625` samt Quellenangabe und
die Koordinaten der englischen Wikipedia-Artikel (Aufrufe mit dem Projekt-User-Agent). OpenStreetMap war
von dieser Maschine aus nicht erreichbar (Overpass setzt die Verbindung zurück) und ist deshalb **kein**
Zeuge.

**B1 Namen (631 Namensbefunde aus T01):**

| Ergebnis | Anzahl | Was passiert |
|---|---|---|
| gespeicherter Name ist ein Name des verlinkten Objekts (Label, Alias oder Sitelink in irgendeiner Sprache: 354; gleich ohne Gattungswörter: 50; beschreibende Form: 67; Transliteration: 37) | **508** | der **Name** bleibt, kein Schreibvorgang — aber ein passender Name beweist den **Link** nicht: bei **72** davon ist der Link für sich verdächtig (Gattungsbegriff 4, mit anderen Sites geteilt 36, Objekt > 5 km entfernt 35; Feld `link_suspect` in `names.jsonl`). Sie sind **nicht** in Welle 2 und nicht geschrieben — Kandidaten für eine spätere Recherche-Welle, 5 davon unten für dich |
| der Name passt nicht, und der Wikidata-Link selbst ist falsch (Gattungsbegriff wie Q309 „history“: 21; geteiltes Eltern-/Geschwisterobjekt: 43; Objekt ohne Koordinate: 8; Objekt > 5 km entfernt: 5) | **77** | 18 davon hat die erste Reparaturwelle schon korrigiert (angewandt 2026-09-23, 26 Zeilen, heute nachgelesen: 0 Abweichungen). Die übrigen **59** einzeln recherchiert → **Welle 2: 12 Sites / 13 Zeilen geplant**, nicht angewandt (`qid_repair/wave2/`, Vorabprüfung gegen Produktion: 0 Abweichungen); 47 bleiben unverändert, jede mit Begründung |
| Name weder Wikidata-Name noch Transliteration, Objekt in der Nähe | **46** | **Lesen** (19 an einer Ortschaft verankert, 27 an einer Site) |

Von den 47 unverändert gelassenen Links: 24 Sites haben schlicht kein eigenes Wikidata-Objekt, 3 Einträge
sind Sammelbegriffe (Giants' Graves, Milecastles, Runestones of Sweden), 2 haben den **richtigen** Link,
aber einen falschen Punkt (Castle of Kirkûk 24 km, Roman Temple Qsarnaba 23 km), **5 haben den richtigen
Link, weil eine zweite kuratierte Zeile dieselbe Stätte ist** (Ancient Amathunta/Amathus,
Tel Hermal Fort/Shaduppum, Ñustahispana/Ñusta Hispana, zweimal 39 Bridge Street Chester, der Lykische
Grab-Eintrag/Amyntas Rock Tombs) — Dublettenkandidaten, 2 widersprechen sich selbst (Ramesses III Temple:
Name und Punkt Karnak, Beschreibung Medinet Habu; Rocca San Felice: Ort vs. Mefitis-Heiligtum), und
**11 haben einen Kandidaten, der die 1-km-Regel nicht beweisen kann** (ohne `P625` oder knapp außerhalb:
La Cobata, Tombs of the Nobles, Temple of Amun, House of Aion, Lakkos, Clachtoll Broch, Sonnentempel des
Niuserre, Porta Nord, Cocoraque Butte, Minoan Modi, Petroglyphen von Arpa-Uzen).

**B1/B2 Koordinaten (477 T01-Koordinatenbefunde + 11 weitere aus B2 = 488):** Ein Punkt wird nur
versetzt, wenn **zwei unabhängige Zeugen** (Wikidata-`P625`, Koordinaten des englischen Artikels)
innerhalb der Toleranz übereinstimmen (1 km, nach unten durch die Wikidata-Genauigkeit begrenzt) und der
gespeicherte Punkt außerhalb liegt. Zwei Zeugen zählen **einmal**, wenn

* `P625` als aus der englischen Wikipedia importiert belegt ist,
* einer der beiden der andere ist, **gerundet oder abgeschnitten** auf das Raster, in dem seine Ziffern
  stehen (Nachkommastellen, ganze Bogensekunden oder -minuten): Castro of Santa Trega hat im Artikel
  41.8927, -8.8698 — den Wikidata-Punkt 41.89275, -8.869808 auf vier Stellen gekürzt; Taq Kasra hat im
  Artikel 33°05'37", 44°34'51" — den Wikidata-Punkt auf ganze Sekunden gerundet; egal aus welcher
  Wikipedia `P625` importiert wurde,
* oder beide **derselbe Punkt** sind: näher als eine Bogensekunde (31 m), als ein Schritt ihres Rasters
  oder als die Wikidata-Genauigkeit (Petroglyph Beach: beide in Juneau; Temple of Atargatis: 8 m).

Die erste Fassung (2026-09-23 früh) zählte ein Paar erst unter 5 m Abstand als einen Zeugen; eine
Nachprüfung fand darin Rundungskopien. Mit der Regel oben fallen **8 der 17** damals geplanten
Versetzungen auf „offen“ zurück (El Kab, Bülövqaya, Khao Sam Kaeo, Eridu, Taq Kasra, Temple of Atargatis,
Sialkot Fort, Castro of Santa Trega). Bei Wikidata-Objekten mit mehreren Koordinaten gilt jetzt die
bevorzugte (`preferred`), nicht die erste. Museumsobjekte bekommen den Fundort (`P189`) — aber nur, wenn
der gespeicherte Punkt am Museum liegt.

| Ergebnis | alle 488 | davon die 285 |
|---|---|---|
| **versetzen** — Plan fertig, nicht angewandt (Calakmul 907 km, Yenikale 840 km, Guyaju 80 km, Zempoala 27 km, Melgunov Kurgan 21 km, Halamata 10 km, Iskanwaya, Las Médulas, Pamukkale) | **9** (27 journalisierte Änderungen: `lat`, `lon`, `geom`) | 5 |
| gespeicherter Punkt = Punkt des Wikipedia-Artikels, nur Wikidata weicht ab — bleibt | 98 | 69 |
| verlinktes Objekt kann nicht für den Punkt sprechen (Ortschaft/Region 115, Linie/Fläche 33, von mehreren Sites geteilt 30, anderer Name 32) — bleibt | 210 | 99 |
| offen: nur ein Zeuge (102), beide Zeugen sind einer (52), Zeugen widersprechen sich (9), kein Zeuge (7), einer stützt den gespeicherten Punkt (1) | 171 | 112 |

Der Plan (`output/remediation/bcases/coords_plan/`) schreibt je Site drei journalisierte Änderungen über
`apply_remediation_change()` — auch `geom`, weil es keinen Trigger gibt und die Umkreissuche auf `geom`
rechnet. Vorabprüfung gegen Produktion heute (nach der Nachprüfung): **27 Zeilen, 0 Abweichungen**.
Knappster Fall: Yenikale, die beiden Zeugen liegen 34 m auseinander — knapp über einer Bogensekunde und
keine Rundung des jeweils anderen, zählt also zweimal. Pergamonaltar bleibt in Pergamon (Fundort-Regel),
Tayma Stones bleiben offen (Wikidata nennt weder Fundort noch Koordinate).

**B2 Land (117):** 25 politische Linien (B10: so lassen) · 45 Küste/Insel/Grenze oder grenzüberschreitend
(so lassen; neu dabei die Felsbilder von Côa und Siega Verde — ihre eigene Beschreibung nennt Portugal
**und** Spanien, eines allein zu schreiben wäre falsch) · 4 schon richtig `Northern Ireland` ·
22 Irland→Nordirland (**alle 22 inzwischen geschrieben**, UK-Lane) · 5 falsches Land: 3 geschrieben,
**2 offen** (Achladia Deutschland→Griechenland, Delphinion Griechenland→Türkei; Weg: eine mechanische
Länder-Lane, noch nicht gebaut) · 3 falsche Koordinate + 12 „braucht Zeugen“: davon 1 versetzt
(Yenikale), der Rest offen · 1 kein Land (`Baltic Sea`).

**Dubletten:** 20 echte Paare (beide Namen sind Wikidata-Namen desselben Objekts, < 2 km) — der Plan
schätzte ~8. Überlebensregel: mehr Content-Links, dann mehr Quellen, dann ältere Zeile, dann die kleinere
ID (reiner Gleichstandsbrecher; bei 7 Paaren entscheidet er). Die Liste für die Scope-Lane:
`output/remediation/bcases/DUPLICATES.jsonl` (`loser_id`, `survivor_id`, `evidence`, **19** Zeilen, keine
Kette). **Zurückgehalten** (`DUPLICATES_HELD.jsonl`): Banias (Syrien) / Caesarea Philippi (Israel) — eine
Stätte, 290 m, aber auf den beiden Seiten der Golan-Linie, die du in B10 so gelassen hast; welche Zeile
bleibt, entscheidet ein Land, und das ist deine Frage, nicht die der Scope-Lane. Dazu 13 Punkte, auf denen
36 Sites übereinander liegen (`stacked.jsonl`) — keine Dubletten, sondern Platzhalterkoordinaten.

**Was nur du entscheiden kannst:**

1. ~~**Die 9 Koordinaten schreiben?**~~ **Erledigt 2026-09-23**: geschrieben (27 Zeilen, 0
   Abweichungen), dazu Welle 2 mit einem dritten Zeugen aus dem Netz (Aziz Dheri, Kephala Kea, Jordbro,
   Dwasieden; 12 Zeilen). FIELD_CONTRACT §4.6 verbietet automatische Koordinatenänderungen; beide
   Wellen erfüllen deine Regel „zwei unabhängige Zeugen“ in der strengen Form oben.
2. **Dubletten ausblenden:** ~~Darf E4 `retired` (Grund `duplicate_of:<uuid>`) für die 19 Verlierer
   genutzt werden?~~ **Erledigt 2026-09-25**: die 19 sind per scope-e4 ausgeblendet (`be5d6c5`), unter
   deinem Auftrag vom 2026-09-25 („keine Fragen mehr, autonom Empfehlungen umsetzen“) - B6 verlangte
   die Freigabe je Site, die Liste nennt jede einzelne mit Beleg (`bcases/DUPLICATES.jsonl`). **Offen:**
   Banias / Caesarea Philippi: welche Zeile, und damit welches Land (B10)?
3. **`Baltic Sea`**: welches Land (oder keines) für eine Stätte in internationalen Gewässern?
4. **Ahin Posh Tape** — die **Umkehr ist erledigt** (2026-09-23, `journal-reversal-1`: Land wieder
   `Afghanistan`). **Offen: der Punkt.** Gespeichert ist 33.668, 70.955 (in Pakistan), aus Wikidata
   Q4695118, das den Stupa bei Jalalabad mit einem pakistanischen Dorf vermengt. Die Zeugen (am
   2026-09-25 abgerufen und maschinell geprüft): der englische Artikel 34.412045, 70.45213;
   Errington 2017 (nach Ball und Gardin 1982) 34°24′N 70°27′E, „c. 2km south of Jalalabad“ - aber
   das ist der Artikel-Punkt auf Bogenminuten gerundet, also **kein zweiter unabhängiger Zeuge** (1.354
   m auseinander); Pleiades 59662 liegt 24 km daneben. Alle drei legen die Stätte **rund 95 km vom
   gespeicherten Punkt**, bei Jalalabad - der gespeicherte Punkt ist falsch, aber die Zwei-Zeugen-Regel
   trägt keine Versetzung, deshalb ist nichts geplant. **Deine Frage** (FIELD_CONTRACT §4.6): den
   Artikel-Punkt schreiben? Beleg: AUDIT_LOG 2026-09-25, „the wrong-both correction lane ... and Ahin
   Posh Tape's coordinates“, Abschnitt „Ahin Posh Tape's coordinates“.
5. **Verdächtige Links hinter passenden Namen** (aus den 72): „Milefortlet - Hadrians Wall“ →
   Q1568283 „milecastle“, „Dolmens of Sardinia“ → Q101659 „dolmen“, „Nuraghes of Sardinia“ → Q688292
   „nuraghe“ (jeweils der Gattungsbegriff, derselbe Fehler, den die Wellen 1 und 2 reparieren),
   „Asklepion, Kos“ → Q731841 „Asclepeion“ (geteilt mit „Asklepieion - Pathos“ auf Zypern) und
   „The Temple of Artemis“ — gespeichert in Griechenland bei 40.78, 24.72, verlinkt und beschrieben als
   der Tempel in Ephesos, 388 km entfernt. „Themistoclean Wall“ → „walls of Themistocles“ ist ein
   Fehlalarm des Kleinbuchstaben-Tests (ein bestimmtes Objekt).
6. **Lesen, kein Rechnen mehr möglich:** 46 Namen (N7), 11 Link-Kandidaten ohne 1-km-Beweis,
   2 widersprüchliche Einträge (+ Tikal aus Welle 1), 5 Dublettenkandidaten aus der Link-Recherche, 171
   offene Koordinaten (Liste mit Grund in `coords.jsonl`).
7. **Chiapa de Corzo / Zoque Culture Archaeological Zone** (2026-09-25, nur gelesen): nach den Daten
   **dieselbe Stätte**, aber **nicht** von der Dublettenregel gedeckt - deshalb nicht in
   `DUPLICATES.jsonl` und nicht in der Scope-Lane. Belege: die beiden Punkte liegen **7,4 m**
   auseinander (16.702978, -93.004036 / 16.703006, -93.004100); beide Zeilen haben dasselbe
   Vorschaubild (`Mound_1.JPG`); beide Beschreibungen erzählen dieselbe Stätte (Zoque-Hauptort,
   70 Hektar, das 2010 in Mound 11 gefundene Grab mit rund 4.000 Stücken aus Jade, Perlmutt und
   Bernstein, die E-Gruppe); der zweite `source_url` von Chiapa de Corzo - vor der Aufteilung durch
   `2026-09-23_source-url-split-wave4`, Journalzeile 32153 - war der englische Artikel
   `Chiapa_de_Corzo_(Mesoamerican_site)`, also genau der `source_url` und `enwiki_title` der
   Zoque-Zeile, und der gehört zu **Q4384315**, dem Wikidata-Objekt, das die Zoque-Zeile trägt.
   Warum die Regel nicht greift: (a) Chiapa de Corzo (`24aa135d-4714-47f5-96c0-d58f0bc04b6f`) trägt
   **kein** Wikidata-Objekt - Welle 4 hat ihr Q4384315 gerade deshalb nicht gegeben, weil die
   Zoque-Zeile es schon trägt; beide Regeln (Scope-Lane Regel c, `bcases` DUP) verlangen, dass beide
   Zeilen dasselbe Objekt tragen. (b) Selbst mit dem Link wäre es nach der Regel keine Dublette,
   sondern „PART-OF“: „Chiapa de Corzo“ ist das englische Label von Q4384315, „Zoque Culture
   Archaeological Zone“ ist **kein** Name des Objekts (Labels, Aliase, Sitelinks aller Sprachen,
   heute abgerufen: u. a. „Zona Arqueológica de Chiapa de Corzo“, „Chiapa de Corzo (Mesoamerican
   site)“). Nach beiden Überlebensregeln bliebe die Zoque-Zeile (`ed186ea9-9ed1-415d-828b-97d9f21401d2`:
   3 Content-Links, 20 Bilder, Wikidata- und enwiki-Link) und Chiapa de Corzo würde ausgeblendet
   (0 Links, 0 Bilder, kein Link) - dann trüge die bleibende Zeile den Namen, den Wikidata **nicht**
   kennt. **Deine Frage:** eine Stätte? Wenn ja: Chiapa de Corzo mit `duplicate_of:ed186ea9…`
   ausblenden (E4, wie die 19) und die Zoque-Zeile in „Chiapa de Corzo“ umbenennen - oder
   umgekehrt die Zoque-Zeile ausblenden und ihre Bilder/Links/IDs an Chiapa de Corzo hängen (das
   verschiebt Zeilen, also ein eigener Plan). Ein „ja“ mit der Richtung genügt; die Zeile kommt
   dann als 20. Eintrag in `DUPLICATES.jsonl` mit diesem Beleg.
8. **Lokale Kopien gelöschter Commons-Dateien** (2026-09-25, nur gelesen): Die Liveness-Lane hat
   am 23.09. sechs Bildzeilen ausgeschlossen, deren Commons-Dateien gelöscht sind (fünf als
   Urheberrechtsverletzung, eine aus anderem Grund; Dedan, Stadion Olympia, Stoa des Eumenes,
   Dionysostheater, Chesterfield). Keine Seite zeigt sie mehr - aber die Dateien liegen weiter auf
   dem VPS unter `public/data/images/wiki/<kürzel>/` und sind per URL abrufbar
   (`/data/images/wiki/9a9a0dca/hero.webp` antwortet 200). Dedans Vorschaubild zeigte noch auf diese
   Datei; der Chunk `thumb-repoint-2026-09-25-001` hat es am 2026-09-25 geleert (angewandt, Dedan hat
   kein lebendes Bild mehr). Die Dateien selbst liegen weiter auf dem VPS: die Bild-Lanes löschen nie
   Dateien (Design Eintrag 7). **Deine Frage:** sollen die sechs Dateien vom Server?

9. **Elf Namensschlüssel auf sechs Lyra-Sites** (Phase 6 Punkt 2, 2026-09-25, nur gelesen): Auf
   den 5.004 `ancient_nerds`-Sites weicht **kein** `name_normalized` vom Postgres-Schlüssel
   `left(lower(unaccent(name)), 500)` ab. Abweichend sind 11 Alias-Zeilen von sechs Radar-Sites
   (Quelle `lyra`: Yap 4, Charnwood Forest 2, Doggerland 2, North Sentinel Island, Roopkund Lake,
   Cerutti Mastodon site) - von Lyras Wikidata-Alias-Schreiber mit Pythons `normalize_name`
   gebildet (der Schreiber ist repariert, `370babf`). Eine exakte Suche nach diesen Namen findet die
   Site nicht; die unscharfe Suche schon. Die Journal-Lanes schreiben nur `ancient_nerds`-Zeilen.
   **Deine Frage:** dürfen sie diese 11 `lyra`-Zeilen schreiben (dann erweitert der Orchestrator die
   Name-Key-Lane um die Quelle `lyra`), oder bleiben sie?
10. **Die Abnahme ist versiegelt** (Phase 6 Punkt 6): `output/remediation/acceptance/PROTOCOL.md` -
    60 frisch gezogene geschriebene Sites (Seed 20260925, ohne Pilot- und Zwischenstichproben), je
    Feld ein unabhängiger Opus-Richter, auf jeden Fehlerbefund ein zweiter, 10 eingeschleuste
    Kanarienvögel. **Bestanden** nur mit 0 bestätigten schweren Fehlern, höchstens 3 von 60 Sites
    mit irgendeinem bestätigten Fehler und 0 Fehlern der sechs Maschinenprüfungen; ungültig, wenn
    weniger als 9 der 10 Kanarienvögel gefunden werden. Gezogen wird erst nach dem letzten Schreiben.
    **Wenn du eine Schwelle anders willst: jetzt, vor dem Ziehen** - danach ist sie fest.
11. **Shorts-Ledger** (Phase 6 Punkt 5): Die Tabelle `site_shorts` existiert (Migration 0021, seit
    23.09. angewendet) und ist leer. Die 16 Shorts, die vor ihr gerendert wurden, trägt
    `scripts/backfill_site_shorts_ledger.py` nach - dafür braucht es die Zugangsdatei
    `video-assets/prod-db.env` (A6). Nach den neuen Kartentexten (Phase 5) sprechen diese 16 den
    alten Text; das Gate S13 lässt sie nicht durch. **Deine Frage** (Shorts-Projekt, nicht Phase 6):
    neu rendern oder zurückziehen?

## D. Phasen 4 und 5: Beschreibungen und Kartentexte (Stand 2026-09-25: Phase 4 geschrieben, Lane L läuft, Phase 5 offen)

Entwurf: Eintrag [6] in `logs/design_texts_images_2026-09-22.json`. Die Texte werden von Code aus
Sätzen einer festgenagelten Wikipedia-Revision zusammengesetzt; das Modell wählt nur Satz- und
Span-Nummern. Geschrieben wird erst nach Push #1, in Schritten zu 100 Sites, jede Zeile mit Journal.
**Phase 4 ist durch** (2026-09-24/25): 984 Defekt-Sites tragen ihre neue Beschreibung, jeder Schritt
mit 0 Abweichungen abgenommen (`phase4_runner/MASS_RESULT.md` und AUDIT_LOG „Phase-4 mass run“, beide
auf Branch `wip/p4-pilot`).

**Entschieden seit 2026-09-23** (je mit Beleg; nicht wieder öffnen):

* **„Nur Defekt-Sites“** (2026-09-23): Phasen 4/5 schreiben nur die Sites mit nachgewiesenem
  Textfehler (`SCOPE4.json` v1, 1.623 Sites); alle anderen behalten Beschreibung und Karte. Der
  Schreiber verweigert jede andere Site (`outside-defect-scope`, ohne Schalter). AUDIT_LOG 2026-09-24,
  „The owner's defect scope“.
* **„T8 nur berichten“** (2026-09-24): die Abdeckung (T8) hält den Lauf nicht mehr an, sie wird
  berichtet (Massenlauf: 933 von 1.321 Spur-W-Sites = 70,6 %); T1-T7, T9 und T10 bleiben harte
  Schwellen. `PILOT_RESULT_3.md`, Abschnitt „Owner decision“.
* **„Alle kennzeichnen“** (2026-09-24): Lane L kennzeichnet **jeden** März-KI-Text, nicht nur die des
  Scopes (4.003 Zeilen geplant). AUDIT_LOG 2026-09-25, „Lane L marks every March-AI text“.
* **Dein Auftrag vom 2026-09-25** („keine Fragen mehr, autonom Empfehlungen umsetzen“): darunter die
  19 Dubletten-Ausblendungen (B1/B2 Punkt 2) und Push #2 (D5).

| # | Was nur du kannst | Warum kein Agent | Umfang | Was ich von dir brauche | Blockiert |
|---|---|---|---|---|---|
| D1 | **Push #1: Kennzeichnung und Namensnennung ausliefern** | Ein Push ist ein Live-Deploy (A1). Er muss **vor** der ersten Schreibung live sein, damit keine Seite ohne ihren Hinweis ausgeliefert wird. Er enthält: die Zeile unter der Beschreibung, die Provenienz-Felder der API, die Entfernung des 10-Site-Zitat-Seeds aus `api/main.py` (alle 10 tragen den Schlüssel, lesend geprüft am 23.09.), die Lizenzzeilen in Disclaimer und `terms.html`, den Satz-Splitter. Sichtbar ändert sich vor der ersten Schreibung nichts - gerendert wird nur, wo Provenienz existiert. | 1 Push | **erledigt 2026-09-23**: Push #1 `8a957b4` live (CI grün, api/api2 auf `8a957b45`, `terms.html` live) | - |
| D2 | **Wortlaut der Zeile unter der Beschreibung** | Rechtstext (CC BY-SA 4.0 §3(a), EU AI Act Art. 50). Entwurf, übernommen aus dem Design: `Text: Wikipedia – '<Titel>' (revision of <Datum>), CC BY-SA 4.0 · sentences selected and shortened by an AI system · source →` (bei übersetztem Text: `· translated by an AI system ·`). Für KI-geschriebenen Text (Übersetzung, Umformulierung, Altbestand vom März) steht zusätzlich die bestehende Fußnote `AI-generated text · images from the original sources · always verify with the sources.` | 1 Zeile + 1 Fußnote | **entschieden 2026-09-23: Entwurf ok** | D1 |
| D3 | **Satz in Disclaimer und `terms.html`** | Rechtstext. Entwurf: „Site descriptions reproduce and shorten text from Wikipedia under CC BY-SA 4.0; each links its exact source revision." - dazu grenzt der Disclaimer CC BY-NC-SA 4.0 auf Stories, Journals und Dokumentation ein, und der Wikipedia-Eintrag nennt 4.0. Achtung: für übersetzte (T), umformulierte (R) und alte März-Texte (L) trifft „reproduce and shorten" nicht wörtlich zu; die Seiten selbst sagen es je Site richtig. | 2 Dateien | **entschieden 2026-09-23: präzise Fassung** - „Site descriptions that carry a source line reproduce, shorten or translate text from the linked source revision (Wikipedia: CC BY-SA 4.0); the line states how an AI system was involved." (wahr ab dem Push und nach jeder Schreibung) | D1 |
| D4 | **SEO-Risiko zur Kenntnis nehmen** | ~~Rund 4.400~~ Mit dem Defekt-Scope tragen **984** SSR-Seiten Wikipedia-Wortlaut (Duplicate Content; Stand 2026-09-25). Die Pilot-Schreibung war am 2026-09-24. Gegenmittel: Auswahl und Kürzung je Site, eigener Kartentext, strukturierte Daten (`isBasedOn`, `license`), korrektes `lastmod` aus dem Journal. 14 Tage nach der Pilot-Schreibung prüfe ich die Pilot-Kohorte mit `scripts/gsc_report.py` (inspect) und berichte - das blockiert nichts. | Hinweis | „gelesen" | nichts |
| D5 | **Push #2: Kartentexte** | Die Karten-Datei wird bei jedem API-Start in die DB übernommen. Deshalb eine Sitzung, in dieser Reihenfolge: Backup-Drill, Schreibung der Karten mit Journal, Datei byte-gleich aus der DB neu erzeugen, **sofort** Push #2. Datei vor der DB zu pushen ist verboten (Boot-Import ohne Journal). Wenn CI rot wird und kein Deploy kommt: Rücknahme über `revert4.py` und `git revert`. | 1 Sitzung (mit dem Defekt-Scope nur die Karten der Scope-Sites) | ~~die Zusage, dass du am Ende der Sitzung sofort pushst~~ **freigegeben 2026-09-25** durch deinen Auftrag „keine Fragen mehr, autonom Empfehlungen umsetzen“: der Orchestrator fährt die Sitzung und pusht sofort (Phase-6-Runbook Schritt 4) | alle Kartentexte |
| D6 | **Sites ohne Quelle (Spur 0) und die Halteliste** | Was kein Artikel und keine freie Quelle trägt, bleibt beim alten Text; das entscheidet der Lauf, nicht ein Agent. | **gemessen 2026-09-25**: `phase4_runner/runs/mass-2026-09-25/HOLDS4.jsonl` (Arbeitsbaum `wip/p4-pilot`, 909 Zeilen): **620 Sites** behalten ihre Beschreibung, u. a. 267 ABSTAIN des Auswählers, 103 ohne Suche (Kandidaten der Spuren T, R und B3; die Suche ist aus), 78 V14, 35 `scope-pending`, 29 ohne Quelle, 27 V9, 24 V6; **265 Karten** zurückgehalten (V10 162, zu kurz 122). Dazu **19 Sites mit zu frischer Wikipedia-Revision** (jünger als 48 h): der Lauf versucht sie selbst erneut, frühestens ab 2026-09-26T21:30Z | Sichtung; je Site „so lassen" oder Quelle nennen (wie B3) | nichts |
| D7 | **Alttexte ohne beweisbare Herkunft** | Ein zurückgehaltener Text, der dem Stand vor März (`d4526691`) gleicht, bekommt **keine** KI-Kennzeichnung - seine Herkunft ist nicht beweisbar. Liste: `logs/_write_apply_p4l/*/UNCLAIMED.jsonl` (Arbeitsbaum `wip/p4-pilot`). | **gemessen 2026-09-25**: **17** (9 gleich `d4526691`, 8 nicht im Snapshot) | Sichtung | nichts |
| D8 | **876 statt 904 ungegroundete Kartentexte** | Du hast „die 904“ entschieden, aber keine Datei listet diese 904 Sites; die Messung vom 2026-09-19 ist nicht erhalten. Mit der dokumentierten Methode auf dem festgenagelten Export sind es **876** (40 Lesarten derselben Daten ergeben 788–897); der Scope `SCOPE4.json` v1 nutzt die 876. Beleg: AUDIT_LOG 2026-09-24, „The owner's defect scope“, Abschnitt „The 904“ (Branch `wip/p4-pilot`) | 28 Sites Unterschied, nicht zu benennen | nichts, wenn 876 gilt; sonst die Liste vom 2026-09-19 finden - dann wird sie als neue Scope-Version festgenagelt | nichts |
| D9 | **Zitatnummern ohne Quelle (Abnahme-Prüfung D1)** - **entschieden und geplant 2026-09-25** | Die Beschreibung setzt eine Nummer `[N]`, zu der `raw_data.description_citations` keinen Eintrag hat; der Leser sieht eine nackte hochgestellte Zahl. Welche Quelle den Satz trägt, steht nicht in den Daten, und ein Agent darf weder eine Quelle erfinden noch den Text umschreiben. Die Lane `orphan-citations` schreibt diese Sites deshalb gar nicht, auch nicht ihre unzitierten Einträge. Stand 2026-09-25: Die Abnahme `draw-2026-09-25` ist an D1 gescheitert (Kuntur Amaya). Die Lane repariert 69 der 78 D1-Sites; übrig bleiben diese 9. | **9 Sites**: Laüs [3], Porth Hellick Down [2], Acci [2], Ağbulaq Necropolis [2], Afrodit Tapınağı [2], A Figa [2][3][4], Temple of Zeus in Kyrene [2]. Dessen einziger Eintrag [1] zitiert außerdem den „Temple of Bel“ (Warwick), also eine andere Stätte. Killa Mach'ay [4]: Eintrag 2 („3,400 metres“) zitiert kein Marker, er ist wohl die Quelle von [4]. Absalom's Tomb [7][8]: Die Einträge 4, 5 und 6 tragen fast wörtlich die Sätze mit [6], [7] und [8]; eine Umnummerierung des Arrays würde genügen. Die Liste mit Textauszug und allen Einträgen steht in `output/remediation/mechanical_citations/SKIPPED.jsonl` und `PLAN.md`, der Beleg in AUDIT_LOG 2026-09-25, „Acceptance draw-2026-09-25 ends FAIL on A3 (D1)“. | ~~Für jede Site eine von drei Möglichkeiten: (a) die Quelle für die Nummer nennen, der Eintrag kommt dann per Journal-Lane; (b) die Nummer oder den Satz aus dem Text nehmen, als Textänderung mit Journal; (c) die 9 Sites in den Phase-4-Scope aufnehmen (neue Scope-Version, Text und Zitate baut dann der Code). Ohne Reparatur trifft die neue Stichprobe von 60 aus 4.194 mit **12 %** mindestens eine dieser Sites, und dann scheitert A3 erneut.~~ **Entschieden 2026-09-25 durch deinen Auftrag „keine Fragen mehr, autonom Empfehlungen umsetzen“, nichts mehr von dir nötig.** Ergebnis je Site: **6 mit neuem, belegtem Text** über Option (c), den D9-Lauf (Phase 4, Scope-Version 2; Beschreibungen im Journal 73840–73851, Karten 73870–73875): Laüs, Porth Hellick Down, Acci, Ağbulaq Necropolis, Temple of Zeus (Kyrene), Absalom's Tomb. **3 über Option (b)**, weil Phase 4 sie zurückhielt, mit der neuen Lane `dangling-markers`: **Killa Mach'ay** (`abstained`) verliert [4] („[1][3][4]“ wird „[1][3]“) und dazu den Eintrag 2 („3,400 metres“), den danach keine Nummer mehr zitiert – ohne das hielte D1 dort nicht, und dieselbe Wikipedia-URL tragen die Einträge 1 und 3 weiter; **Afrodit Tapınağı** (`search-stopped`) verliert dreimal [2]; **A Figa** (`search-stopped`) verliert [2], dreimal [3] und [4]. Jeweils fällt nur die Nummer mit dem Leerzeichen davor weg, sonst bleibt der Text Zeichen für Zeichen gleich und behält seine KI-Kennzeichnung (Lane L); nur deren Hash zieht mit. Auf Produktion geprobt (ROLLBACK): danach halten D1 und D4 auf allen 5.004 Sites. Die Schreibung macht der Orchestrator; Plan und Belege: `output/remediation/mechanical_dangling_markers/PLAN.md`, AUDIT_LOG 2026-09-25, „HUMAN_ONLY D9 option (b)“. Wer später eine Quelle für einen dieser Sätze nennt, bekommt Nummer und Eintrag per Journal-Lane zurück; die alten Werte liegen im Journal (`old_value`). Nebenbei: Bei 61 der 69 reparierten Sites zeigt das Popup danach dieselben Quellen-Links, weil ihre Einträge auf der Domain der eigenen `source_url` liegen. 8 Sites verlieren einen sichtbaren Link: Carmona, Altar of the Twelve Gods, Belören Kalesi, Borough Hill (Sawston), Agios Georgios Hill, Bedd Taliesin (Coflein), Agri Bavnehøj und Temple of Khonsuirdis. Temple of Khonsuirdis hat keine `source_url` und zeigt danach gar keine Quelle mehr; seine Einträge sind allerdings nur allgemeine Artikel (Liste ägyptischer Tempel, Psammetich I., Luxor). Alle entfernten Einträge liegen im Journal (`old_value`). Wer einen davon zurück will, setzt dafür auch die Nummer in den Text. | ~~die neue Abnahme (A3)~~ nur noch bis zur Schreibung der Lane `dangling-markers`; danach scheitert keine der 5.004 Sites mehr an D1 |
| D10 | **Die März-Texte außerhalb des Defekt-Scopes (Abnahme `draw-2026-09-25b`, Stufe 1)** - **offen, nur der Teil „Leeren“** | Die neue Abnahme misst die Texte, die dein Scope „Nur Defekt-Sites“ (2026-09-23) stehen ließ. Stufe 1, noch ohne zweite Richter: alte März-Karten **18 von 43 falsch, alle schwer** (erfundene Jahreszahlen, Maße, Behauptungen), Phase-5-Karten 1 von 12; alte März-Beschreibungen **9 von 29 schwer falsch**, Phase-4-Beschreibungen 1 von 10. Der Scope beruhte auf dem Phase-3-Finder, und der hat die meisten Textfehler nicht gefunden. Solange diese Texte ausgeliefert werden, kann keine Abnahme bestehen (A1/A2; die Wahrscheinlichkeit liegt bei etwa 0,0002). Entwurf mit Zahlen: `output/remediation/REPAIR_TEXTS_2026-09-26.md`. | **gemessen 2026-09-25** (Journal-ID 73911): 4.063 der 4.926 lebenden Sites tragen noch März-Text, 3.238 davon hat Phase 4 nie gesehen (2.477 mit eigenem englischem Artikel, 246 mit geteiltem Artikel, 515 ohne Artikel). | **Teil 1, unter deinem Auftrag vom 2026-09-25 umgesetzt, keine Entscheidung nötig:** Phase 4/5 über die 3.238 Sites mit Scope-Version 3 (so hatte das Design ursprünglich rund 4.300 Sites vorgesehen). **Teil 2, deine Entscheidung** (er hebt „Alle kennzeichnen“, D6 und die Plan-Regel E1 „kein Massen-Umschreiben von Beschreibungen ohne gesonderte Freigabe“ auf): Was danach zurückgehalten bleibt (geschätzt etwa 2.100 Beschreibungen und 2.430 Karten), wird entweder **(a) geleert**. Das ist die Regel des Plans „belegt oder leer“: Die Karte fällt auf der SiteCard auf die Beschreibung zurück, aber rund 43 % der Site-Seiten verlieren ihren Text (Risiko dünner Seiten in der Search Console); Rücknahme mit einem Befehl über das Journal. Oder es wird **(b) je Site von Opus geprüft und gekürzt**: Es bleiben nur Sätze mit zwei belegten Quellen, und wo nichts bleibt, wird geleert (etwa 60 Mio. Tokens, eine neue Lane mit Pilot, mehrere Tage). **Empfehlung: für die Karten (a)**, sie sind kurz, laut vorgelesen und zu 42 % schwer falsch; **für die Beschreibungen (b)**. Bis du entscheidest, wird nichts geleert; Teil 1 dauert ohnehin länger als einen Tag. | die nächste Abnahme |

## C. Grenzen, die auch im autonomen Lauf gelten

* **Kein Push, kein Deploy, kein Versand** ohne dich (A1/A2) - freigegeben ist Push #2 (D5), durch
  deinen Auftrag vom 2026-09-25.
* **Keine Zugangsdaten erfinden**: was nur du hast, wird gefragt, nicht geraten (A3/A6).
* **Keine Prüfung wird aufgeweicht**, damit sie grün wird — auch nicht unter Zeitdruck.
* Nach **zwei gescheiterten Versuchen** am selben Problem: Meldung statt Weiterraten.

## Was der Agent allein macht (zur Abgrenzung)

Zensus, Modellprüfung aller 5.004 Sites über die fünf Felder (Beschreibung, Zeitstellung, Typ, Land,
Kartentext), Korrekturvorschlag **mit Belegzitat**, Quellenabruf, Journal + Rücknahme-SQL je
Schreibung, Backups/Retention, Prüfflotten, Selbstangriff gegen den Auftrag, Abschlussbericht.
