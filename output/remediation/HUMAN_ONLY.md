# Was nur ein Mensch tun kann

Stand: 2026-09-21. Auftrag: **alle 5.004 `ancient_nerds`-Sites prüfen und vom Modell korrigieren lassen
(deepseek-v4.1-flash), mit Quellen und Belegen an jeder Korrektur.** Diese Tabelle listet alles auf, was
davon **nicht** durch einen Agenten erledigt werden kann — mit Menge, Beleg und der Frage, die du
beantworten musst.

**Stand des Schreibens (2026-09-22):** Die Korrekturen sind **in der Produktionsdatenbank** —
**994 Zeilen an 1.022 Sites** aus beiden Wellen (erste Welle 410 Zeilen an 396 Sites, zweite Welle
584 Zeilen an 601 Sites: 596 `site_type`, 389 `period_start`, 9 `country`), jede mit Journaleintrag.
Zurückgehalten: 72 Zeilen (Handprüfung); an der Länderprüfung abgelehnt: 8 Zeilen; **80 geplante Zeilen
stehen unverändert auf dem alten Wert**. Der Schreiber hat nach jedem 100er-Schritt nachgelesen:
**sechsmal 0 Abweichungen**, `matched_0=0`. Abnahme von außen (`logs/verify_writes.py`, fragt die
Datenbank in beide Richtungen): **994 Zeilen tragen den neuen Wert, 80 tragen unverändert den alten,
1.022 von 1.022 Sites gelesen — 0 Abweichungen**. Vor der ersten Welle: Sicherung
`backups/2026-09-21_pre-write/` (655 MB) mit bestandenem Restore-Test (`unified_sites` 1.759.676 =
1.759.676). Zu jeder Schreibung liegt eine Zeile im Journal `remediation_change_log` mit altem und
neuem Wert, und daneben je Chunk eine `ROLLBACK.sql`, die die Umkehrung in einer Transaktion ausführt,
prüft, dass jede Zeile wieder auf dem alten Wert steht, und dann `ROLLBACK;` setzt — sie beweist die
Umkehrbarkeit, statt sie auszuführen.

Belege: `snapshot/unified_sites.jsonl.gz` (eigene Zählung heute), `phase3_pilot/COST.md:141`,
`AUDIT_LOG.md` (Routing-Messung, mypy-Zählung, VLM-Kompetenz), `git log`.

## A. Entscheidungen, die den Lauf oder das Ausliefern freigeben

| # | Was nur du kannst | Warum kein Agent | Umfang | Was ich von dir brauche | Blockiert |
|---|---|---|---|---|---|
| A1 | **Push nach `main`** | Ein Push ist ein Live-Deploy (`ci.yml`). Unumkehrbar nach außen. | **97 Commits** lokal, nicht gepusht | „push" oder „weiter lokal" | Auslieferung |
| A2 | **Die korrigierten Daten auf den Globus bringen** | Die DB ist noch am selben Tag korrigiert; die statischen JSON entstehen erst beim Deploy. Das ist der Push (A1). | 5.004 Sites betroffen | Freigabe des Push | Auslieferung |
| A3 | **Web-Recherche: Suchanbieter + Key** | Im Code existiert **keine** Suchroute (geprüft: kein `*SEARCH*`/`SERP`/`TAVILY`-Zugriff). Ein kostenpflichtiger Key ist Zugang **und** Kosten — beides deine Sache. | betrifft alle 5.004 Sites | **entschieden 2026-09-22: MiniMax** — die Suchroute wird mit MiniMax geklärt (nur der Suchdienst, die Begründung bleibt bei deepseek) | nur die Suchstufe |
| A4 | **Cron-Mailadresse (`MAILTO`)** | Der Aufräum-Cron hat kein `MAILTO`; ein fehlgeschlagenes Backup meldet sich niemandem. | 1 Zeile Crontab | deine Adresse | kein Lauf, aber Sicherheit |
| A5 | **Offsite-Kopie** | Das Repo (`.git` = 35 G) liegt auf derselben Maschine. Ein Ausfall der Maschine nimmt Code **und** Verlauf mit. | 1 Entscheidung | wohin kopieren (Ziel/Medium) | Sicherheit |
| A6 | **`video-assets/prod-db.env`** | Unbekannte Zugangsdatei; Inhalt kann ich nicht lesen (Policy) und darf es nicht. | 1 Datei | sagen, ob sie für den Lauf gebraucht wird | unklar |
| A7 | **`mypy api/` Altbestand** | 93 Typfehler sind **vorbestehend**, nicht aus dieser Arbeit. CI-Gate kann dadurch rot sein. | 93 Fehler | jetzt reparieren oder getrennt führen | CI-Grün |

## B. Sites, bei denen der Lauf dir eine Entscheidung vorlegt (Menge kommt aus dem Lauf)

| # | Was nur du kannst | Warum kein Agent | Umfang (gemessen) | Was ich von dir brauche |
|---|---|---|---|---|
| B1 | **Namens-/Koordinaten-Fälle** | Ein Wikidata-Name ≠ gespeicherter Name kann ein **Alias** sein — das ist eine Projekt- und Sprachfrage, keine Faktenfrage. | ~~285 Sites~~ — die 285 aus `COST.md:141` sind **reine Koordinatenfälle**; die Alias-Frage betrifft **631 Namensbefunde** (T01). Stand 2026-09-23: siehe Abschnitt „B1/B2 — was die Daten entschieden haben“ | **fast alles mechanisch entschieden** — offen: 46 Namen lesen, 1 Freigabe (9 Koordinaten), 5 verdächtige Links hinter passenden Namen, Einzelfälle unten |
| B2 | **Land bei grenzwertiger Lage** | `lat/lon` außerhalb des beanspruchten Landes: Grenzfluss, Insel, Gebietsreform — topologisch richtig, inhaltlich falsch. | **117 Sites** (T02), mechanisch eingeteilt: siehe Abschnitt „B1/B2 — was die Daten entschieden haben“ | offen: 2 Länder (Weg: mechanische Lane), 1 Umkehr, `Baltic Sea`, ~15 Koordinaten ohne zweiten Zeugen |
| B3 | **Quelle für Sites ohne Textroute** | Braucht eine Quelle, die kein automatischer Endpunkt liefert. | **17 Sites** ohne Wikipedia/Prosa-Route; 385 ohne enwiki, davon 368 über `source_url` erreichbar; **42 Sites ohne `source_url`** | Quelle nennen oder „keine Quelle möglich" |
| B4 | **Foto-Auswahl (Stichprobe)** | Der Bildprüfer ist **über-inklusiv** bei `site_photo` (gemessen) — nur Augen entscheiden, ob ein Foto die Site zeigt. | Stichprobe der 200 geprüften Bilder + Neuzugänge | Freigabe der Stichprobe |
| B5 | **Stil-/Rubrikgrenzfälle** | „Legend says …", „among the most famous" — Fehler oder erlaubter Ton? Das ist eine Redaktionsfrage. | 3–4 Fälle je Prüfrunde | Regel: Fehler oder nicht |
| B6 | **Löschungen** | Der Plan verbietet `DELETE`. Wenn eine Site ganz weg soll, ist das deine Entscheidung. | unbekannt | Einzelfall-Freigabe |
| B7 | **72 zurückgehaltene Zeilen** | Der Prüfer hat sie freigegeben, aber seine eigene Begründung trägt die Korrektur nicht (z. B. „der gespeicherte Wert ist nicht widerlegt", „der gröbere Typ widerlegt den feineren nicht"). Ich schreibe sie **nicht** — lieber eine Zeile zu wenig als eine unbelegte Zeile in der DB. | **72 von 481** geplanten Zeilen, Liste mit Zitat: `logs/_write_apply/HOLDS.md` | **entschieden 2026-09-21: weglassen** |
| B8 | **4 Zeilen, die die Grenzprüfung abgelehnt hat** | Der Name passt zu einem anderen Ort derselben Schreibweise, die Koordinaten liegen woanders: Lamay (`Mexico→Peru`), San Claudio (`Mexico→Spain`), Soura (`Türkiye→India`) — und Jaffa Gate (`Israel→Palestine`), eine politische Linie, die die Koordinaten nicht entscheiden. | 4 Zeilen | **entschieden 2026-09-21: keine davon schreiben** |
| B9 | **Schreibweise Nordirland** | Die DB hält 1.052 `England` + 118 `Wales` + 83 `Scotland` + **4 `Northern Ireland`** gegen **genau ein** `United Kingdom` — die Konvention des Datensatzes ist das Landesteil. Der Prüfer schrieb 3 Zeilen auf `United Kingdom`; geografisch richtig, aber eine zweite Schreibweise für denselben Ort. | **26 Zeilen** (3 geschrieben, 22 aus dem Zensus, 1 weiterer Treffer) | **entschieden 2026-09-21: `Northern Ireland`** — meine erste Vorlage war falsch begründet, mit der Messung erneut gefragt |
| B10 | **Politische Grenzfälle aus dem Zensus** | Zypern 14, Krim 9, Kosovo 2, Golan 2, Palästina 2 — die Datei `countries.geojson` sagt etwas anderes als der Datensatz, und die Datei ist keine politische Instanz. | **29 Zeilen**, Liste: `logs/_country_mismatches.txt` | **entschieden 2026-09-21: so lassen** |
| B11 | **Geschriebene Zeilen, die die Regeln vom 23.09. heute nicht schrieben** | Zwei neue Schreiber-Regeln (nach dem gescheiterten Such-Pilot) auf die 994 schon geschriebenen Zeilen angewandt, nur gemessen, nichts geändert: (1) Die **Widerspruchsregel** — der Prüfer schrieb `REFUTED: NO`, seine eigene Begründung nennt aber eine scheiternde Hälfte — hielte **77** Zeilen zurück. Nach drei Lesungen sagen davon 60–62 wirklich „gespeicherter Wert nicht widerlegt" oder „Vorschlag widerlegt", also dieselbe Klasse wie B7 (dort: weglassen); rund 10 sind Fehlalarme, deren Satz weiter unten für die Schreibung argumentiert (Presa-Tusiu, Annaghmare, Chacamarca, La Almoloya, Apollonia, Ashley, Court Hill, Erebuni, Asclepieion of Athens, Pen Dinas); 5–8 sagen beides. (2) Die **Bucket-Regel** — eine `period_start`-Änderung innerhalb des Buckets des alten Werts ist kein Fehler — hätte **170 der 389** geschriebenen `period_start`-Zeilen nicht geschrieben. Beide Gruppen stehen unverändert in der DB. | **77 + 170 Zeilen**, je mit Schlüssel, altem/neuem Wert und Prüfer-Begründung: `logs/review_holds/WRITTEN_HELD_BY_PHRASE.md` und `logs/review_holds/WRITTEN_SAME_BUCKET.md` (erzeugt mit `tools/measure_review_holds.py`, Befehl im Kopf des Skripts) | je Gruppe oder je Zeile: **behalten oder zurücknehmen** (Rücknahme über das Journal, wie jede andere Schreibung) |
| B12 | **Zurückhaltungen durch vier Formulierungen, die sich nachweislich geirrt haben** | Die Widerspruchsregel hält künftig (Gap- und Suchlauf) jede Zeile zurück, deren Prüfer-Begründung eine scheiternde Hälfte nennt. Vier ihrer 18 Formulierungen haben auf den geschriebenen Zeilen Fehlalarme gezeigt: „neither half holds" **4 von 7**, „the stored value is not contradicted" **4 von 9**, „the reason fails" 1 von 4, „does not show the stored value wrong" 1 von 10. Solche Zeilen werden nicht geschrieben, aber ihre Ablehnung trägt den Vermerk `hand-read before it counts as refused (HUMAN_ONLY.md B12)` — sie sind keine erledigte Ablehnung. | je Lauf: die Ablehnungen `reviewer-why-names-a-failing-half` mit diesem Vermerk | Regel bestätigen: Handlesung, und geschrieben wird eine solche Zeile nur mit deiner Freigabe |

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

1. **Die 9 Koordinaten schreiben?** FIELD_CONTRACT §4.6 verbietet automatische Koordinatenänderungen.
   Der Plan erfüllt deine Regel „zwei unabhängige Zeugen“ in der strengen Form oben (kein Import, keine
   Rundungskopie, nicht derselbe Punkt); ein „ja“ genügt, der Orchestrator fährt dann Probe, Anwendung
   und Nachlesen. Keine der 9 landet in einem anderen Land als dem gespeicherten.
2. **Dubletten ausblenden:** Darf E4 `retired` (Grund `duplicate_of:<uuid>`) für die 19 Verlierer
   genutzt werden? B6 verlangt die Freigabe je Site — die Liste nennt jede einzelne mit Beleg. Und
   Banias / Caesarea Philippi: welche Zeile, und damit welches Land (B10)?
3. **`Baltic Sea`**: welches Land (oder keines) für eine Stätte in internationalen Gewässern?
4. **Ahin Posh Tape**: Phase 3 schrieb `Afghanistan → Pakistan`; die eigene Beschreibung sagt „bei
   Jalalabad, Afghanistan“, der Wikidata-Link ist ein Dorf in Pakistan. Umkehr + Punkt prüfen.
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
   (`/data/images/wiki/9a9a0dca/hero.webp` antwortet 200). Dedans Vorschaubild zeigt noch auf diese
   Datei; der geplante Chunk `thumb-repoint-2026-09-25-001` (AUDIT_LOG 2026-09-25) leert es, weil
   Dedan kein lebendes Bild mehr hat. Die Bild-Lanes löschen nie Dateien (Design Eintrag 7). **Deine
   Frage:** sollen die sechs Dateien vom Server?

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

## D. Phasen 4 und 5: Beschreibungen und Kartentexte (Stand 2026-09-23, gebaut, nichts geschrieben)

Entwurf: Eintrag [6] in `logs/design_texts_images_2026-09-22.json`. Die Texte werden von Code aus
Sätzen einer festgenagelten Wikipedia-Revision zusammengesetzt; das Modell wählt nur Satz- und
Span-Nummern. Geschrieben wird erst nach Push #1, in Schritten zu 100 Sites, jede Zeile mit Journal.

| # | Was nur du kannst | Warum kein Agent | Umfang | Was ich von dir brauche | Blockiert |
|---|---|---|---|---|---|
| D1 | **Push #1: Kennzeichnung und Namensnennung ausliefern** | Ein Push ist ein Live-Deploy (A1). Er muss **vor** der ersten Schreibung live sein, damit keine Seite ohne ihren Hinweis ausgeliefert wird. Er enthält: die Zeile unter der Beschreibung, die Provenienz-Felder der API, die Entfernung des 10-Site-Zitat-Seeds aus `api/main.py` (alle 10 tragen den Schlüssel, lesend geprüft am 23.09.), die Lizenzzeilen in Disclaimer und `terms.html`, den Satz-Splitter. Sichtbar ändert sich vor der ersten Schreibung nichts - gerendert wird nur, wo Provenienz existiert. | 1 Push | „push #1" - und zuvor den Wortlaut von D2 und D3 bestätigen | alle Schreibungen der Phase 4 |
| D2 | **Wortlaut der Zeile unter der Beschreibung** | Rechtstext (CC BY-SA 4.0 §3(a), EU AI Act Art. 50). Entwurf, übernommen aus dem Design: `Text: Wikipedia – '<Titel>' (revision of <Datum>), CC BY-SA 4.0 · sentences selected and shortened by an AI system · source →` (bei übersetztem Text: `· translated by an AI system ·`). Für KI-geschriebenen Text (Übersetzung, Umformulierung, Altbestand vom März) steht zusätzlich die bestehende Fußnote `AI-generated text · images from the original sources · always verify with the sources.` | 1 Zeile + 1 Fußnote | **entschieden 2026-09-23: Entwurf ok** | D1 |
| D3 | **Satz in Disclaimer und `terms.html`** | Rechtstext. Entwurf: „Site descriptions reproduce and shorten text from Wikipedia under CC BY-SA 4.0; each links its exact source revision." - dazu grenzt der Disclaimer CC BY-NC-SA 4.0 auf Stories, Journals und Dokumentation ein, und der Wikipedia-Eintrag nennt 4.0. Achtung: für übersetzte (T), umformulierte (R) und alte März-Texte (L) trifft „reproduce and shorten" nicht wörtlich zu; die Seiten selbst sagen es je Site richtig. | 2 Dateien | **entschieden 2026-09-23: präzise Fassung** - „Site descriptions that carry a source line reproduce, shorten or translate text from the linked source revision (Wikipedia: CC BY-SA 4.0); the line states how an AI system was involved." (wahr ab dem Push und nach jeder Schreibung) | D1 |
| D4 | **SEO-Risiko zur Kenntnis nehmen** | Rund 4.400 SSR-Seiten tragen danach Wikipedia-Wortlaut (Duplicate Content). Gegenmittel: Auswahl und Kürzung je Site, eigener Kartentext, strukturierte Daten (`isBasedOn`, `license`), korrektes `lastmod` aus dem Journal. 14 Tage nach der Pilot-Schreibung prüfe ich die Pilot-Kohorte mit `scripts/gsc_report.py` (inspect) und berichte - das blockiert nichts. | Hinweis | „gelesen" | nichts |
| D5 | **Push #2: Kartentexte** | Die Karten-Datei wird bei jedem API-Start in die DB übernommen. Deshalb eine Sitzung, in dieser Reihenfolge: Backup-Drill, Schreibung der Karten mit Journal, Datei byte-gleich aus der DB neu erzeugen, **sofort** Push #2. Datei vor der DB zu pushen ist verboten (Boot-Import ohne Journal). Wenn CI rot wird und kein Deploy kommt: Rücknahme über `revert4.py` und `git revert`. | 1 Sitzung, ~44 Schritte | die Zusage, dass du am Ende der Sitzung sofort pushst | alle Kartentexte |
| D6 | **Sites ohne Quelle (Spur 0) und die Halteliste** | Was kein Artikel und keine freie Quelle trägt, bleibt beim alten Text; das entscheidet der Lauf, nicht ein Agent. Liste mit Grund je Site: `phase4_runner/HOLDS4.jsonl` nach dem Massenlauf. | wird gemessen | Sichtung; je Site „so lassen" oder Quelle nennen (wie B3) | nichts |
| D7 | **Alttexte ohne beweisbare Herkunft** | Ein zurückgehaltener Text, der dem Stand vor März (`d4526691`) gleicht, bekommt **keine** KI-Kennzeichnung - seine Herkunft ist nicht beweisbar. Liste: `logs/_write_apply_p4l/*/UNCLAIMED.jsonl`, Zahl im Abschlussbericht. | wird gemessen | Sichtung | nichts |

## C. Grenzen, die auch im autonomen Lauf gelten

* **Kein Push, kein Deploy, kein Versand** ohne dich (A1/A2).
* **Keine Zugangsdaten erfinden**: was nur du hast, wird gefragt, nicht geraten (A3/A6).
* **Keine Prüfung wird aufgeweicht**, damit sie grün wird — auch nicht unter Zeitdruck.
* Nach **zwei gescheiterten Versuchen** am selben Problem: Meldung statt Weiterraten.

## Was der Agent allein macht (zur Abgrenzung)

Zensus, Modellprüfung aller 5.004 Sites über die fünf Felder (Beschreibung, Zeitstellung, Typ, Land,
Kartentext), Korrekturvorschlag **mit Belegzitat**, Quellenabruf, Journal + Rücknahme-SQL je
Schreibung, Backups/Retention, Prüfflotten, Selbstangriff gegen den Auftrag, Abschlussbericht.
