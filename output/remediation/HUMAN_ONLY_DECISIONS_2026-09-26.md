# HUMAN_ONLY – Entscheidungen nach O9 (2026-09-26)

Grundlage: Owner-Entscheidung **O9** vom 2026-09-26, „Nach meiner Empfehlung entscheiden“ (`FINISH_PLAN_2026-09-26.md`
§1). Jeder offene Punkt aus `HUMAN_ONLY.md` wird nach der dort oder im verwiesenen Beleg festgehaltenen Empfehlung
entschieden; wo O1-O11 einen Punkt neu regeln, gilt die neue Regel. Gemessen wurde nur lesend: Produktion per SELECT am
2026-09-26 (Journal-Maximum `remediation_change_log.id` = 73911, seit der D10-Messung ist also nichts geschrieben), das
VPS-Dateisystem per `ls`/`command -v`, lokal `mypy api/`. Nichts geschrieben, nichts gepusht.

Workstreams (FINISH_PLAN §3): WA Beschreibungen v3 · WB Teaser-Karten · WC Satzprüfung · WD1 Koordinaten/Periode/Typ/
`source_url` · WD2 Bilder/Scope · WF Ausliefern und Bericht. Die eigenen Aktionen führt WE aus, mit den stehenden Regeln
(Journal, Probe, Schritte ≤ 100 Sites, Rücklesen, geprobte Rücknahme, kein DELETE). Neu benannt: **L5**, eine Link- und
Namenswelle (B1-L, B1-N), denn keine Workstream schreibt `site_external_ids` oder `name`. L5 läuft **vor** dem WD-Harvest.

**Bilanz: 27 offene Punkte.** Durch eine Workstream ausgeführt: **13** (B1-D, B1-K, B2-B, B3, B4, B5, B6, B13, Nr. 4,
Nr. 10, D6, D7, D10). Mit eigener Aktion: **10** (A4, A5, A7, B1-L, B1-N, B2-L, Nr. 7, Nr. 8, Nr. 9, D4). Nur
Dokumentation: **4** (A6, B12, Nr. 11, D8). Owner wirklich nötig: nur **A4** (Webhook-URL oder Root + Mail-Relay) und
**A5** (Drittstandort: Konto, Datenträger, Kosten).

## A. Freigaben und Betrieb

### A4 – Cron-Mailadresse (`MAILTO`)
- **Empfehlung/Messung:** keine inhaltliche Empfehlung (AUDIT_LOG 2026-09-20: „choosing a destination I do not have;
  flagged for Martin“). Die Crontab von `deploy` hat 2 Backup-Einträge und 0 `MAILTO`. Auf dem VPS fehlen `sendmail`,
  `mail`, `mailx`, `msmtp` und `ssmtp`, und `deploy` hat kein sudo; ein `MAILTO` stellte also nichts zu.
- **Entscheidung:** Alarm über den Discord-Webhook des Projekts (`pipeline/utils/notify.py`, `DISCORD_WEBHOOK_URL`). Auf
  denselben Webhook warten Alarm und Digest des Founders-Dashboards.
- **Ausführung:** Code-Änderung in `scripts/remediation/00_backup_and_drill.sh`: bei Exit ≠ 0 ein `curl -X POST` an die
  URL aus einer Datei, die nur `deploy` lesen darf. Probe per erzwungenem Fehlschlag (`BACKUP_ROOT=/tmp/cron_probe`).
  **Owner nötig: ja**: Nur der Admin des Discord-Servers kann die Webhook-URL anlegen. Echte Mail bräuchte Root und ein
  Relay-Konto.

### A5 – Offsite-Kopie
- **Empfehlung/Messung:** AUDIT_LOG 2026-09-20, „Offsite copies“: Kreuzkopie Arbeitsplatz ↔ VPS für die Bilder
  (20 GB) und `video-assets/` (4,6 GB); „a genuine third-party offsite still needs `rclone`/bucket credentials that are
  Martin's to supply“. Heute liegt der Code auf GitHub (`origin/main` enthält `integrate/wave1`). Nur an einem Ort
  liegen die DB-Dumps (VPS, `backups/<datum>_remediation/`, ~655 MB) und `output/remediation/` (Arbeitsplatz, 2,3 GB);
  auf dem VPS sind 88 GB frei.
- **Entscheidung:** Drittstandort wie empfohlen; bis dahin wird die Kreuzkopie auf die beiden Einzelstücke ausgedehnt.
- **Ausführung:** wöchentlich nach dem Sonntags-Drill den neuesten Dump per `scp` nach
  `C:/PythonProjects/AncientMap-Offsite/db/`; dazu `tar -czf - -C output --exclude='*.env' remediation | ssh ancientnerds "cat > /var/www/ancientnerds/backups/remediation-evidence/remediation-2026-09-26.tgz"`
  und sha256 auf beiden Seiten. **Owner nötig: ja, nur für den Drittstandort** (Konto und Kosten eines
  Speicheranbieters oder ein externer Datenträger).

### A6 – `video-assets/prod-db.env`
- **Empfehlung:** A6 selbst: „der Remediation-Lauf braucht sie nicht“; gebraucht würde sie nur für den Ledger-Nachtrag
  der 16 alten Shorts.
- **Entscheidung:** nicht gebraucht, denn der Nachtrag entfällt (Nr. 11). Die Datei bleibt unberührt und ungelesen.
- **Ausführung:** nur Dokumentation. **Owner nötig: nein.**

### A7 – `mypy api/`-Altbestand
- **Empfehlung/Messung:** keine Empfehlung. CODE_AUDIT_2026-09-25: Der CI-gleiche Lauf (`ci.yml:136`, ohne
  Abhängigkeiten) ist sauber. Heute meldet das Repo-venv „Found 93 errors in 14 files“, alle vorbestehend.
- **Entscheidung:** getrennt führen. Kein Gate ist rot, und es ist keine Remediation-Arbeit.
- **Ausführung:** eigene Code-Änderung nach WF (etwa `/audit` bei freier Quota). **Owner nötig: nein.**
- **Nachtrag 2026-09-26 (vorgezogen):** Die Abschluss-Orchestrierung hat A7 als WE2 in WE gelegt, und WE kommt nach
  FINISH_PLAN §3 vor WF. Gebaut auf `wip/we2`: mit dem Repo-venv (mypy 1.19.1) 93 → 0 Fehler, mit mypy 2.3.1 ebenfalls
  0; der CI-gleiche Lauf ohne Abhängigkeiten endet vorher wie nachher mit Exit 0. Die Änderung ist Typisierung plus zwei
  echte Fehlerbehebungen mit Tests (`52d37fa` remove-image, `c6b58ff` `/ask`) und dem Entfernen des Discord-Mocks der
  Testsuite (`7e6d0e5`); kein Gate war rot. Sie geht wie jede grüne Code-Änderung nach `main`. Ein Push baut das
  api-Image (Discord-Bot, Kartenspiel) und, wegen `pipeline/database.py`, das Lyra-Image neu; api und api2 starten
  nacheinander hinter Health-Checks neu. Die journalisierten Lanes schreiben über psql (`mechanical/apply.py`), nicht
  über die API. Beleg: AUDIT_LOG 2026-09-26 „A7“, Runbook `docs/procedures/CODE_AUDIT.md`.

## B. Einzelfälle und Regeln

### B1-L – Links (Nr. 5, 6): 5 verdächtige, 11 ohne 1-km-Beweis, 2 widersprüchliche + Tikal, 47 unverändert gelassene
- **Empfehlung/Messung:** Nr. 5: „derselbe Fehler, den die Wellen 1 und 2 reparieren“. Nr. 6: „Lesen“. `names.jsonl`
  `link_suspect` (72 Sites): „Kandidaten für eine spätere Recherche-Welle“. Milefortlet → Q1568283 „milecastle“
  (geteilt mit Milecastles, beide auf demselben Punkt); Dolmens of Sardinia → Q101659; Nuraghes of Sardinia → Q688292;
  Asklepion Kos → Q731841 (geteilt mit Pathos auf Zypern). „The Temple of Artemis“ (`a939e800…`, `Greece`) steht bei
  40.780, 24.716, 0,8 km von der Stadt Thasos, trägt aber Q43018, die Ephesos-Beschreibung und die 19 Bilder von „The
  Temple of Artemis-Selçuk“ → B1-D. Themistoclean Wall ist ein Fehlalarm.
- **Entscheidung (O6):** Opus liest je Site. Ein QID bzw. `enwiki_title` wird nur geschrieben, wenn Objekt oder Artikel
  genau diese Stätte nennt (keine Gattung, kein Container, kein Geschwister); sonst wird der falsche Link entfernt.
- **Ausführung:** eigene journalisierte Lane **L5** auf `site_external_ids` mit dem Werkzeug der Wellen 1-4
  (`qid_repair/`), bis zu 120 Sites (47 + 72 + Tikal). L5 läuft vor dem WD-Harvest, sonst erntet WD `P625`, `P571` und
  `P18` von Gattungsobjekten. Den Scope der Sammeleinträge entscheidet WD2. **Owner nötig: nein.**

### B1-N – 46 Namen (N7)
- **Empfehlung/Messung:** „Lesen“ (19 an einer Ortschaft, 27 an einer Site verankert). 44 sind sichtbar, 0 im Journal
  umbenannt. Stufe 1: Name 56 richtig / 1 kosmetisch falsch / 3 unbelegbar von 60.
- **Entscheidung:** Gelesen wird in L5; bei den 19 Ortschafts-Ankern ist der Link das Problem. Umbenannt wird nur mit
  einem belegten Namen dieser Stätte, sonst bleibt der Name (`name` ist NOT NULL).
- **Ausführung:** L5 mit einer neuen Namens-Lane: 2 Zellen, `name` und `name_normalized`; den Schlüssel
  `left(lower(unaccent(name)),500)` rechnet Postgres. Nr. 7 nutzt sie mit. **Owner nötig: nein.**

### B1-D – 5 Dublettenkandidaten (+ The Temple of Artemis)
- **Empfehlung/Messung:** in Nr. 6 als „Dublettenkandidaten“ geführt; es gilt die Überlebensregel der 19. Alle sind
  sichtbar: Amathunta/Amathus ≈10 m, Tel Hermal Fort/Shaduppum 1,7 km, Ñustahispana/Ñusta Hispana 0,5 km, zweimal
  „39 Bridge Street, Chester“ 14 m, Lycian Mezarı2/Amyntas Rock Tombs 1,1 km; dazu Temple of Artemis (GR) → Selçuk.
- **Entscheidung:** Belegt die Lesung eine einzige Stätte, wird der Verlierer `retired` (`duplicate_of:<uuid>`). Nichts
  wird gelöscht.
- **Ausführung: WD2.** **Owner nötig: nein.**

### B1-K – Koordinaten (Nr. 6, B2): 171 offene, Zeugenfälle, Stapelpunkte, Kirkûk/Qsarnaba
- **Empfehlung/Messung:** „Lesen“, Versetzung nur mit zwei Zeugen (FIELD_CONTRACT §4.6). Von den 171 sind 166
  sichtbar und nie versetzt. B2 hat 13 sichtbare Zeugenfälle, etwa die Tayma Stones auf dem Louvre (48.861, 2.336).
  12 Punkte tragen 34 sichtbare Sites. Kirkûk (24 km) und Qsarnaba (23 km) haben den richtigen Link, aber einen
  falschen Punkt. Stufe 1: Koordinaten 7 von 60 falsch, davon 5 schwer.
- **Entscheidung (O6):** Ein widerlegter Punkt wird durch einen belegten ersetzt: Die Quelle nennt diese Stätte samt
  Koordinate, und kein gleichwertiger Zeuge widerspricht (Muster: Nr. 4). Museumsobjekte bekommen den belegten Fundort.
  `lat`/`lon` sind NOT NULL; ohne Beleg bleibt der gespeicherte Punkt und zählt in WF als unbelegt.
- **Ausführung: WD1** (3 Zellen `lat`, `lon`, `geom` je Site, wie `bcases/coords_plan/`). **Owner nötig: nein.**

### B2-L – 2 Länder: Achladia, Delphinion
- **Empfehlung/Messung:** „Weg: eine mechanische Länder-Lane“. Achladia (`74145e9b-76a6-48de-a902-08ecb2f1f7bb`)
  steht auf `Germany`, liegt samt `P625` aber auf Kreta (P17 Greece). Delphinion (`6aa4c8de-3794-42fe-b68e-6b6ab77bd8ed`)
  steht auf `Greece`, liegt aber in Milet, 20 m von `P625`. Der Datensatz schreibt `Türkiye` (218 Zeilen, 0 `Turkey`).
- **Entscheidung:** Achladia `Germany → Greece`, Delphinion `Greece → Türkiye`.
- **Ausführung:** eigene journalisierte Lane mit 2 Zellen `country` (Muster `t05`/`uk-parts` in `mechanical/lane.py`,
  Prämisse = gespeicherter Punkt). Keine Workstream schreibt `country`. **Owner nötig: nein.**

### B2-B – `Baltic Sea` (Nr. 3)
- **Empfehlung/Messung:** zum Land keine Empfehlung. FINISH_PLAN §2 führt „Baltic Sea Anomaly“
  (`c8d2c13e-fd9a-466c-9fdc-fc26ee798ded`, sichtbar, `Underwater structures`) als Nicht-Site. Ihre Beschreibung: ein
  Sonarbild von Schatzsuchern (2011).
- **Entscheidung:** kein Land zu wählen. Die Site wird als Nicht-Site `retired`; `country` bleibt unverändert.
- **Ausführung: WD2.** **Owner nötig: nein.**

### B3 – Sites ohne Textroute oder ohne `source_url`
- **Empfehlung/Messung:** keine inhaltliche („Quelle nennen oder ‚keine Quelle möglich‘“). 42 sichtbare Sites haben
  keine `source_url`; 515 von WAs 3.238 Sites haben keinen Artikel.
- **Entscheidung (O5, O6):** Text kommt aus WA, wo ein Artikel existiert, sonst aus WC; ohne Beleg wird er geleert.
  `source_url` bekommt nur eine belegte URL der Stätte, sonst bleibt sie leer.
- **Ausführung: WA/WC** (Text), **WD1** (`source_url`). **Owner nötig: nein.**

### B4 – Foto-Auswahl, Augen-Labels
- **Empfehlung/Messung:** „ohne sie bleibt die Vision-Stufe zu“; C1 hat keinen Auslöser bestanden.
  `vlm_pilot/LABELS.jsonl` fehlt weiter. Stufe 1: gezeigtes Bild 11 von 60 falsch, 2 davon schwer.
- **Entscheidung:** Die Vision-Stufe bleibt zu; Augen-Labels sind nicht nötig. Das gezeigte Bild kommt nach O6 aus einer
  Quelle zum geprüften eigenen Objekt (`P18`, Leitbild des Artikels, `P373`); ist es widerlegt und ohne belegten Ersatz,
  wird Hero/Thumbnail geleert.
- **Ausführung: WD2.** **Owner nötig: nein.**

### B5 – Stilgrenzfälle („Legend says …“, „among the most famous“)
- **Empfehlung:** keine Regel festgehalten. Der Beleg (AUDIT_LOG, „The four writes the arithmetic called
  unjustified“) wertet es als quellennäher, eine unbelegte Legende durch die Einschränkung der Quelle zu ersetzen.
- **Entscheidung (O2, O5):** Ton ja, unbelegte Behauptung nein. „Legend says …“ nur, wenn eine Quelle die Legende als
  Legende berichtet; Superlative, „unerklärt“ und Zahlen nur mit Quelle.
- **Ausführung: WB** (Prüfer), **WC** (Satzprüfung). **Owner nötig: nein.**

### B6 / Nr. 2 – Banias / Caesarea Philippi
- **Empfehlung/Messung:** keine Empfehlung; gehalten, weil „welche Zeile bleibt, entscheidet ein Land“ (B10: „so
  lassen“). 290 m, dasselbe Q606295. Caesarea Philippi (`ce7db300…`, Israel) hat 5 Links und 20 Bilder, Banias (Syria)
  4 Links und 20 Bilder.
- **Entscheidung:** Die Überlebensregel gilt wie bei den 19: Banias wird `retired`
  (`duplicate_of:ce7db300-8777-425d-917a-2f6d9f325b58`). **Kein Land wird geschrieben** (B10).
- **Ausführung: WD2.** **Owner nötig: nein.**

### B12 – Handlesung für vier Formulierungen, die sich geirrt haben
- **Empfehlung/Messung:** „Regel bestätigen: Handlesung, geschrieben nur mit Freigabe“. Den Vermerk tragen 4
  Ablehnungen, alle aus dem Lückenlauf (`logs/_write_dry_gap/ALL_REFUSED.jsonl`): 2 `card_description`, 2
  `description`. Der DeepSeek-Pfad läuft nie wieder.
- **Entscheidung:** bestätigt; keine der vier wird geschrieben. Ihre Felder machen WB bzw. WA/WC ohnehin neu.
- **Ausführung:** nur Dokumentation. **Owner nötig: nein.**

### B13 – Die 21 „beide falsch“-Zeilen
- **Empfehlung/Messung:** keine inhaltliche Empfehlung („Wert mit Quelle nennen, oder ‚so lassen‘“). Alle 21 Zellen
  tragen den Wert vor Phase 3. 13 × `period_start`: Nine Stones, Chanhudaro, Choquequirao, Pampas Gramalote, Holyhead
  Mountain Hut Circles, Aquae Calidae, Carteia, Lalibela, Cave of Aurignac, Nine Ladies, Gårdstånga, Maa Palaeokastro,
  Argura. 8 × `site_type`: Altar of Athena Polias, South Stoa I, Palaestra at Delphi, Cnidian und Boeotian Treasury,
  Stoa Poikile, Alvastra Pile-Dwelling, Península de Kola.
- **Entscheidung (O6 statt „so lassen“):** belegt ersetzen (wörtliches Zitat über diese Stätte), sonst leeren. Ein
  geleertes `period_start` leert `period_name` mit und macht die Site zum E3-Fall (b), ohne Datum. Kola ist die
  Halbinsel; ihre Beschreibung nennt als Stätte Bolshoy Oleni Ostrov.
- **Ausführung: WD1**, für Kola zuerst **WD2**. **Owner nötig: nein.**

### Nr. 4 – Ahin Posh Tape, der Punkt
- **Empfehlung/Messung:** AUDIT_LOG 2026-09-25: „the enwiki point, with Errington 2017 / Ball and Gardin 1982 placing
  the stupa within that arcminute cell 2 km south of Jalalabad, is the reading to put before him“. Gespeichert ist
  33.66801142959909, 70.95519786406209 (in Pakistan); alle Zeugen liegen rund 95 km entfernt bei Jalalabad.
- **Entscheidung:** den Artikel-Punkt 34.412045, 70.45213 schreiben. O6 deckt das, der Punkt ist belegt.
- **Ausführung: WD1** (3 Zellen an `786cada5-1feb-4c5c-9e79-b8ffdf8aacc6`; Belege: enwiki oldid 1366870556, Zenodo
  3355036). **Owner nötig: nein.**

### Nr. 7 – Chiapa de Corzo / Zoque Culture Archaeological Zone
- **Empfehlung/Messung:** Nr. 7 nennt als ersten Weg: Chiapa de Corzo ausblenden (`duplicate_of:ed186ea9…`) und die
  Zoque-Zeile in „Chiapa de Corzo“ umbenennen; beide Überlebensregeln behalten die Zoque-Zeile. Die Punkte liegen
  unverändert 7,4 m auseinander. Chiapa (`24aa135d…`) hat 0 Links, 0 Bilder, keine ID; Zoque hat 3 Links, 20 Bilder und
  Q4384315.
- **Entscheidung:** eine Stätte, Richtung wie empfohlen. Der Slug löst über die 8-Hex-ID auf
  (`sites_html.site_detail`): Die umbenannte Seite antwortet mit 301, die ausgeblendete mit 410.
- **Ausführung:** Ausblenden in **WD2** (2 Zellen, 20. Dubletteneintrag); Umbenennen als eigene Aktion über die
  Namens-Lane aus L5 (2 Zellen). **Owner nötig: nein.**

### Nr. 8 – Lokale Kopien gelöschter Commons-Dateien
- **Empfehlung/Messung:** keine Empfehlung („the owner's“, AUDIT_LOG 2026-09-25, Dedan). Die Bildzeilen 70233, 80453,
  87351, 87352, 97070 und 107331 sind `is_excluded`, nichts zeigt mehr auf sie. Die Dateien liegen root-eigen auf dem
  VPS und sind per URL erreichbar. Fünf hat Commons als Urheberrechtsverletzung gelöscht, eins ist ein Werbefoto.
- **Entscheidung:** löschen. Kein Teil des Produkts verweist auf sie, und die DB- und Journalzeilen bleiben als Beleg.
- **Ausführung:** VPS-Schritt (`deploy` ist in der Gruppe `docker`). Danach muss
  `/data/images/wiki/9a9a0dca/hero.webp` mit 404 antworten. **Owner nötig: nein.**
  ```
  docker run --rm -v /var/www/ancientnerds/public/data/images/wiki:/w alpine sh -c '
    rm -v "/w/403e3c53/Infopanel hardloopbaan Olympia.webp" \
      "/w/75374382/Athens Acropolis Stoa of Eumenes II (28437052525).webp" \
      /w/9a9a0dca/Dedan_tomb_1.webp /w/9a9a0dca/hero.webp \
      "/w/cb039044/Athens Acropolis Sanctuary of Dionysos Eleuthereus (28154647030).webp"
    find /w/fe252099 -maxdepth 1 -name "A Minecraft Movie McDonald*s promotion - 3 May 2025.webp" -print -delete'
  ```

### Nr. 9 – Elf Namensschlüssel auf sechs Lyra-Sites
- **Empfehlung/Messung:** keine Empfehlung. Die Ursache ist behoben (`370babf`); die Lane ist geprobt, ihr Wächter 1
  lässt aber nur `ancient_nerds` zu. Heute weichen genau 11 `unified_site_names`-Zeilen ab: ids 3616643, 3616936,
  3616938, 3617031, 3617034-3617036, 3617283, 3617346, 3617349, 3617350.
- **Entscheidung:** reparieren. Ohne den abgeleiteten Schlüssel findet die exakte Suche die Sites nicht; es gibt kein
  DELETE.
- **Ausführung:** Code-Änderung in `scripts/remediation/name_key/`, die `lyra` nur für diese Zeilen zulässt, dann die
  journalisierte Lane mit 11 Zellen `name_normalized`. **Owner nötig: nein.**

### Nr. 10 – Die versiegelten Abnahme-Schwellen
- **Empfehlung:** Einwände nur vor dem Ziehen.
- **Entscheidung:** **durch O1 überholt** („Keine Abnahme mehr“). `draw-2026-09-25b` ist nur noch eine Messung, die
  V3-Sperre fällt, eine Schwelle gibt es nicht mehr.
- **Ausführung: WF** (Fehlerquoten je Feld, nur berichtend). **Owner nötig: nein.**

### Nr. 11 – Shorts-Ledger und die 16 alten Shorts
- **Empfehlung/Messung:** keine Empfehlung. Phase 6 Item 5: nichts veröffentlicht, die 16 sprechen die alten Karten,
  das Gate S13 lässt sie nicht durch.
- **Entscheidung (O2-O4):** zurückziehen, denn die alten Karten sind zu 18 von 43 schwer falsch. Neu gerendert wird mit
  der WB-Karte; der neue Render schreibt das Ledger selbst (`pipeline/video/shorts_ledger.py`), der Nachtrag entfällt.
- **Ausführung:** nur Dokumentation. Den Batch-Start behält der Owner nach der Shorts-Regel vom 17.09. („Batch nur mit
  Go“); er braucht dafür nichts, was nur er hat. **Owner nötig: nein.**

## D. Phasen 4 und 5

### D4 – SEO-Risiko (Wikipedia-Wortlaut)
- **Empfehlung:** „gelesen“, dazu „14 Tage nach der Pilot-Schreibung prüfe ich die Pilot-Kohorte mit
  `scripts/gsc_report.py` (inspect)“.
- **Entscheidung:** zur Kenntnis genommen; die Prüfung findet statt, auch für WAs ~2.700 neue Wikipedia-Seiten.
- **Ausführung:** Lese-Aktion ab **2026-10-08**: `gsc_report.py inspect <URL>` für die 97 P4-Sites vom 2026-09-24
  (Journal `phase4:%`, `description`, `applied_at < '2026-09-25'`); für WAs Sites 14 Tage nach ihrem letzten Schritt.
  Der Schlüssel `secrets/gsc-key.json` ist vorhanden. **Owner nötig: nein.**

### D6 – Halteliste Phase 4 (620 Beschreibungen, 265 Karten, 19 zu frische Revisionen)
- **Empfehlung:** „so lassen oder Quelle nennen“; REPAIR_TEXTS §4: „Supersedes … D6“.
- **Entscheidung:** durch O5 und O2-O4 überholt. Was WA nicht ersetzt, prüft WC Satz für Satz; alle Karten werden neu
  geschrieben. Die 19 laufen ab 2026-09-26T21:30Z in WA, denn mit O1 ist die V3-Sperre aufgehoben.
- **Ausführung: WA → WC → WB.** **Owner nötig: nein.**

### D7 – Alttexte ohne beweisbare Herkunft
- **Empfehlung/Messung:** REPAIR_TEXTS, Klasse H6: „keep, listed for the owner (origin not provable)“. Heute tragen 14
  sichtbare Beschreibungen kein `_description_provenance`; Lane L nannte 17.
- **Entscheidung (O5 statt „behalten“):** Satz für Satz prüfen und kürzen. Die Provenienz lautet „Herkunft unbelegt,
  satzweise geprüft“, eine März-KI-Herkunft wird nicht behauptet.
- **Ausführung: WC**, vorher WA, wo ein Artikel existiert. **Owner nötig: nein.**

### D8 – 876 statt 904 ungegroundete Karten
- **Empfehlung:** „nichts, wenn 876 gilt“.
- **Entscheidung:** 876 gilt; mit O3 („Alle Karten neu“) ist die Frage gegenstandslos.
- **Ausführung:** nur Dokumentation. **Owner nötig: nein.**

### D10 – März-Texte außerhalb des Defekt-Scopes, Teil 2
- **Empfehlung:** Karten „(a) leeren“, Beschreibungen „(b) prüfen und kürzen“.
- **Entscheidung:** Für die Beschreibungen gilt (b) wie empfohlen, das ist O5. Für die Karten ersetzen O2-O4 die
  Variante (a): Alle ~4.900 Karten werden belegte Teaser mit 160-190 Zeichen; geleert wird nur, was nach zwei
  Umschreibungen nicht besteht.
- **Ausführung: WC** (Beschreibungen), **WB** (Karten); Teil 1 ist WA. **Owner nötig: nein.**

## Als erledigt markiert, aber von O1-O11 berührt

- **A2** (Export): Teil von WF.
- **A3** („7.761 unbelegbare Felder bleiben“): durch O6 überholt; WD1/WD2 ersetzen belegt oder leeren.
- **D5** (Push #2, `417386f`, live): Jede weitere Kartenschreibung in WB verlangt sofort die neu erzeugte Kartendatei
  und einen Push (WF).
- **C** („kein Push ohne dich“): durch O8 überholt.
- B7-B11, D1-D3 und D9 bleiben entschieden.
