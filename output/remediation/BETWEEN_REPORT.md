# Zwischenbericht — AncientMap Sites-DB-Sanierung

Stand: 21.09.2026, laufender Massenlauf-Vorbereitung. Geschrieben für Martin, in einfachen Worten.

---

## 1. Die kurze Antwort auf deine Frage

Du hast zwei Mal gefragt, wo wir stehen. Die ehrliche Kurzfassung:

**Nein — es sind NICHT alle 5.004 Sites geprüft.** Bisher wurden 3 Spalten an 2.735 Sites verändert,
und der Prüf-Apparat, der alle 5.004 prüfen *kann*, ist gerade fertig gebaut und wird jetzt zum ersten
Mal im großen Maßstab gestartet.

**Warum das trotzdem viel Arbeit war:** Der Prüfer, der die Sites bewerten soll, musste erst gebaut
werden — mit Kostenmessung, Belegprüfung und Wiederaufsetzbarkeit. Ohne das wäre ein 5.004-Site-Lauf
ein Blindflug über 47 Stunden gewesen.

---

## 2. Was tatsächlich in der Datenbank geändert wurde

Das Journal (`remediation_change_log`) ist die einzige Wahrheit. Es sagt genau:

| Spalte | Zeilen | Sites | Was passiert ist |
|---|---|---|---|
| `unified_sites.country` | 35 | 35 | „Georgia (country)" → „Georgia", „Chile, Easter Island" → „Chile" |
| `wiki_images.is_hero` | 5.438 | 2.719 | Titelbild gewechselt, wo das aktuelle zu klein war |
| `wiki_images.image_kind` | 105 | 16 | Bildart aus alten VLM-Urteilen eingetragen |

**Das sind 3 Spalten. Nicht die 5.004 Sites.** Die übrigen Felder (Name, Beschreibung, Zeitstellung,
Site-Typ, Kartenbeschreibung) hat noch **kein** Modell angefasst.

---

## 3. Was der Prüf-Apparat kann (fertig gebaut)

Das ist der Kern der Arbeit der letzten Stunden. Ich habe einen Läufer gebaut, der pro Site und pro
Feld **eine Frage an DeepSeek stellt**. Für jede Frage:

1. **Belege holen** — Wikipedia, Wikidata, ggf. weitere Quellen, jeweils mit URL gespeichert.
2. **Eine Frage pro Feld** — nicht fünf Werte auf einmal, sonst kann die Antwort nicht zugeordnet werden.
3. **Urteil verlangen + Korrekturvorschlag + Quelle** — genau das, was du wolltest.
4. **Die Quelle prüfen** — der zitierte Satz muss wirklich in den Bytes stehen, die wir geholt haben.

**Gemessene Kosten:** ca. 0,0007–0,0008 $ pro Aufruf. Für alle 5.004 Sites × 5 Felder = 25.020 Aufrufe
≈ **18–20 $**. Die ursprüngliche Planung im Dokument rechnete mit ~350 $. Also etwa 1/20 der Kosten.

**Harte Schranke ist nicht das Geld, sondern die Zeit** — siehe Punkt 5.

---

## 4. Was ich an Qualität gemessen habe (und was nicht gut ist)

Ich habe ein Experiment gebaut, das den Prüfer gegen **bekannte Fehler** laufen lässt (die 24 Fehler,
die das alte Zensus-System übersehen hat, aber ein menschlicher Prüfer gefunden hat).

| Runde | Was geändert wurde | Trefferquote |
|---|---|---|
| 1 | Ausgangsfrage | 5 von 19 = 26 % |
| 2 | Frage umgestellt: erst Beleg, dann Urteil | 8 von 19 = 42 % |
| 3 | Klassen-Vokabular + Schwellenwerte ergänzt | 7 von 19 = 37 % |
| 4 | Schwellenwert-Korrektur (falsch gemacht) | 5 von 19 = 26 % |
| 5 | Jahrhundert-Umrechnung ergänzt | 7 von 19 = 37 % |
| 6 | Korrektur + Quelle verlangt | 7 von 19 = 37 % |

**Ehrliche Einordnung:** 37 % Trefferquote heißt, das Modell findet etwa jeden dritten Fehler, den das
alte System übersehen hat. Das ist besser als das alte System (0 % auf diesen Feldern), aber weit von
„100 % korrekt" entfernt. Wer das anders darstellt, lügt.

**Was dagegen sehr gut ist:** In Runde 6 trugen **alle 13 Korrekturvorschläge** eine Quelle, und
**kein einziger zitierter Satz war erfunden** (0 von 14 Zitaten fehlten in unseren Belegen). Das war
das Risiko, das mich am meisten beunruhigt hat — Modelle, die Quellen erfinden. Es ist gemessen: tun sie hier nicht.

---

## 5. Die harte Grenze: Zeit, nicht Geld

Ein Testlauf über 1 Site dauerte **19 Sekunden** (4 Abrufe + 5 Modellaufrufe).

Hochgerechnet auf alle 5.004 Sites: **etwa 47 Stunden**, wenn er unbeaufsichtigt durchläuft.
Bei 2 parallelen Batches entsprechend weniger — aber der Hauptbremsklotz ist gemessen und
nicht weggeredet: eine einzelne Site (`overpass-api.de`-Belege) ist von diesem Rechner aus
**nicht erreichbar** (TLS-Reset nach 0,077 s). Vom VPS aus geht es. Das ist eine offene
Entscheidung für dich.

---

## 6. Was nur du (Mensch) entscheiden/erledigen kannst

Das steht ausführlich in `output/remediation/HUMAN_ONLY.md`. Die wichtigsten:

1. **Server-Arbeit / VPS-Zugang** — die Belege für Koordinaten sind nur vom VPS aus erreichbar.
2. **Such-Dienst / Schlüssel** — der Code kennt keinen Web-Suchdienst. Für echte Recherche außerhalb
   Wikipedia/Wikidata brauchst du einen Zugang (oder eine Entscheidung, es zu lassen).
3. **Freigabe für den Massenlauf** — 47 Stunden Laufzeit, ~20 $, alles über DeepSeek. Startet nicht
   ohne deine explizite Anweisung.
4. **`MAILTO` für den Backup-Cron** — die nachts laufende Sicherung meldet Fehler an niemanden.
   Das braucht eine E-Mail-Adresse, die nur du hast.
5. **Entscheidung: alle 5.004 oder nur die 1.813 auffälligen?** — das ist die zentrale Frage.
   Siehe Punkt 7.

---

## 7. Die wichtigste Erkenntnis: Der Arbeitsvorrat ist der falsche Ort

Das war der überraschendste Messwert der ganzen Session. Das alte System hat 1.813 Sites als
„auffällig" markiert und einen Arbeitsvorrat daraus gebaut. Dann habe ich gemessen, ob die
bekannten Fehler überhaupt in diesem Vorrat liegen:

- Von **36 Sites**, die der Blindprüfer untersucht hat, liegen **11 (31 %) im Vorrat** und
  **25 (69 %) außerhalb**.
- Von den **24 bekannten Fehlern** liegen nur **5 im Vorrat**.

**Das heißt:** Ein Lauf über die 1.813 „auffälligen" Sites würde die meisten echten Fehler
**nicht erreichen**. Deshalb muss der Lauf über **alle 5.004 Sites** gehen — genau wie du es
angeordnet hast. Der neue Prüfer liest darum die Sites selbst, nicht die alten Befunde.

Das ist auch der Grund, warum die neue Frage mit den Worten beginnt: *„No census check flagged
this site"* — sie prüft bewusst auch die Sites, die das alte System für sauber hielt.

---

## 8. Was gerade JETZT läuft

Zwei Dinge parallel:

1. **Mutationslauf über 54 Fälle** (`bbcda29ce`) — das ist mein Selbsttest des Selbsttests:
   für jede Schutzregel im Code wird geprüft, dass ein Test sie auch wirklich fängt. Ergebnis
   bisher aus früheren Runden: 43/43, 45/45, 46/46, 50/50, 52/52, 53/53 gefangen. Der Instrument
   hat sich dabei selbst verbessert (ein Absturz hinterließ einmal einen Mutanten im Baum — seit
   dem gibt es einen Baum-Integritätswächter).

2. **Vorbereitung des Massenlaufs** in einem Nebenbaum (`git worktree`, damit der Formatierer des
   Editors den Code während des Laufs nicht anfasst). Der Trockenlauf wird gerade gestartet.

---

## 9. Was noch NICHT existiert (Stand dieser Stunde)

Ehrlich benannt, damit du weißt, was fehlt:

- **Der Schreiber** (Stück 6) — die Komponente, die einen bestätigten Befund tatsächlich in die
  Datenbank schreibt. Sie ist **entworfen, aber nicht gebaut**. Ohne sie sammelt der Massenlauf nur
  Vorschläge, er ändert nichts.
- **Die Prüf-Stufe (Reviewer)** — der Entwurf verlangt sie („nur nicht widerlegte Befunde werden
  geschrieben"), der Läufer **verweigert** sie aber für den neuen Discover-Modus. Das ist eine
  bewusste Lücke, die geschlossen werden muss, bevor geschrieben wird.
- **Web-Recherche** — siehe Punkt 6.2.

---

## 10. Alle Commits dieser Sitzung

**77 Commits vor `origin/main`, nichts gepusht.** Ein Push wäre ein Live-Deploy, und das ist deine
Entscheidung. Im Working Tree ist alles gesichert; die Beweisspur liegt zusätzlich auf dem VPS
(`/var/www/ancientnerds/remediation-evidence/`).

---

## 11. Was ich als Nächstes mache (ohne auf dich zu warten)

1. Den Massenlauf über alle 5.004 Sites **starten** — erst Trockenlauf, dann live, mit harten
   Schranken (`--max-calls`, `--max-usd`), damit er nicht unkontrolliert Geld verbrennt.
2. Den **Schreiber** bauen (Stück 6), während der Lauf läuft.
3. Die **Prüf-Stufe** schließen (Reviewer für Discover-Batches).

Was ich **nicht** ohne dich mache: pushen, deployen, den VPS-Zugang selbst einrichten,
Suchdienst-Schlüssel besorgen.
