# Abschluss-Programm – Stand

Entscheidungen: `output/remediation/OWNER_DECISIONS_2026-10-08.md` ab D139. Nur Fable 5.2 (D153), keine Messläufe (D154), kein Wochenlimit (D155), alles ohne Halt (D156). Fahrplan je Block: `drivers/<block>/PLAYBOOK.md`.

Zustände: `offen`, `läuft`, `done`, `blocked` (mit Grund).

| # | Block | Zustand | Stand |
|---|---|---|---|
| 0 | Fable-Umbau im Code | done | Commit 2bc9aab, live auf main seit 11.11. (7e4bee2); 4 nicht dringende Prüfbefunde werden nachgezogen |
| 1 | Beta-Label entfernen (D139) | done | live seit 10.11., Commit 5877741 |
| 2 | Google-Diagramme ohne 7-Tage-Mittel (D150) | done | live seit 10.11.; alte Zweige archiviert, Arbeitskopien gelöscht |
| 3 | 4 schwache Karten neu (D132) | done | 3 geschrieben (Schritt 45); Banwolseong behält seine Karte, Quelle nicht erreichbar |
| 4 | Karten Etappe 2 (a2) | done | 138 neue Karten live (Schritte 46-49: 125 + 13 nach Reparatur), 60 Beschreibungen repariert (WC-Schritt 14), Export geprüft, 0 Abweichungen |
| 5 | Karten Etappen 3 und 4 (a3, a4) | gestrichen (D158) | – |
| 6 | 37 fehlende Stätten (D143) | gestrichen (D158) | Recherche und Plan bleiben liegen |
| 7 | Bilder (D17, D15, D59) | gestrichen (D158) | – |
| 8 | Duplikate Teil B (D144) | done | 12.11.: 29 Duplikate stillgelegt, Bilder/Namen/Links auf 7 Hauptstätten umgezogen (u. a. Tarxien, Dodona je 20 Bilder), Kartenwerte neu, Export geprüft, 0 Abweichungen |
| 9 | Zeitrahmen-Prüfung (D20) | done | 12.11.: 47 Stätten entschieden (12 stillgelegt, 35 bestätigt, die 5 wartenden erledigt), 22 Anfangsjahre korrigiert, Kartenwerte neu, Export geprüft, 0 Abweichungen; 11 Fälle auf der Owner-Liste |
| 10 | Textprüfung beenden + 141 Fehler | läuft | 13.11.: mass-05 (143), mass-04 (489) und mass-03 (487) geschrieben, je 0 Abweichungen; läuft: Fehlerliste defects-2026-10-02 (91 Prüfungen), danach 9 ungeprüfte Alttexte (O28) |
| 11 | 40 Stätten ohne Text (WN) | offen | Streitfälle gestrichen (D158) |
| 12 | Dünne Texte anreichern | gestrichen (D158) | – |
| 13 | Namen + „gehört zu“ | gestrichen (D158) | – |
| 14 | Moderne Stadt statt Stätte (D13) | gestrichen (D158) | – |
| 15 | Google: Messung und Vorschlag (D141) | done (Teil O22) | Live seit 11.11. (7e4bee2), nachgeprüft: Mini-Länderseiten, Ortsseiten ohne Text und neue Stories tragen ein noindex nur für Google; Story-Quellen ohne Suchtreffer-Auszüge; alte Sitemap entfernt. Beim Owner: alle Stories (1B, Anfang Dezember), Ortsseiten-Aufbau (2), Über-uns-Seite (4). Vorschlag: `output/seo-audit-2026-11-10/PROPOSAL_D141.md` |
| 16 | Abschluss (Phase 8), Aufräumen, Schlussbericht | offen | nach den Blöcken |

## Code, der parallel gebaut wird

Stand 11.11.: fertig gebaut und gegengeprüft sind A1, A2 (37 Stätten: verstecktes Einfügen, Kartenzeile, Text- und Bild-Lanes), B1 (Duplikate), B2 (Zeitrahmen X13), C1 (Google-Maßnahmen, im Rollout). Der Fable-Limit-Stopp hat A3 und B3 unterbrochen; Rest neu gestartet (wf_e1b054f4-b93). Gegenprüfung des Fable-Umbaus: 4 Befunde, keiner dringend (ein alter Modellname ließe sich über einen Seitenweg noch aufzeichnen; zwei alte Briefe nennen Sonnet), werden nachgezogen.

Workflow build-gaps (wf_ef9de7c7-f04), drei Spuren in eigenen Arbeitskopien (`.worktrees/build-a`, `build-b`, `integrate`): 37 Stätten und Bilder (A1-A7), Duplikate, Zeitrahmen, Streitfälle, Abschluss, Stadt/Stätte (B1-B10), Google-Maßnahmen (C1). Liste der Lücken: `drivers/CODE_GAPS.md`. Eingespielt wird zwischen den Blöcken.

Nach D158 (schlanker Abschluss): etwa 2.000 Antworten, 3-4 Tage Laufzeit.

## Verbrauch (Fable-Antworten je Block)

Wird nach jedem Block ergänzt.

## Laufwerk C:

10.11. abends: 29 GB frei, nachdem die drei alten Arbeitskopien gelöscht sind. Unter 10 GB wird angehalten.
