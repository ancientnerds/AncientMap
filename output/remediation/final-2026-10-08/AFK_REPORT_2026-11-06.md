# Bericht für Martin – was am 06.11.2026 erledigt wurde

Stand: 06.11.2026 abends. Alles unten habe ich am Ende noch einmal selbst nachgeprüft: im Git-Verlauf,
in den Ergebnisdateien und mit reinem Lesen auf dem Server. Was ich behaupte, stimmt. Wo etwas offen
ist, steht es dabei. In die Datenbank der Webseite wurde heute nur eine einzige Sache geschrieben:
die abgebrochene Theo-Anfrage (Punkt 5). Gepusht wurden nur die zwei Archiv-Markierungen (Punkt 6),
kein Code.

## 1. Was erledigt ist

1. **Epochen je Land (D101).** Wenn eine Quelle nur ein Epochenwort nennt („Jungsteinzeit“,
   „römisch“), bekommt die Fundstelle jetzt das Anfangsjahr dieser Epoche *in ihrem Land*. Früher
   galt überall der britische Wert. Beispiel: Jungsteinzeit in Syrien 10.000 v. Chr., in England
   4.000 v. Chr. Römisch in England ab 43 n. Chr., in Spanien ab 218 v. Chr. Jeder Wert ist mit
   einem Wikipedia-Artikel belegt. Nennt die Quelle eine Jahreszahl, gilt immer die Jahreszahl. Für
   ein Land ohne belegten Wert gibt es kein Jahr; es wird nie ein Wert aus einem anderen Land genommen.
2. **Test der Datierung an 50 Fundstellen (D99).** Ergebnis unten in Abschnitt 2.
3. **Neue Prüfung der Bild-Prüfer (D103).** Ergebnis unten in Abschnitt 3.
4. **Die 37 neuen Stätten (D57/D104).** Die zweite Recherche-Runde ist gelaufen. Der Opus-Prüfer hat
   36 der 37 Stätten abgenommen. Nur bei Nan Madol ist er mit dem Anfangsjahr nicht einverstanden
   (siehe Abschnitt 4, Frage F). Palmyra steht jetzt richtig bei 7500 v. Chr. Eingefügt wird
   weiterhin nichts, die Stätten warten wie beschlossen auf Beschreibung und Bild.
5. **Theo-Anfrage afe7c26a (D110)** ist in der Datenbank auf „abgebrochen“ gesetzt. Nachgeprüft:
   Status „cancelled“, Reservierung freigegeben. Pausiert ist jetzt noch 1 Anfrage, abgebrochen 15.
   Kleiner Schönheitsfehler: Das Skript hat sich nach dem richtigen Schreiben selbst falsch geprüft
   und eine Fehlermeldung gezeigt. Die Daten sind richtig, das Skript ist korrigiert.
6. **Alte Zweige (D110)** sind als Archiv-Markierungen auf GitHub gesichert (geprüft: sie zeigen auf
   die richtigen Stände) und lokal gelöscht.
7. **Aufräumen auf dem Server (D107).** Gelöscht: 5 alte Kopien der Programmbibliotheken, ein alter
   Datenbank-Auszug (100 MB), 4 alte Skripte, 2 alte Sicherungsordner. Zusammen etwa 2,1 GB. Der
   Server hat jetzt 72 GB frei. Nachgeprüft: alles weg. Die Ordner `pfps/` und `tts_test/` sind
   **nicht** gelöscht (Frage I).
8. **Externe Sicherung auf deinem PC (D106).** Es wird jetzt nur noch 1 Sicherung auf C: behalten
   statt 2. Es lag ohnehin nur eine da (vom 05.11.), und sie stimmt mit dem Server überein.
   C: hat 41 GB frei.

## 2. Was der Datierungs-Test zeigt

Wir haben 50 Fundstellen ohne Anfangsjahr von Claude recherchieren lassen und jeden Vorschlag von
einem zweiten Claude gegenprüfen lassen. Danach habe ich 15 Fälle selbst auf den Webseiten
nachgelesen.

- Nur **7 von 50** bekämen ein Jahr. Bei 26 nennt keine auffindbare Quelle überhaupt ein Datum.
  17 Vorschläge hat der Gegenprüfer zu Recht verworfen.
- Von den 7 sind nach meiner Prüfung **5 richtig, 1 fraglich, 1 falsch**. Das sind 71 bis 86 %
  richtig. Verlangt hatten wir mindestens 95 %. **Der Test ist also nicht bestanden.**
- Verbraucht: 80 KI-Antworten (Sonnet), etwa 11 Antworten je gefundenem Jahr.

Fünf Beispiele:

| Fundstelle | Vorschlag | Bewertung |
|---|---|---|
| Brean Down (England) | 10.050 v. Chr. | richtig: Jäger hinterließen dort vor etwa 12.000 Jahren Essensreste |
| Karabel (Türkei) | 323 v. Chr. | richtig: genutzt „ab der hellenistischen Zeit“ |
| Port Way (Römerstraße, England) | 43 n. Chr. | fraglich: Die Quelle sagt, die Straße könnte älter sein als die Römer |
| Höhle Čertova pec (Slowakei) | 3 Millionen v. Chr. | **falsch**: Die Quelle sagt nur „Altsteinzeit“, und unsere Tabelle macht daraus den frühesten denkbaren Wert |
| Bant's Carn (Scilly-Inseln) | 2500 v. Chr. | zu Recht verworfen: Die Quelle sagt genauer „mittlere Bronzezeit“, die KI hat das grobe „Bronzezeit“ genommen |

Hauptfehler: Grobe Wörter wie „Steinzeit“ oder „Altsteinzeit“ werden zu absurd frühen Jahren;
schwache Einzelquellen (unbelegte Kurzartikel, Reiseseiten); und es fehlen Epochen in der Tabelle
(Chimú, spätrömisch).

## 3. Welche Bild-Prüfer jetzt bestehen

**Keiner.** Alle drei Prüfer sind durchgefallen, auch die zwei, die schon auf Opus laufen (es gibt
keine höhere Stufe):

- **Vorfilter** (sortiert vorab Bilder aus, die gar kein Foto der Stätte sind), jetzt Sonnet:
  durchgefallen, sogar schlechter als vorher Haiku. Er wirft echte Fotos von Stätten weg.
- **Zeigt-das-Bild-die-Stätte**, Opus: durchgefallen.
- **Gegenprüfung**, Opus: durchgefallen (177 von 200 übereinstimmend, nötig wären 190).

Aber: Ein großer Teil der „Fehler“ sind Fehler in unserer Musterlösung vom 19.09., nicht in Opus.
Dort gelten z. B. Fotos von Quinoa-Pflanzen, einem Strand oder Dorfkirchen als „zeigt die Stätte“.
Außerdem widersprechen sich zwei Regeln bei Museumsstücken (Frage B). Mit korrigierter Musterlösung
würde die Gegenprüfung bestehen (etwa 197 von 200). Echte Opus-Fehler gab es trotzdem, vor allem bei
direkten Nachbarn (ein Stonehenge-Scan wurde für Woodhenge gehalten).

Die eigentliche Bildsuche ist nicht gestartet.

## 4. Deine nächsten Entscheidungen

Kosten in KI-Antworten; „kostenlos“ heißt: nur Programmierarbeit, keine KI-Antworten.

**Datierung**

- **A – Wie weiter mit der Datierung?** (1) Aufhören: Die übrigen 565 Fundstellen bleiben
  „undatiert“, kostenlos. (2) Erst nachbessern (grobe Epochenwörter geben kein Jahr mehr, genauere
  Epoche ist Pflicht, schwache Einzelquellen zählen nicht, fehlende Epochen werden belegt), dann ein
  zweiter Test mit 50 neuen Fundstellen: etwa 80 Antworten. (3) Trotzdem alle 565 machen: 770 bis
  900 Antworten, Ergebnis etwa 65 bis 80 datierte Stätten, davon etwa jede fünfte bis siebte falsch.
  **Empfehlung: 2.**
- **G – Die 5 geprüften richtigen Jahre** (Brean Down, Mawk'allaqta, Karabel, Çimdin Kalesi,
  Moel y Gest) über das gesicherte Verfahren in die Datenbank schreiben? Port Way und Čertova pec
  nicht. Kostenlos. **Empfehlung: ja, aber zusammen mit dem nächsten Schritt.**
- **Epochen je Land (D101), fünf kleine Fragen, alle kostenlos:**
  1. Italien: „römisch“ allein gibt kein Jahr (Italien war Roms Kernland, keine Provinz),
     „römische Kaiserzeit“ ab 27 v. Chr. **Empfehlung: so lassen.**
  2. Deutschland, Niederlande, Schweiz: „römisch“ allein gibt kein Jahr, weil die Römer dort zu sehr
     unterschiedlichen Zeiten kamen. **Empfehlung: so lassen.**
  3. Fehlende Länder (z. B. Bronzezeit auf dem Balkan und in China, Jungsteinzeit in Indien und
     Nordafrika) und fehlende Epochen (Chimú, spätrömisch) mit Wikipedia-Belegen füllen?
     **Empfehlung: ja.**
  4. Eine Liste der schon geschriebenen Jahre, die nach der alten Regel falsch sein könnten (z. B.
     Jungsteinzeit = 4000 v. Chr. im Nahen Osten), nur zum Ansehen? **Empfehlung: ja, nur die Liste.**
  5. Reicht Wikipedia als Beleg, und bleiben die alten britischen Werte für mittlere/späte
     Jungsteinzeit und Eisenzeit? **Empfehlung: ja.**

**Bilder**

- **B – Museumsstücke:** Zählt ein Foto eines echten Bauteils der Stätte, das heute im Museum steht
  (z. B. Ischtar-Tor in Berlin), als „zeigt die Stätte“? **Empfehlung: ja.**
- **C – Musterlösung mit etwa 40 falschen Einträgen:** (A) Ich korrigiere sie, du bestätigst die
  Liste, ich bewerte die vorhandenen Antworten neu: kostenlos, aber schwächerer Nachweis. (B) Neue,
  saubere Messung: 550 bis 950 Antworten, meist Opus. (C) Prüfer trotzdem freigeben.
  **Empfehlung: B, wenn es billig sein muss A.**
- **D – Vorfilter:** Opus testen (5 Antworten) oder den Vorfilter weglassen (dann wird die Bildsuche
  um mehrere hundert Opus-Antworten teurer). **Empfehlung: Opus testen.**
- **E – „Falsche Stätte“:** Bleibt es bei null erlaubten Fehlern (dann besteht kein Prüfer), oder
  reichen höchstens etwa 2 %, weil danach noch die Gegenprüfung jedes Bild ansieht?
  **Empfehlung: 2 %.**
- Zur Info: Die Bildsuche selbst kostet danach etwa 2.500 bis 3.200 Antworten, davon 1.500 bis 2.000
  Opus, dazu mehrere Stunden Bilder-Laden. Sie startet erst nach deiner Freigabe.

**Neue Stätten**

- **F – Nan Madol (Mikronesien):** Die Recherche sagt 900 n. Chr. (Bau der Steininseln), der Prüfer
  sagt 1 n. Chr. (erste Besiedlung der Sandinseln darunter). (a) Kleine dritte Runde nur für dieses
  Feld: 2 Antworten, kein neuer Code. (b) Den Prüfer-Wert übernehmen: dafür müsste erst Code gebaut
  werden. (c) Nan Madol vorerst herausnehmen, die 36 anderen abnehmen. **Empfehlung: a.**

**Server**

- **I – `pfps/` (1,6 GB, wohl Kartenspiel-Bilder) und `tts_test/` (8 MB):** Sie gehören zum
  Code-Projekt; nur auf dem Server gelöscht, kämen sie beim nächsten Update zurück. (a) Lassen.
  (b) Erst prüfen, ob die Webseite sie braucht, und nur dann per Code-Update entfernen (das geht
  live). (c) Sofort entfernen. **Empfehlung: a.**

## 5. Noch offen, ohne dass du etwas tun musst

- Der Vorfilter-Wechsel auf Opus ist nur notiert, nicht eingestellt (wartet auf Frage D).
- Der große Mutations-Test der Bild-Prüfer lief nicht, weil gleichzeitig ein anderer Lauf im selben
  Ordner arbeitet. Nur die schnelle Vorprüfung lief, sie ist in Ordnung.
- Die alte, gescheiterte Datierungs-Automatik nutzt noch die alte Epochentabelle. Sie wird durch den
  neuen Weg ersetzt und wurde deshalb nicht angepasst.
- Der Pilot-Bericht mit allen 50 Fundstellen liegt in
  `output/remediation/fields/wd5r/PILOT_REPORT.md` (nicht in Git, weil der Ordner ausgenommen ist).
