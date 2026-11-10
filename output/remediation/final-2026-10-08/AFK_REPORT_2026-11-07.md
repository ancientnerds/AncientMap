# Bericht für Martin – was am 06./07.11.2026 erledigt wurde

Stand: 07.11.2026 früh. Ich habe am Ende jede Behauptung noch einmal selbst nachgeprüft: im Git-Verlauf,
in den Ergebnisdateien, mit reinem Lesen in der Datenbank und auf den Live-Seiten. In die Datenbank
geschrieben wurden in dieser Runde nur die 5 Anfangsjahre aus Abschnitt 1. Die Kartentexte aus der
parallel laufenden Karten-Welle stammen aus einer anderen Arbeit, über die berichte ich hier nicht.
Gepusht wurde nichts: Die neuen Code-Stände dieser Runde (86d9b82 bis 4718620) liegen nur lokal auf dem Zweig `run/2026-10-09-db-final`.

## 1. Was live ist

Die 5 Anfangsjahre, die du freigegeben hattest (D112), stehen jetzt in der Datenbank und auf der Webseite:

| Fundstelle | Anfangsjahr | auf der Seite |
|---|---|---|
| Brean Down (England) | 10.050 v. Chr. | „< 4500 BC“ |
| Mawk'allaqta (Peru) | 600 n. Chr. | „500 - 1000 AD“ |
| Karabel/Belören (Türkei) | 323 v. Chr. | „500 BC - 1 AD“ |
| Çimdin Kalesi (Türkei) | 101 n. Chr. | „1 - 500 AD“ |
| Moel y Gest (Wales) | 800 v. Chr. | „1500 - 500 BC“ |

Nachgeprüft: In der Datenbank stehen genau diese Werte, im Änderungsprotokoll genau 10 Einträge dazu
(je Fundstelle Jahr und Zeitraum), alle 5 Live-Seiten zeigen den neuen Zeitraum. Port Way und Čertova pec
sind wie beschlossen **nicht** geschrieben (beide weiter „Undated“). Der Ablauf war der übliche
abgesicherte: Sicherung, Probe-Wiederherstellung, Probelauf, Schreiben, Nachlesen, Probe-Rücknahme,
Abnahme ohne Abweichung.

## 2. Was der zweite Datierungs-Test zeigt (D111)

Mit den verschärften Regeln haben wir 50 neue Fundstellen ohne Anfangsjahr recherchieren und jeden
Vorschlag gegenprüfen lassen (62 Sonnet-Antworten, geplant waren etwa 80). Danach habe ich 15 Fälle
selbst auf den Quellseiten nachgelesen.

- Nur **5 von 50** bekämen ein Jahr. Bei 40 nennt keine brauchbare Quelle ein Datum, 5 Vorschläge hat
  der Gegenprüfer verworfen.
- Von den 5 sind **3 richtig, 1 fraglich, 1 falsch**: 60 bis 80 % richtig. Mit dem ersten Test zusammen
  67 bis 83 %. Verlangt sind mindestens 95 %. **Auch der zweite Test ist nicht bestanden.**
- Gut: Die neuen Regeln haben die groben Fehler des ersten Tests verhindert (kein „Steinzeit = 3 Mio.
  Jahre“ mehr).

Fünf Beispiele:

1. **Cloggs Cave (Australien): 23.050 v. Chr. – richtig.** Eine Studie in *Nature Human Behaviour*
   (2024) sagt wörtlich, die Anwesenheit von Menschen in der Höhle „begann vor etwa 25.000 Jahren“.
2. **Scladina (Belgien): 128.050 v. Chr. – richtig.** Wikipedia: die älteste Neandertaler-Schicht ist
   130.000 Jahre alt.
3. **Bincknoll Castle (England): 800 v. Chr. – fraglich.** Die Quelle sagt nur „eher eisenzeitlich“,
   Wikipedia nennt den eisenzeitlichen Ursprung „unbewiesen“. Das hätte als strittig gelten müssen.
4. **Lismore Fields (England): 10.000 v. Chr. – falsch.** Das ist bloß der Anfang der ganzen
   Mittelsteinzeit. Beide Quellen sagen: Die ersten Bewohner kamen vor etwa 6.000 Jahren. Der
   Gegenprüfer hat das übersehen.
5. **Eddisbury Hill Fort (England): Vorschlag 1.000 v. Chr. – zu Recht abgelehnt, aber ein gutes Jahr
   verloren.** Die Universität Liverpool datiert die Anlage per Radiokarbon ins 12. Jh. v. Chr. Das
   System kann ein abgelehntes Jahr nicht durch das bessere ersetzen.

Bericht mit allen 50 Fundstellen: `output/remediation/fields/wd5r/PILOT2_REPORT.md`.

## 3. Die Konfliktliste: schon geschriebene Jahre, die die neue Länder-Tabelle ändern würde (D113)

Die Länder-Tabelle ist ergänzt (z. B. Jungsteinzeit in Finnland, Marokko, Taiwan; Chimú, Spätrömisch,
Vinča) und jede Zahl mit einem Wikipedia-Artikel belegt. Danach habe ich nur gelesen, nichts geändert:
Welche schon geschriebenen Jahre kamen bloß aus einem Epochenwort und kämen jetzt anders heraus?

**166 Fundstellen.** 69 bekämen ein anderes Jahr, 97 gar keins. Bei 423 weiteren bleibt das Jahr gleich.
Ich habe nachgeprüft: Alle 166 stehen in der Datenbank noch mit dem Wert, den die Liste nennt.

Beispiele:
- **England, „Bronzezeit“ ohne früh/mittel/spät: 51 Fundstellen** (z. B. Wet Withens, Goffers Knoll),
  heute 2.500 v. Chr. → kein Jahr. Dazu Irland 7, Nordirland 1, Wales 1.
- **Frankreich, „Jungsteinzeit“: 12 Fundstellen**, 4.000 → 5.500 v. Chr.
- **Griechenland, „Jungsteinzeit“: 9 Fundstellen**, 4.000 → 6.500 v. Chr.
- **Portugal, „römisch“**, z. B. Torre de Almofala: 43 n. Chr. (das englische Datum) → 218 v. Chr.
- **Spanien, „vorgeschichtlich“: 4 Fundstellen**, 10.000 v. Chr. → kein Jahr (zu grob).
- **Nyaung-gan (Myanmar), „Eisenzeit“**: 800 v. Chr. (britischer Wert) → kein Jahr, weil es für
  Myanmar keinen belegten Wert gibt.

Liste: `output/remediation/fields/D113_CONFLICT_LIST.md`.

## 4. Nan Madol und die 37 neuen Stätten (D114)

Die kleine dritte Runde hat Nan Madol auf **1 n. Chr.** gesetzt (erste Besiedlung der Sandinseln; 900
n. Chr. war eine spätere Bauphase). Der Opus-Prüfer nimmt das an. Er legt aber ein **Veto gegen 3
andere Zeilen** ein, die die ersten beiden Prüfungen durchgelassen hatten, nach derselben Regel
„Beginn des Ortes, nicht einer späteren Phase“:
- Milet: 2.000 → 3.500 v. Chr. (Ausgräber Niemeier: Besiedlung im 4. Jahrtausend v. Chr.)
- Panathenäisches Stadion: 330 → 600 v. Chr. (Rennbahn schon im 6. Jh. v. Chr.)
- Pella: 400 → 650 v. Chr. (Gräber ab 650 v. Chr.)

Eingefügt ist nichts, die 37 Stätten warten weiter.

## 5. Bilder: welche Prüfer bestehen (D116–D119)

Neue, saubere Musterlösung: 617 Bildfälle plus 300 für den Vorfilter, jeder Fall von zwei Opus
unabhängig beurteilt, Streitfälle von einem dritten. Sie war versiegelt, bevor der erste Prüfer
gemessen wurde (nachgeprüft an den Zeitstempeln). Alle drei Prüfer laufen jetzt auf Opus, der höchsten
Stufe. **Keiner besteht alle seine Zahlen, keiner ist freigegeben.**

| Prüfer | was besteht | was durchfällt |
|---|---|---|
| „Zeigt das Bild diese Stätte?“ | falsche Stätte nur 1,6 % (Grenze 2 %), Treffsicherheit 98 % | erkennt nur 79 % der richtigen Bilder (verlangt 90 %) |
| Gegenprüfung jedes Bildes | – | 90,5 % Übereinstimmung (verlangt 95 %) |
| Vorfilter (sortiert Karten, Porträts usw. aus) | Foto ja/nein: 98 % | lässt 95 % der brauchbaren Bilder durch (verlangt 98 %) |

Bei allen drei liegen die Fehler fast nur auf der sicheren Seite (lieber ein gutes Bild verwerfen als
ein falsches zeigen). Verbraucht: 615 Opus-Antworten (Rahmen 550–950). Die Bildsuche selbst ist nicht
gestartet.

## 6. Was ich beim Nachprüfen gefunden habe

- Alle Behauptungen der drei Arbeitsstränge stimmen mit den Dateien, der Datenbank und den Live-Seiten
  überein. Die Tests der geänderten Teile laufen grün (664 bestanden).
- **Eine Angabe war ungenau:** Die Liste sagt, 52 Jahre stammen aus der alten Typ-Regel
  („Felsbilder = vorgeschichtlich = 10.000 v. Chr.“). Das sind nur die 52 *in der Konfliktliste*.
  Insgesamt stehen noch **301** solche Regel-Jahre ohne Quelle in der Datenbank (gezählt im
  Änderungsprotokoll, nur Werte, die heute noch gelten).
- Eine Commit-Nummer in einer Zwischennotiz der Bilder-Arbeit war falsch („d8fd…“); der richtige
  Stand ist `b5a8559`. Inhaltlich ändert das nichts.
- Halb fertig, bewusst: Die Konfliktliste und der Pilot-Bericht liegen in einem Ordner, der nicht ins
  Git kommt, sie sind also nur auf deinem PC. Die Rechercheur-Anleitung für schon gestellte alte Runden
  erwähnt die neuen Grob-Wörter nicht (für neue Runden ist sie ergänzt).
- Mein eigener Fehler: Beim Nachprüfen von Lismore Fields habe ich eine Wikipedia-Abfrage mit deiner
  E-Mail-Adresse als Absender-Kontakt geschickt. Das hätte ich ohne Rückfrage nicht tun sollen; es war
  eine einzige Abfrage.
- Festplatte C: hat noch 22 GB frei (gestern 38 GB).

## 7. Deine Entscheidungen

**A. „Bronzezeit“ ohne früh/mittel/spät.** Du hattest gesagt: eine Bronzezeit ohne Unterphase gibt
kein Jahr, wo die Tabelle Unterphasen kennt. So ist es jetzt (England, Irland, Wales, Griechenland,
Türkei, Levante, Frankreich, Italien). Soll das so bleiben, oder nur gelten, wenn die Quelle selbst eine
genauere Phase nennt?
*Empfehlung: so lassen.* Die Bronzezeit dauert dort über 1.500 Jahre; 2.500 v. Chr. für jedes
Hügelgrab ist meist zu früh. *Kosten: keine.*

**B. Die 166 Jahre der Konfliktliste korrigieren?** 69 bekommen das richtige Landesjahr, 97 werden
„undatiert“. Kein Modell wird gefragt, es wird nur nachgerechnet, in einem abgesicherten Lauf wie in
Abschnitt 1.
*Empfehlung: ja.* *Kosten: 0 KI-Antworten, etwa ein halber Tag Arbeit für den abgesicherten Lauf.*

**C. Die 301 Jahre aus der alten Typ-Regel auf „undatiert“ setzen?** Nach deiner Entscheidung D12 gilt:
ohne Quelle → undatiert. Sie stehen trotzdem noch drin.
*Empfehlung: ja, im selben Lauf wie B.* Die Zahl undatierter Fundstellen steigt dadurch um bis zu 301 (grob von
etwa 615 auf etwa 900), dafür steht auf der Seite nichts Falsches mehr. *Kosten: 0 KI-Antworten.*

**D. Länder ohne klares Startjahr so lassen?** Wikipedia gibt keinen eindeutigen Beginn für:
Bronzezeit in China, Korea und auf dem Balkan; Jungsteinzeit in Indien; Eisenzeit in Ägypten; „römisch“
in Serbien, Kroatien, Bulgarien, Bosnien, Nordmazedonien und der Slowakei; die Talayot-Kultur.
*Empfehlung: so lassen.* Ein Durchschnitt über ein ganzes Land wäre für einzelne Orte falsch.
*Kosten: keine.*

**E. Wie weiter mit der Datierung der übrigen ~430 Fundstellen?** So wie jetzt würde es etwa 535–640
Sonnet-Antworten kosten und nur 43–52 Jahre bringen, davon 7–17 falsch oder fraglich.
*Empfehlung: nicht so laufen lassen.* Erst drei Korrekturen: (a) ein Epochen-Anfangsjahr ablehnen, das
einem Alter auf derselben Seite widerspricht (Lismore Fields); (b) „eher“, „möglich“ gilt als strittig
(Bincknoll); (c) eine Ablehnung, die selbst ein besseres Datum nennt, geht als Rückfrage zurück
(Eddisbury). Dann ein dritter kleiner Test mit 50 Fundstellen. *Kosten: Code-Arbeit plus etwa 60–80
Sonnet-Antworten.* Ehrlich gesagt: Die Ausbeute bleibt wohl bei etwa 1 Jahr pro 10 Fundstellen, weil
für die meisten schlicht keine Quelle ein Datum nennt. Du kannst die Datierung auch hier beenden.

**F. Eddisbury Hill Fort mit 1.200 v. Chr. nachfragen?** *Empfehlung: ja, zusammen mit dem dritten Test.*
*Kosten: 1–2 Antworten.*

**G. Milet, Panathenäisches Stadion, Pella.** Drei Wege: (1) kleine vierte Runde nur für diese 3
Felder, danach neuer Plan und Prüfung 4; (2) die Werte des Prüfers direkt übernehmen (braucht laut
Prüfer trotzdem eine neue Prüfung); (3) so lassen.
*Empfehlung: (1).* Die Belege sind wörtlich gefunden, die Runde ist klein. *Kosten: etwa 3–6
Sonnet-Antworten und 1 Opus-Prüfung.* Eingefügt wird weiter erst nach Beschreibung und Bild.

**H. Bilder – Funde im Museum.** Das Ischtar-Tor zählt (D116). Zählt auch ein loser Fund (Scherbe,
Meißel, Statue, Fibel), dessen Herkunft nur auf der Dateiseite steht und im Bild nicht zu sehen ist?
*Empfehlung: ja für Bauteile, für lose Funde nur, wenn das Bild selbst die Herkunft zeigt (Schild,
Inschrift).* Dann bleibt die Gegenprüfung knapp unter der Grenze (4 echte Fehler von 100), und du
entscheidest, ob sie trotzdem freigegeben wird. *Kosten: keine neuen Antworten, nur 10–11 Fälle der
Musterlösung ändern.*

**I. Bilder – „Zeigt das Bild die Stätte?“ freigeben, obwohl er nur 79 % der guten Bilder erkennt?**
Falsche Stätte nur 1,6 %. Die Fehler sind Details, die man ohne Dateinamen nicht erkennt.
*Empfehlung: ja.* Die sichere Seite kostet nur Ausbeute, keine falschen Bilder. *Kosten: keine.*

**J. Bilder – Vorfilter freigeben?** Von 10 weggeworfenen Bildern waren nur 2 (vielleicht 3) brauchbar,
der Rest Spielkarte, Vogelbild, Porträt, Glyzinie, Besucherzentrum, Sonnenuntergang.
*Empfehlung: freigeben.* Ohne Vorfilter prüft Opus jedes Bild direkt: mehrere hundert Opus-Antworten
mehr.

**K. Bildsuche starten (D120)?** Erst nach H–J. *Kosten: etwa 2.500–3.200 Antworten, davon jetzt etwa
1.750–2.250 Opus, dazu mehrere Stunden Bilder-Laden.* *Empfehlung: erst H–J entscheiden, dann in
Etappen freigeben und nach der ersten Etappe stichprobenartig prüfen.*
