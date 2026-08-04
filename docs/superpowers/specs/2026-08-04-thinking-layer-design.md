# Denkschicht für den Dauerforscher — Design (Ansatz C: Hybride Denkschleife)

**Datum:** 2026-08-04 · **Status:** Spec approved-pending-review, NICHT implementiert
**Vorgänger:** `2026-07-26-permanent-researcher-design.md` (Graph + Feeder + Lanes),
`2026-07-26-full-project-graph-design.md` (11.5K-Nodes-Projektgraph)

## Vision (User)

Der Dauerforscher soll nicht nur „zufällig" forschen, sondern:

1. **erkennen, welches Wissen schon erforscht ist** (lebendes Weltmodell),
2. **Verbindungen finden, die noch keiner sieht** (Synthese-Papers),
3. **eigene prüfbare Hypothesen jagen** (Hypothesen-Runs mit Falsifikation),
4. dabei **keine Echo-Chamber** werden.

Unabhängig vom ENTITÄT-Buch, soll dessen Research aber mitversorgen, wenn es
sauber funktioniert. **Alles muss auf der Knowledge-Seite sichtbar sein**,
damit nachvollziehbar ist, was wann gerade passiert.

## Ist-Zustand (Befund 2026-08-04)

- `pick_next_frontier_topic()` ist eine reine SQL-Score-Formel
  (Signal + 0,5·Eingangsgrad − 2,0 Diversitätsmalus + 0,5·random) — kein LLM.
- Fragen entstehen aus einem statischen Template („What does the evidence say
  about X?…") — Vorwissen über Nachbarthemen fließt nicht ein.
- Der Graph kennt nur `leads_to`-Kanten (Paper→Thema) und Labels/Status,
  keine Inhalte. Kein Mechanismus liest Papers quer (Synthese, Widerspruch).
- Der 11.476-Nodes-Projektgraph (Sites/Kulturen/Personen/Epochen, Status
  `reference`) wird vom Picker vollständig ignoriert.
- **Echo-Risiko aktiv:** `ancientnerds_research`-Adapter liefert Theos eigene
  Papers als Tier-2-Quelle („Reputable") in jeden Run — Fehler können sich
  über Paper-Generationen verfestigen.

## Entscheidungen (User, 2026-08-04)

| Frage | Entscheidung |
|---|---|
| Konvergenz-Ziele | Synthese-Papers + lebendes Weltmodell + Hypothesen-Jagd (alle drei) |
| Autonomie | Voll autonom — Denkschicht queued Runs selbst, Discord informiert nur |
| Echo-Schutz | Provenance-Regel (eigene Papers = Kontext, nie unabhängige Bestätigung) |
| Sichtbarkeit | Alles auf der Knowledge-Seite (Graph + Aktivitäts-Feed + Live-Status) |

## Architektur

Wochenzyklus, passend zum adaptiven End-of-Week-Batch-Gate (6e1869b):
**Mo–Do denken (billig), Fr–So forschen (teuer), danach lernen.**

```
Injectors (stündlich) ─┐
Papers (Qdrant) ───────┤→ [2] Graph-Miner ─┐
Weltmodell ────────────┘        (Mo–Do)     │→ [3] Curator-Agent → Frontier
                                            │       (nächtlich)    (connection/
[6] Feedback ← Paper fertig ← Runs (Fr–So) ─┘                       hypothesis)
```

### 1. Weltmodell — Tabelle `knowledge_claims`

Ein Claim pro Erkenntnis: `text`, `node_id` (Graph-Referenz),
`status` (`established` | `contested` | `refuted` | `open`), `confidence`
(0–1), Provenance (`paper_ids[]`, `external_source_count`), Timestamps.
Befüllt beim Paper-Publish aus den Conclusion-Sections (liegen in Qdrant),
gepflegt vom Curator. **`refuted` bleibt refuted** — widerlegte Thesen werden
nie wieder als offene Fragen gequeued (Langzeitgedächtnis gegen Wiederkäuen).

### 2. Graph-Miner (SQL/Python, kein LLM, Mo–Do)

Verbindungs-Kandidaten aus **Daten statt aus Theos Prosa** (strukturell
echo-sicher):

- **Link-Prediction:** zwei `explored`-Cluster teilen ≥2 Referenz-Nachbarn
  (Kultur/Epoche/Land/Person im Projektgraph), haben aber keine direkte Kante.
- **PostGIS-Kookkurrenz:** erforschte Sites räumlich nah + zeitlich
  überlappend, ohne Verbindung im Graph.
- **Widerspruchs-Detektor:** numerische Konflikte zwischen Claims
  verschiedener Papers (Academic-Lift-Conflict-Detection wiederverwenden).

Output: gescorte Kandidatenliste mit angehängter Struktur-Evidenz.

### 3. Curator-Agent — „Denkstunde" (LLM, nächtlich Mo–Do, Low-Lane)

Budget ~200–500k Tokens/Pass (vernachlässigbar ggü. Runs). Liest neue Papers
seit dem letzten Pass, Miner-Kandidaten und das Weltmodell. Tut vier Dinge:

1. **Claims aktualisieren** (neu/bestätigt/strittig/widerlegt),
2. **Kandidaten kuratieren:** Junk verwerfen, die besten als
   `connection`-Frontier-Nodes anlegen — mit **gezielter Frage am Node**
   („Wir haben X etabliert (P1), Y blieb offen — prüfe Z"),
3. **Hypothesen formulieren** als `hypothesis`-Nodes, falsifikationsorientiert
   („steelman the null hypothesis" ist Teil der Frage),
4. **Denkprotokoll** in `thinking_log` schreiben + Discord-Kurzfassung.

Structured Output (bewährtes Schema-Muster), best-effort wie die Injectors —
ein Fehlschlag killt nie den Feeder-Loop.

### 4. Frontier-Erweiterung

- `research_nodes` + Spalte `question` (Text, nullable) und neue Kinds
  `connection`, `hypothesis`.
- Picker: Kind-Gewichte (Hypothese > Verbindung > Roh-Thema, env-tunable)
  zusätzlich zur bestehenden Score-Formel.
- Feeder nutzt `node.question`, falls vorhanden, sonst das bisherige Template.
- **Slot-Quote: max. 1 von 3 Wochenend-Runs** ist Synthese/Hypothese —
  frische externe Themen behalten die Mehrheit (Anti-Echo-Baustein).

### 5. Provenance-Regel (Echo-Schutz im Run)

- `ancientnerds_research`-Adapter: von Tier 2 auf Kontext-Tier herabgestuft;
  Treffer werden als **[self]** markiert.
- Specialist-Prompts: self-sourced Claims müssen extern re-verifiziert werden;
  eigene Papers zählen nie als unabhängige Bestätigung.
- Verdicts von `connection`-/`hypothesis`-Runs brauchen **≥2 externe
  Tier-1/2-Quellen**, sonst `inconclusive`.

### 6. Feedback-Schleife

Paper fertig → Hypothesen-Outcome (`confirmed`/`refuted`/`inconclusive`) ans
Node + ins Weltmodell, Node → `explored`, betroffene Claims aktualisiert.
Ein `refuted` ist ein Erfolg (Discord meldet es als solchen).

### 7. Sichtbarkeit — Knowledge-Seite

- **Graph:** `connection`/`hypothesis` als eigene Farben + Layer-Chips
  (13→15 Kind-Klassen); Hypothesen-Outcome als Farbzustand
  (offen/bestätigt/widerlegt).
- **Focus-Card:** gespeicherte Forschungsfrage, zugehörige Claims (Status,
  Konfidenz, Provenance), verlinkte Papers.
- **Aktivitäts-Feed:** chronologische Timeline aus `thinking_log` +
  Run-Ereignissen — „Denkstunde: N Claims aktualisiert, M Kandidaten,
  K Hypothesen", Run-Starts/-Abschlüsse, neue Frontier-Nodes.
  Endpoint `GET /api/v1/knowledge/activity` (public, gecacht, CC BY).
- **Live-Status:** bestehendes `/api/theo/research/current` (30s-Poll) auf
  der Knowledge-Seite einbinden — sichtbar, an welchem Node Theo arbeitet.

## Datenmodell (neu/geändert)

| Objekt | Änderung |
|---|---|
| `knowledge_claims` | NEU: text, node_id FK, status, confidence, paper_ids[], external_source_count, timestamps |
| `thinking_log` | NEU: pass-timestamp, kind (curator/miner/run-event), summary, details jsonb |
| `research_nodes` | + `question` text nullable; kinds erweitert um `connection`, `hypothesis`; + `outcome` für hypothesis-Nodes |
| `research_edges` | neue Kind-Werte (z. B. `connects`, `contradicts`) — Schema unverändert |

Migrationen wie üblich als ALTER TABLE im Orchestrator-Startup (eine
Transaktion, siehe project_lyra_migration_transaction).

## Fehlerverhalten

Miner + Curator laufen best-effort im Feeder-Loop (Muster
`run_all_injectors`): loggen, nie raisen. Claims-/Log-Schreiben transaktional.
`is_junk_label()`-Sperre gilt für alle neuen Node-Insert-Pfade. Curator-Ausfall
degradiert das System auf heutiges Verhalten (Statik-Template, Roh-Frontier) —
kein neuer Single Point of Failure.

## Tests

- Miner-SQL mit DB-Fixtures (Link-Prediction, Kookkurrenz, Konfliktfälle).
- Curator mit gemocktem Structured Output (Claim-Übergänge, Junk-Verwurf,
  refuted-bleibt-refuted).
- Picker-Gewichte + Slot-Quote (Unit, analog test_theo_worker_quota).
- Adapter: Tier-Herabstufung + [self]-Markierung + ≥2-extern-Regel.
- Feed-Endpoint: Cache + Shape.

## Nicht-Ziele (Phase 1)

- Keine neue Embedding-Infrastruktur (Qdrant existiert).
- Keine Änderungen an der Convergence-Pipeline-Interna jenseits
  Prompts/Adapter-Tier/Verdict-Regel.
- Kein eigenes Weltmodell-UI jenseits der Knowledge-Seite (kein Admin-Panel).
- Keine Änderung am Batch-Gate/Budget-Modell (6e1869b bleibt wie es ist).

## Offene Punkte (vor Implementierung klären)

1. Claim-Extraktion beim Publish: eigener kleiner LLM-Call oder Teil des
   bestehenden Gate-Passes? (Kostenfrage, vermutlich Gate-Pass.)
2. Genaue Kind-Gewichte + Kandidaten-Cap pro Denkstunde (Vorschlag: max. 5
   neue connection-Nodes/Pass, damit die Frontier nicht flutet).
3. Discord-Format der Denkprotokolle (eigener Webhook-Kanal?).
