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
| B1 | **Namens-/Koordinaten-Fälle** | Ein Wikidata-Name ≠ gespeicherter Name kann ein **Alias** sein — das ist eine Projekt- und Sprachfrage, keine Faktenfrage. | ~~285 Sites~~ — die 285 aus `COST.md:141` sind **reine Koordinatenfälle**; die Alias-Frage betrifft **631 Namensbefunde** (T01). Stand 2026-09-23: siehe Abschnitt „B1/B2 — was die Daten entschieden haben“ | **fast alles mechanisch entschieden** — offen: 46 Namen lesen, 1 Freigabe (17 Koordinaten), Einzelfälle unten |
| B2 | **Land bei grenzwertiger Lage** | `lat/lon` außerhalb des beanspruchten Landes: Grenzfluss, Insel, Gebietsreform — topologisch richtig, inhaltlich falsch. | **117 Sites** (T02), mechanisch eingeteilt: siehe Abschnitt „B1/B2 — was die Daten entschieden haben“ | offen: 3 Länder (Weg: mechanische Lane), 1 Umkehr, `Baltic Sea`, ~15 Koordinaten ohne zweiten Zeugen |
| B3 | **Quelle für Sites ohne Textroute** | Braucht eine Quelle, die kein automatischer Endpunkt liefert. | **17 Sites** ohne Wikipedia/Prosa-Route; 385 ohne enwiki, davon 368 über `source_url` erreichbar; **42 Sites ohne `source_url`** | Quelle nennen oder „keine Quelle möglich" |
| B4 | **Foto-Auswahl (Stichprobe)** | Der Bildprüfer ist **über-inklusiv** bei `site_photo` (gemessen) — nur Augen entscheiden, ob ein Foto die Site zeigt. | Stichprobe der 200 geprüften Bilder + Neuzugänge | Freigabe der Stichprobe |
| B5 | **Stil-/Rubrikgrenzfälle** | „Legend says …", „among the most famous" — Fehler oder erlaubter Ton? Das ist eine Redaktionsfrage. | 3–4 Fälle je Prüfrunde | Regel: Fehler oder nicht |
| B6 | **Löschungen** | Der Plan verbietet `DELETE`. Wenn eine Site ganz weg soll, ist das deine Entscheidung. | unbekannt | Einzelfall-Freigabe |
| B7 | **72 zurückgehaltene Zeilen** | Der Prüfer hat sie freigegeben, aber seine eigene Begründung trägt die Korrektur nicht (z. B. „der gespeicherte Wert ist nicht widerlegt", „der gröbere Typ widerlegt den feineren nicht"). Ich schreibe sie **nicht** — lieber eine Zeile zu wenig als eine unbelegte Zeile in der DB. | **72 von 481** geplanten Zeilen, Liste mit Zitat: `logs/_write_apply/HOLDS.md` | **entschieden 2026-09-21: weglassen** |
| B8 | **4 Zeilen, die die Grenzprüfung abgelehnt hat** | Der Name passt zu einem anderen Ort derselben Schreibweise, die Koordinaten liegen woanders: Lamay (`Mexico→Peru`), San Claudio (`Mexico→Spain`), Soura (`Türkiye→India`) — und Jaffa Gate (`Israel→Palestine`), eine politische Linie, die die Koordinaten nicht entscheiden. | 4 Zeilen | **entschieden 2026-09-21: keine davon schreiben** |
| B9 | **Schreibweise Nordirland** | Die DB hält 1.052 `England` + 118 `Wales` + 83 `Scotland` + **4 `Northern Ireland`** gegen **genau ein** `United Kingdom` — die Konvention des Datensatzes ist das Landesteil. Der Prüfer schrieb 3 Zeilen auf `United Kingdom`; geografisch richtig, aber eine zweite Schreibweise für denselben Ort. | **26 Zeilen** (3 geschrieben, 22 aus dem Zensus, 1 weiterer Treffer) | **entschieden 2026-09-21: `Northern Ireland`** — meine erste Vorlage war falsch begründet, mit der Messung erneut gefragt |
| B10 | **Politische Grenzfälle aus dem Zensus** | Zypern 14, Krim 9, Kosovo 2, Golan 2, Palästina 2 — die Datei `countries.geojson` sagt etwas anderes als der Datensatz, und die Datei ist keine politische Instanz. | **29 Zeilen**, Liste: `logs/_country_mismatches.txt` | **entschieden 2026-09-21: so lassen** |

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
| gespeicherter Name ist ein Name des verlinkten Objekts (Label, Alias oder Sitelink in irgendeiner Sprache: 354; gleich ohne Gattungswörter: 50; beschreibende Form: 67; Transliteration: 37) | **508** | **bleibt**, kein Schreibvorgang |
| der Wikidata-Link selbst ist falsch (Gattungsbegriff wie Q309 „history“: 21; geteiltes Eltern-/Geschwisterobjekt: 43; Objekt ohne Koordinate: 8; Objekt > 5 km entfernt: 5) | **77** | 18 davon hat die erste Reparaturwelle schon korrigiert (angewandt 2026-09-23, 26 Zeilen, heute nachgelesen: 0 Abweichungen). Die übrigen **59** einzeln recherchiert → **Welle 2: 12 Sites / 13 Zeilen geplant**, nicht angewandt (`qid_repair/wave2/`, Vorabprüfung gegen Produktion: 0 Abweichungen); 47 bleiben unverändert, jede mit Begründung |
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
gespeicherte Punkt außerhalb liegt. Zwei Zeugen zählen einmal, wenn `P625` als aus der englischen
Wikipedia importiert belegt ist oder beide exakt derselbe Punkt sind (Petroglyph Beach: beide in Juneau).
Museumsobjekte bekommen den Fundort (`P189`) — aber nur, wenn der gespeicherte Punkt am Museum liegt.

| Ergebnis | alle 488 | davon die 285 |
|---|---|---|
| **versetzen** — Plan fertig, nicht angewandt (Calakmul 907 km, Yenikale 840 km, Temple of Atargatis 459 km, Guyaju 80 km, El Kab, Zempoala, Melgunov Kurgan …) | **17** (51 journalisierte Änderungen: `lat`, `lon`, `geom`) | 11 |
| gespeicherter Punkt = Punkt des Wikipedia-Artikels, nur Wikidata weicht ab — bleibt | 98 | 69 |
| verlinktes Objekt kann nicht für den Punkt sprechen (Ortschaft/Region 115, Linie/Fläche 33, von mehreren Sites geteilt 30, anderer Name 32) — bleibt | 210 | 99 |
| offen: nur ein Zeuge (102), beide Zeugen sind einer (45), Zeugen widersprechen sich (8), kein Zeuge (7), einer stützt den gespeicherten Punkt (1) | 163 | 106 |

Der Plan (`output/remediation/bcases/coords_plan/`) schreibt je Site drei journalisierte Änderungen über
`apply_remediation_change()` — auch `geom`, weil es keinen Trigger gibt und die Umkreissuche auf `geom`
rechnet. Vorabprüfung gegen Produktion heute: **51 Zeilen, 0 Abweichungen**. Pergamonaltar bleibt in
Pergamon (Fundort-Regel), Tayma Stones bleiben offen (Wikidata nennt weder Fundort noch Koordinate).

**B2 Land (117):** 25 politische Linien (B10: so lassen) · 44 Küste/Insel/Grenze (so lassen) · 4 schon
richtig `Northern Ireland` · 22 Irland→Nordirland (**alle 22 inzwischen geschrieben**, UK-Lane) ·
6 falsches Land: 3 geschrieben, **3 offen** (Achladia Deutschland→Griechenland, Delphinion
Griechenland→Türkei, Côa Spanien→Portugal; Weg: eine mechanische Länder-Lane, noch nicht gebaut) ·
3 falsche Koordinate + 12 „braucht Zeugen“: davon 1 versetzt (Yenikale), der Rest offen · 1 kein Land
(`Baltic Sea`).

**Dubletten:** 20 echte Paare (beide Namen sind Wikidata-Namen desselben Objekts, < 2 km) — der Plan
schätzte ~8. Überlebensregel: mehr Content-Links, dann mehr Quellen, dann ältere Zeile, dann die kleinere
ID (reiner Gleichstandsbrecher; bei 7 Paaren entscheidet er). Die Liste für die Scope-Lane:
`output/remediation/bcases/DUPLICATES.jsonl` (`loser_id`, `survivor_id`, `evidence`, 20 Zeilen, keine
Kette). Dazu 13 Punkte, auf denen 36 Sites übereinander liegen (`stacked.jsonl`) — keine Dubletten,
sondern Platzhalterkoordinaten.

**Was nur du entscheiden kannst:**

1. **Die 17 Koordinaten schreiben?** FIELD_CONTRACT §4.6 verbietet automatische Koordinatenänderungen.
   Der Plan erfüllt deine Regel „zwei unabhängige Zeugen“; ein „ja“ genügt, der Orchestrator fährt dann
   Probe, Anwendung und Nachlesen. Folgefall: Temple of Atargatis landet in Syrien, gespeichert ist
   Libanon — das Land muss danach nachgezogen werden.
2. **Dubletten ausblenden:** Darf E4 `retired` (Grund `duplicate_of:<uuid>`) für die 20 Verlierer
   genutzt werden? B6 verlangt die Freigabe je Site — die Liste nennt jede einzelne mit Beleg.
3. **`Baltic Sea`**: welches Land (oder keines) für eine Stätte in internationalen Gewässern?
4. **Ahin Posh Tape**: Phase 3 schrieb `Afghanistan → Pakistan`; die eigene Beschreibung sagt „bei
   Jalalabad, Afghanistan“, der Wikidata-Link ist ein Dorf in Pakistan. Umkehr + Punkt prüfen.
5. **Lesen, kein Rechnen mehr möglich:** 46 Namen (N7), 11 Link-Kandidaten ohne 1-km-Beweis,
   2 widersprüchliche Einträge (+ Tikal aus Welle 1), 5 Dublettenkandidaten aus der Link-Recherche, 163
   offene Koordinaten (Liste mit Grund in `coords.jsonl`).

## C. Grenzen, die auch im autonomen Lauf gelten

* **Kein Push, kein Deploy, kein Versand** ohne dich (A1/A2).
* **Keine Zugangsdaten erfinden**: was nur du hast, wird gefragt, nicht geraten (A3/A6).
* **Keine Prüfung wird aufgeweicht**, damit sie grün wird — auch nicht unter Zeitdruck.
* Nach **zwei gescheiterten Versuchen** am selben Problem: Meldung statt Weiterraten.

## Was der Agent allein macht (zur Abgrenzung)

Zensus, Modellprüfung aller 5.004 Sites über die fünf Felder (Beschreibung, Zeitstellung, Typ, Land,
Kartentext), Korrekturvorschlag **mit Belegzitat**, Quellenabruf, Journal + Rücknahme-SQL je
Schreibung, Backups/Retention, Prüfflotten, Selbstangriff gegen den Auftrag, Abschlussbericht.
