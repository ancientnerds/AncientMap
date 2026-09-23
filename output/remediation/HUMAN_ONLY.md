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
| B1 | **Namens-/Koordinaten-Fälle** | Ein Wikidata-Name ≠ gespeicherter Name kann ein **Alias** sein — das ist eine Projekt- und Sprachfrage, keine Faktenfrage. | **285 Sites**, deren einziger Befund ein Name-/Koordinaten-Mismatch ist (`phase3_pilot/COST.md:141`) | je Site: Name falsch oder Alias? |
| B2 | **Land bei grenzwertiger Lage** | `lat/lon` außerhalb des beanspruchten Landes: Grenzfluss, Insel, Gebietsreform — topologisch richtig, inhaltlich falsch. | **117 Sites** (T02) | Land korrigieren oder Koordinate |
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

## C. Grenzen, die auch im autonomen Lauf gelten

* **Kein Push, kein Deploy, kein Versand** ohne dich (A1/A2).
* **Keine Zugangsdaten erfinden**: was nur du hast, wird gefragt, nicht geraten (A3/A6).
* **Keine Prüfung wird aufgeweicht**, damit sie grün wird — auch nicht unter Zeitdruck.
* Nach **zwei gescheiterten Versuchen** am selben Problem: Meldung statt Weiterraten.

## Was der Agent allein macht (zur Abgrenzung)

Zensus, Modellprüfung aller 5.004 Sites über die fünf Felder (Beschreibung, Zeitstellung, Typ, Land,
Kartentext), Korrekturvorschlag **mit Belegzitat**, Quellenabruf, Journal + Rücknahme-SQL je
Schreibung, Backups/Retention, Prüfflotten, Selbstangriff gegen den Auftrag, Abschlussbericht.
