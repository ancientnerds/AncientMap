# Bericht für Martin – AFK-Lauf ab 05.11.2026 (Wellen 1 und 2)

Stand: 07.11.2026 (Endprüfung). Ich habe jede Behauptung unten selbst noch einmal nachgeprüft, und zwar nur
lesend: Git-Verlauf des Zweigs `run/2026-10-09-db-final`, das Änderungsprotokoll `remediation_change_log` in der
Produktionsdatenbank, die Ergebnisdateien und die Live-Seite. Gepusht wurde nichts. Was danach am 06./07.11.
passiert ist (D99–D120), steht in `AFK_REPORT_2026-11-06.md` und `AFK_REPORT_2026-11-07.md`.

## 1. Was live ist (nachgeprüft)

Nachgezählt im Änderungsprotokoll (Zeilen je Lauf, Sites in Klammern). Jeder Lauf ging über den üblichen
abgesicherten Ablauf: Sicherung, Probe-Wiederherstellung, Probelauf, Schreiben, Nachlesen, Probe-Rücknahme und
Abnahme ohne Abweichung.

| Lane | Lauf | Journal-Zeilen | Was |
|---|---|---|---|
| D14 Teil A | `2026-11-05_mechanical-dup-merge-move` | 28 Links (11) + 24 Namenszeilen (12) = 52 | Links und Namen stillgelegter Duplikate sind zum Überlebenden umgezogen |
| D14/D25 | `2026-11-05_mechanical-card-stats` | 8.392 (2.083 Karten) | card_stats neu berechnet |
| D48/D49 | `hero-moves-2026-11-06-001` | 19 `wiki_images.is_hero` + 3 `thumbnail_url` = 22 (16) | Titelbilder gewechselt |
| D79 Welle a1 | `wb-teaser-prov/card-s041..s043` | 41+41, 35+35, 42+42 | 118 neue Kartentexte |
| D81/D25b | `phase4wc:p4wc-4400..4403` | 40+40+40+6 = 126 (63) | Beschreibungsfehler der a1-Sites repariert |
| D81 Karten | `wb-teaser-prov/card-s044` | 19+19 | 19 Karten für die reparierten Sites |

Was ich zusätzlich geprüft habe:
- **Nachlesen der Titelbilder:** Alle 22 Werte stehen heute noch so in der Datenbank. Keine dieser Sites hat zwei
  Titelbilder.
- **Abnahme-Belege:** `mechanical_teaser/ACCEPTED/step-041..044.json` und
  `logs/_write_apply_p4wc/ACCEPTED/step-0013.json` (Ergebnis 0 Abweichungen) liegen vor. Für D14 und card_stats
  liegen die `08_verify_after.txt` vor (0 Zeilen außerhalb der Lane). Für die Titelbilder gibt es keine eigene
  Abnahme-Datei, die Abnahme lief nur auf dem Bildschirm. Deshalb habe ich sie oben selbst nachgelesen.
- **Statischer Export ist frisch:** `index.json` hat `exported_at` 07.11. 06:01 UTC. Der letzte Schreibvorgang war
  um 05:58 UTC. Die neue Kachel von Carranque liegt im Export.
- **5 zufällig gezogene geänderte Sites live auf ancientnerds.com**, alle mit dem neuen Stand:
  - Townleyhall Passage Grave (Irland): neue Beschreibung, auch im Export `details/europe.json`
  - Thul Hairo Khan (Pakistan): neue Beschreibung
  - Carranque (Spanien): neues Titelbild `Carranque.webp`, HTTP 200
  - Welbeck Hill (England): neuer Kartentext, auch in `index.json`
  - La Corona (Guatemala): neuer Kartentext
- **Server-Cron (O9):** Neu eingetragen ist `20 1,2 * * 1 /home/deploy/story_backbone_cron.sh`; die zwei
  Sicherungszeilen sind unverändert. Der erste echte Start ist Mo 09.11. um 00:20 UTC. Zurzeit läuft der Backbone
  nicht; das Log endet mit dem Quota-Stopp vom 27.10.
- **Code-Stände, alle auf dem Zweig, keiner gepusht:**
  - 78aafa2, 292c2b8: D70-Extraktor
  - f08a7d2: Messergebnis. Der Bericht der Spur nannte dafür „70f8ebe“; diese Kennung gibt es nicht, f08a7d2 ist
    der Stand mit diesem Inhalt.
  - 4b74445, 34960bb: Prüfanweisungen der Lane WC
  - 9ad2fb1, 06f840e, f214633: Karten-Welle a1
  - 58ff652: D14
  - 69b1909: Opus-Prüfung der Titelbilder
  - a70e106: Mikronesien in der Länderprüfung
  - 03f6ffe: Offsite-Aufgabe im Projektwissen
- **Nichts läuft halb:**
  - Lokal läuft kein Python-Prozess, also auch kein Hintergrund-Abruf.
  - Kein geschriebener Schritt ist ohne Abnahme.
  - Jede beantwortete Modellrunde ist importiert. Bewusst offen sind nur die unten genannten Punkte.

## 2. Was vorbereitet, aber nicht geschrieben wurde, und warum

1. **D70-Datierungs-Extraktor: am Tor durchgefallen, nichts geschrieben.** Die versiegelte Gold-Runde wurde genau
   einmal gemessen. Ergebnis: 70,3 % richtig (102 von 145; Intervall 62,5–77,2 %), verlangt sind 95 %. Die
   Infobox liegt bei 29 von 31 richtig, ein Epochenwort allein nur bei 44 von 81 (54 %). In der Stichprobe von 30
   Zellen waren nach Mehrheit der drei unabhängigen Prüfer 26 falsch (die Prüfer zählten 26, 29 und 26). Erlaubt
   war höchstens 1.
   Die Fehlerarten:
   - „römisch“ ergab überall 43 n. Chr., also das britische Datum. Beispiel: Siponto, wo das Zitat selbst 189 v. Chr.
     nennt.
   - Epochenwörter wurden in Ortsnamen und gewöhnlichem Text gefunden: „Wari“ in Wari Willka, „geometric shapes“ bei
     Dighton Rock.
   - Das Ende einer Spanne wurde als Beginn gelesen: Rockbourne 401, Huaca Casa Rosada 1438.
   - Zitate handeln vom Nachbarort oder von der Region: Vergilgrab, Lilaia.
   - Vorsichtige Formulierungen und Obergrenzen wurden als Beginn übernommen: Alyscamps „4. Jh. oder früher“.
   - Ein zusätzlich gefundener Fehler: Bei „432&nbsp;BCE“ in der Infobox geht das Vorzeichen verloren (Heraclea
     Lucania wird +432).

   Die 615 Sites bleiben „Undated“. Inzwischen hast du mit D99/D101/D111–D113 einen anderen Weg gewählt, siehe die
   späteren Berichte.
2. **D57, 37 neue Stätten:**
   - Recherche und Plan sind fertig: 983 geplante Journal-Zeilen.
   - Nicht eingefügt, nach O4: Es fehlen noch Beschreibungen (WN), Bilder (D17) und ein Einfügeschritt für card_stats.
   - Die Opus-Prüfung hatte zunächst 6 Vetos eingelegt: Merv, Mesa Verde, Palmyra, Nan Madol und Pantheon wegen des
     Startjahrs, Thermopylae wegen der Koordinaten.
   - Danach ist die zweite Runde gelaufen (D104, siehe Bericht vom 06.11.). Jetzt sind 36 von 37 abgenommen, offen
     ist nur Nan Madol.
3. **D80, Prüfer-Kalibrierung der Lane WC:**
   - wc-wv-1o ist von dir freigegeben (D80).
   - Die 6 Streitfälle des Pilot-Judge sind von Opus entschieden: 3 Mal lag die Rolle richtig, 3 Mal die Musterlösung.
   - Die Prüfanweisungen sind geschärft.
   - Neu versiegelt und gemessen, alle auf Opus und ohne eine einzige falsche Quelle:

   | Messung | Ergebnis |
   |---|---|
   | fc-1o2 | 0,941, durchgefallen (bekannten Fehler verpasst) |
   | fc-2o2 | 0,855, durchgefallen |
   | fc-3o2 | 0,917, bestanden |
   | wv-1o2 | 0,892, durchgefallen |
   | wv-2o2 | 0,870, durchgefallen |
   | pj-1o2 | 0,913, durchgefallen (der bekannte Fehler Cloghanmore wurde wieder verpasst) |
   | pj-2o2 | 0,897, durchgefallen (2 zusätzliche „falsch“, erlaubt ist 1) |

   Die Rolle Pilot-Judge hat damit keine Freigabe. fact_checker (wc-fc-1o) und wc_web_verifier (wc-wv-1o) behalten
   ihren älteren Stand. Die Karten-Welle a1 nutzt den Pilot-Judge nur als Filter vor dem Schreiben; geschrieben
   wurde nur, was er als sauber beurteilt hat.
4. **Welle a1, nicht geschrieben:**
   - 24 Karten sind nach D81/O7 zurückgehalten; 19 davon wurden nach der Reparatur neu geschrieben (s044).
   - 66 Karten sind nicht judge-sauber. 9 davon scheitern nur, weil web.archive.org unser Netz sperrt (AS 212238,
     HTTP 429) oder cultura.gov.it einen TLS-Fehler liefert.
   - Den Kartentext für das Tienen Mithraeum hat der Judge als widerlegt beurteilt.
   - Leominster beaker burial (eebdcbf3) bräuchte die adversarielle Rolle; die ist für WC nicht kalibriert.
   - Niedertiefenbach S2 ist ein neuer Beschreibungsfehler, der auf eine spätere WC-Runde wartet.
5. **D48/D49, Rest der Titelbilder:**
   - 72 Sites ohne passende Ersatzzeile stehen auf `served_image/hero-moves-2026-11-06b/OWNER_LIST.jsonl`
     (2 Hotlinks, 44 ohne Urheber, 19 Streifen, 8 noch ohne Titelbild).
   - 433 kleine Titelbilder stehen auf `SMALL_HEROES.jsonl`.
   - 3 Sites warten auf D15.
   - Bei 8 geplanten Wechseln hat die Opus-Prüfung ein Veto eingelegt (Nachbildung statt Objekt, Landschaft,
     Zeichnung, kaputte Urheberangabe).
   - Nach D82 wird das alles später in D17 gesucht.
6. **D14 Teil B** ist nicht begonnen: 90 offene Duplikat-Gruppen, etwa 180 Modellantworten. Tarxien und Dodona sind
   nach O5 ausgelassen. Ebenfalls offen: Der Name von Caparra (cf49332c) ist noch kein Alias seines Überlebenden.
7. **O8 Bild-Rollen:** nicht begonnen. Inzwischen ist das als D103/D116–D118 weitergelaufen, siehe die späteren
   Berichte.

## 3. Deine Punkte (mit Zahlen und Beispielen)

- **A. Wie es mit den 615 undatierten Sites weitergeht (D73).** Der Extraktor allein schafft keine 95 %. Die
  Restliste `fields/wd5x/D73_REST_LIST.jsonl` (615 Zeilen) nennt für jede Site den Grund:

  | Grund | Sites |
  |---|---|
  | kein Kandidat | 239 |
  | Sammelobjekt | 126 |
  | Zelle wegen des roten Tors nicht geschrieben | 83 |
  | keine Quelle | 77 |
  | nur vorsichtig formuliert | 68 |
  | widersprüchliche Quellen | 16 |
  | außerhalb des D58-Fensters | 5 |
  | zwei Startangaben in einem Satz | 1 |

  Beispiele:
  - Bayston Hill (Sammelobjekt Dorf)
  - Pumawasi, Anta (Peru, kein Kandidat)
  - Burnt Fen (nur vorsichtig formuliert)
  - Menhir du Camp de César (keine Quelle)
  - King Lud's Entrenchments (Start 793 aus dem Wanderweg „Viking Way“, außerhalb des D58-Fensters)

  Deine späteren Antworten D99/D111 haben das teilweise schon entschieden.
- **B. D72-Konfliktliste:** Bei 433 der 4.294 datierten Sites liest der Extraktor ein anderes Zeitband als das
  gespeicherte (`fields/wd5x/D72_CONFLICTS_SUMMARY.json`). Die häufigste Verschiebung ist 500 v.–1 n. Chr. nach
  1–500 n. Chr. (97 Fälle). Bei 70 % Präzision ist das nur ein Prüfhinweis. In den 5 Beispielen lag der Fehler
  jedes Mal beim Extraktor, nicht bei der Datenbank:
  - Heraclea Lucania: Vorzeichenfehler
  - Ales Stenar
  - Alba-la-Romaine: „römisch“ = 43
  - Sanctuary of Pandion
  - Cave di Cusa
- **C. Pilot-Judge der Lane WC:** Bitte entscheiden, ob du ihn freigibst (wie D80 für wv-1o) oder ob die
  Musterlösung korrigiert wird. Meine Nachprüfung spricht eher für den Judge:
  - Llanfechell: Der Cromlech steht nicht mehr.
  - Aquädukt von Lutetia: Die Fachliteratur nennt etwa 16 km statt 26 km.
  - Guellayhuasin: Die Quelle selbst nennt zwei verschiedene Höhen.

  Ebenso bitte bestätigen, dass für fact_checker und wc_web_verifier der ältere Stand gilt.
- **D. 4 schwache Karten aus der Stichprobe von a1:** 10 Karten geprüft, 6 halten, 4 sind schwach, keine ist
  widerlegt. Die schwachen:
  - Banwolseong: „Halbmond“, nicht „Mondsichel“
  - Rudna Glava: Das Feuersetzen ist umstritten, steht aber als Tatsache da.
  - Nakhchivan: „canyon“, wo die Quelle „dere“ sagt
  - Seahenge: Der Eingang ist überzeichnet.

  Sollen diese 4 neu geschrieben werden? Und willst du nach D79 die Wellen a2–a4 freigeben? Kosten siehe Abschnitt 4.
- **E. web.archive.org sperrt unser Netz**, lokal und vom VPS aus (AS 212238 Datacamp, HTTP 429). Warten hilft
  nicht. Dadurch fallen 9 Karten durch. Soll ein anderer Zugang eingerichtet werden, oder bleiben die Karten liegen?
- **F. Adversarielle Rolle für WC kalibrieren?** Nötig für Leominster (eebdcbf3) und künftige Fälle, bei denen ein
  Beschreibungsfehler behalten wurde.
- **G. card_stats nach Datierungswellen:** Die 8.392 neu berechneten Werte stammen fast ganz aus früheren Lanes
  (727 Karten haben die Seltenheitsstufe gewechselt; Rücknahme über ROLLBACK.sql). Nach jeder Datierungswelle
  braucht es eine weitere card_stats-Welle.
- **H. Sicherungen auf dem VPS:**
  - Die zwei d14a-Sicherungen vom 05.11. sind inzwischen weg.
  - Neu liegen dort `2026-11-07_a1-s041`, `2026-11-07_a1-wc4400` und `2026-11-07_a1-s044` mit je etwa 885 MB.
    Der automatische Prune erfasst sie nicht, weil er nur `<datum>_remediation` löscht. Bitte löschen, sobald sie
    nicht mehr gebraucht werden. Der VPS hat 70 GB frei.
  - Vor dem Wechsel der Titelbilder lief keine frische Sicherung; zurück geht es über chunk-001/ROLLBACK.sql
    (Probe bestanden).
- **I. Periodenwort „Neolithikum“ = −4000 (D57):** Ist durch D101 (Startjahre je Land) erledigt.
- **J. D18-Urheber-Nachpflege:** Sie ist nie in Produktion gelaufen. Deshalb bleiben 44 Sites ohne
  Urheber auf der Liste der Titelbilder.

## 4. Kosten

Gezählt sind Modellantworten über `opus_handoff.py`, alle mit echtem Claude-Stempel. **Output-Tokens wurden in
diesem Lauf nicht erfasst:** Die Übergabe protokolliert keine Token. Ich nenne deshalb keine Zahl.

| Lane | Antworten | Modell |
|---|---|---|
| D70 Extraktor (Bau, Abruf, Messung) | 0 | deterministisch; dazu 3 Prüf-Agenten für die Stichprobe |
| D80 Kalibrierung WC | 86 (6 Streitfälle, fc 30, wv 35, pj 15) | Opus |
| Welle a1, Karten (WB) | 2.177 | Opus |
| D81 Reparatur der Beschreibungen (WC) | 128 | Opus |
| D81 Kartenlauf für die reparierten Sites | 192 | Opus |
| Stichprobe a1 | 1 Agent (10 Karten) | Opus |
| D14 Teil A, card_stats | 0 | ohne Modell |
| D48/D49 Prüfung der Titelbilder | 24 | Opus |
| D57 Recherche und Plan | 37 + 6 + 1 Prüfung = 44 | Sonnet 43, Opus 1 |

Welle a1 insgesamt: 2.497 Antworten für 137 geschriebene Karten, also 18,2 je Karte (WB allein 17,3; der D81-Lauf
allein 10,1). Für a2–a4 (891 Sites) wären bei gleichem Verhältnis grob 7.000–7.500 Antworten zu erwarten.

Der Wikimedia-Abruf lief seriell mit mindestens 1 s Abstand: etwa 4.544 Entities, 2.094 + 2.087 Wikitext-Revisionen
und 7.020 Auszüge. Es gab keinen HTTP-Fehler.

## 5. Wiedereinstieg je Lane

- **D70/wd5x:** Abgeschlossen mit „durchgefallen“ (`fields/wd5x/D70_STEP5_VERDICT.json`). Weiter geht es nur über
  D99/D111 (Lane wd5r), Stand siehe `AFK_REPORT_2026-11-07.md`.
- **D80/WC-Kalibrierung:** Wartet auf Punkt C. Danach entweder `release` für pj, oder die Musterlösung korrigieren
  und neu versiegeln. Die Dateien liegen unter `output/remediation/calibration/wc-*-o2*`.
- **Welle a1:** Fertig. Weiter mit D79 (Freigabe a2–a4), den 4 schwachen Karten (D), web.archive.org (E) und der
  adversariellen Rolle (F). Log: `final-2026-10-08/a1-driver/NOTES.md`. Der nächste WB-Schritt ist s045.
- **D14:** Teil B (90 Gruppen, Tarxien, Dodona, Caparra) braucht Modellantworten und deine Kostenfreigabe.
- **D48/D49:** Fertig (Neuplanung ergibt 0 Sites). Der Rest geht nach D17.
- **D57:** Plan von D104 liegt vor; offen ist Nan Madol. Danach Beschreibungen (WN), Bilder (D17), der
  card_stats-Einfügeschritt und ein neuer Plan mit neuer Prüfung.
- **Betrieb:** Am Mo 09.11. nach 00:20 UTC in `/home/deploy/story_backbone.log` nach der Zeile „weekly cron (O9):
  starting story backbone“ sehen. Push 2b der Besucherklassen bleibt gesperrt bis zur GSC-Prüfung (D77).
