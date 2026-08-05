# Wahrheitsfindungs-Frameworks für den Dauerforscher (v2-Referenzrahmen)

**Datum:** 2026-08-05 · **Status:** Analyse/Backlog — keine Implementierung
**Anlass (User):** „Die Vorteile unseres Wissens machen es auch komplizierter,
die Wahrheit zu kennen. Gibt es Frameworks, um die Wahrheit zu finden?"

## 1. Das Kernproblem, präzise benannt

Mehr Wissen erschwert Wahrheitsfindung aus drei Gründen, die alle unseren
Agenten direkt betreffen:

1. **Korrelation statt Unabhängigkeit.** 2.456 Quellen in einem Gila-Run
   klingen nach viel Evidenz — aber wenn 40 davon letztlich EINEN
   Grabungsbericht von 1968 paraphrasieren, ist es EIN Evidenzstrom.
   Zählen ist nicht Wiegen. Genau das meint der User-Satz.
2. **Kaskaden.** Sekundärliteratur zitiert Sekundärliteratur; Fehler
   propagieren und sehen dabei immer bestätigter aus (Zitations-Kaskaden,
   „Woozle-Effekt"). Unsere Echo-Chamber-Abwehr behandelt bisher nur die
   SELBST-Referenz — nicht die Fremd-Kaskade.
3. **Auswahlffekte.** Was publiziert/gefilmt/ausgegraben wurde, ist nicht
   neutral gesampelt. Abwesenheit von Evidenz in einem verzerrten Korpus
   ist schwache Evidenz für Abwesenheit.

## 2. Die Frameworks (je: Kern → Bedeutung für Theo)

### Popper & Mayo — Falsifikation und Severity
Kern: Eine These bewährt sich nur durch STRENGE Tests — Tests, die sie
wahrscheinlich bestanden hätte, wäre sie falsch, sind wertlos (Mayos
Severity-Kriterium). ✅ Teilweise gebaut: Hypothesen-Runs sind
falsifikationsorientiert, refuted ist terminal und ein Erfolg.
→ Lücke: Die Denkstunde prüft nicht, ob ein „confirmed" aus einem strengen
Test stammt oder aus einem Test, der gar nicht scheitern konnte.

### Bayesianische Epistemologie — Credence statt Wahr/Falsch
Kern: Überzeugungen sind Grade (0–1), Updates folgen der Likelihood-Ratio:
Wie viel wahrscheinlicher ist diese Evidenz, wenn die These stimmt, als
wenn nicht? Zwei kritische Korollare: (a) korrelierte Evidenz darf nicht
mehrfach zählen; (b) außergewöhnliche Thesen brauchen außergewöhnliche
Likelihood-Ratios (Priors aus Basisraten — die meisten „verbotene
Archäologie"-Claims der letzten 100 Jahre lösten sich auf).
→ `knowledge_claims.confidence` IST eine Credence — aber heute ohne
Update-Disziplin. Der Curator-Prompt kann Likelihood-Denken erzwingen.

### Heuer — Analysis of Competing Hypotheses (ACH, CIA-Tradecraft)
Kern: Nicht „welche These hat die meiste Bestätigung", sondern: Matrix
aller Thesen × aller Evidenz, Fokus auf DISKONFIRMIERENDER Evidenz; es
gewinnt die These mit der wenigsten Evidenz DAGEGEN. Bestätigung ist
billig (fast jede Evidenz „passt" zu fast jeder These), Widerlegung ist
diagnostisch.
→ Perfekt für `contested` Claims: Die Denkstunde könnte pro contested
Claim eine Mini-ACH führen (These A: mainstream, These B: fringe, These C:
Datenfehler) und die Synthese-Frage aus der diagnostischsten offenen
Evidenz generieren.

### Admiralty Code / NATO + ICD 203 — Zwei Dimensionen, normierte Sprache
Kern: Quellen-VERLÄSSLICHKEIT (A–F, aus Track Record) und Informations-
GLAUBWÜRDIGKEIT (1–6, aus Korroboration/Plausibilität) sind ORTHOGONAL —
eine verlässliche Quelle kann Unplausibles berichten und umgekehrt. ICD
203 normiert zudem Wahrscheinlichkeitssprache (almost no chance … almost
certain) und trennt Konfidenz-ins-Urteil von Wahrscheinlichkeit-des-
Ereignisses.
→ Unser Tier 1–4 vermischt beide Dimensionen. Und: Papers sagen heute
nicht standardisiert, WIE sicher ein Verdict ist.

### GRADE (Evidenzmedizin) — Evidenzqualität mit Auf-/Abwertungsregeln
Kern: Startqualität nach Studientyp, dann explizite Modifikatoren:
Inkonsistenz, Indirektheit, Impräzision, Publikationsbias werten ab;
große Effekte, Dosis-Wirkung werten auf.
→ Übersetzt: `external_source_count` ist ein Zähler; ein GRADE-artiger
`evidence_score` würde Replikation (unabhängige Grabungen!), Direktheit
(Primärbericht vs. Doku), Aktualität (Re-Datierungen!) gewichten.

### Historische Quellenkritik — die Domänen-Methode
Kern (seit Droysen/Bernheim): Primär- vor Sekundärquelle; Provenienz
(wer, wann, mit welcher Tendenz?); Nähe in Zeit/Raum; und KONSILIENZ:
unabhängige METHODEN (Stratigraphie + C14 + Typologie + Texte), die
konvergieren, sind der Goldstandard — nicht viele Texte, die einander
zitieren.
→ Für Archäologie ist das das natürlichste Framework. Unsere Tiers
approximieren es grob; die Primär/Sekundär-Achse und die Methoden-
Diversität einer Korroboration fehlen komplett.

### Toulmin — Anatomie eines Arguments
Kern: Claim ← Grounds (Daten) ← Warrant (warum stützen die Daten den
Claim?) ← Backing, plus Qualifier und Rebuttal. Streit ist meist
Warrant-Streit, nicht Daten-Streit („die Mauer ist poliert" ist unstrittig;
„also Hochtechnologie" ist der strittige Warrant).
→ `knowledge_claims` speichert heute nur den Claim-Text. Ein
`warrant`-Feld macht Kontroversen LOKALISIERBAR — der Kern dessen, was
„Mainstream vs. Fringe kontrastieren" seriös macht.

### Tetlock — Kalibrierung und Scoring
Kern: Gute Urteiler sind KALIBRIERT (von ihren „80%"-Aussagen stimmen
~80%), und Kalibrierung ist messbar (Brier-Score) und trainierbar —
aber nur mit Auflösung: Prognosen müssen gegen Outcomes abgerechnet
werden.
→ Wir haben die komplette Infrastruktur bereits: Hypothesen tragen
Curator-Konfidenz UND bekommen Outcomes (confirmed/refuted/inconclusive).
Niemand rechnet sie bisher gegeneinander ab. Das ist die billigste
hochwertige Erweiterung im ganzen Katalog.

## 3. Ehrliche Ist-Analyse der Denkschicht (v1)

Bereits gebaut: Falsifikations-Framing ✓ · refuted-terminal ✓ ·
Selbst-Referenz-Ausschluss ([self], Tier 4) ✓ · ≥2-extern-Floor für
established ✓ · contested-Tracking ✓ · strukturelle (nicht textliche)
Verbindungs-Kandidaten ✓ · Beobachtbarkeit (Feed) ✓.

Was KEIN Framework-Feature ersetzt: das harte Citation-Gate. Der
Gila-Hold (Score 98, gehalten wegen zweier Bracket-Tokens) zeigt die
richtige Asymmetrie: Lieber ein exzellentes Paper halten als eine
unsaubere Zitatkette publizieren (Precision vor Recall bei Integrität).

## 4. Die Lücken → priorisierter v2-Backlog

**R1 — Evidenz-Unabhängigkeit (größter Hebel).** `external_source_count`
zählt Quellen, nicht Evidenzströme. Umsetzung in Stufen: (a) Curator-
Prompt: „Gruppiere Belege nach gemeinsamer Wurzel (gleiche Grabung,
gleicher Autor, gleiche Primärquelle); zähle Wurzeln, nicht Papers";
Schema: `evidence_roots: [string]` pro Claim-Update statt nur Zahl.
(b) Später strukturell: Zitations-Genealogie über DOI-Referenzlisten
(OpenAlex liefert `referenced_works`). Adressiert direkt Kaskaden (§1.2).

**R2 — Kalibrierungs-Schleife (billigster Gewinn).** Nightly-SQL in der
Denkstunde: alle Hypothesen mit Outcome → Brier-Score der
Curator-Konfidenzen, ins thinking_log + Discord („Kalibrierung: 0.18 über
23 Verdicts, Überkonfidenz im Band 0.8–1.0"). Der Curator-Prompt bekommt
seine eigene Kalibrierungskurve als Kontext — ein sich selbst
korrigierender Urteiler.

**R3 — ACH-lite für contested Claims.** Pro contested Claim hält der
Curator die 2–3 konkurrierenden Thesen + die diagnostischste OFFENE
Evidenz („was würde A und B trennen?"). Die Synthese-/Hypothesen-Frage
wird daraus generiert statt generisch. Schema: `competing: [{hypothesis,
evidence_against}]` am Claim.

**R4 — Warrant-Feld (Toulmin).** `knowledge_claims.warrant TEXT` — bei
contested Claims MUSS der Curator benennen, ob Grounds oder Warrant
strittig ist. Macht Papers präziser („die Beobachtung ist unstrittig,
strittig ist der Schluss").

**R5 — Zwei Dimensionen (Admiralty).** Quellen-Verlässlichkeit (aus
Track Record: wie oft haben sich Claims dieser Quelle/dieses Kanals
gehalten? — berechenbar aus unserer eigenen Outcome-Historie!) getrennt
von Claim-Glaubwürdigkeit. Langfristig; braucht R2 als Datenbasis.

**R6 — ICD-203-Sprache in Papers.** Verdicts mit normierten
Wahrscheinlichkeitsbändern + getrennter Konfidenzangabe. Reine
Prompt-/Render-Änderung, hoher Leser-Ehrlichkeitsgewinn.

**R7 — GRADE-Modifikatoren.** `evidence_score` statt Zähler
(Replikation/Direktheit/Aktualität). Nach R1, teilt sich die Wurzel-Logik.

**Reihenfolge-Empfehlung:** R2 (sofort, ~1 Tag) → R1a (Prompt+Schema,
~1 Tag) → R3+R4 (zusammen, ~2 Tage) → R6 → R1b/R5/R7 (strukturell,
eigene Specs). Alles setzt v1 deployed voraus.

## 5. Grenze der Frameworks (Ehrlichkeit)

Kein Framework LIEFERT Wahrheit; sie disziplinieren die Suche. Für ein
System, das Mainstream UND Fringe ernsthaft kontrastiert, ist die
wichtigste Eigenschaft nicht Cleverness, sondern: dokumentierte Priors,
lokalisierte Kontroversen (Warrant!), unabhängig gewogene Evidenz,
abgerechnete eigene Urteile — und die Bereitschaft, refuted stehen zu
lassen. v1 hat das Skelett; R1–R4 machen daraus Methode.

Siehe: Heuer, *Psychology of Intelligence Analysis* (ACH); Mayo,
*Statistical Inference as Severe Testing*; GRADE Handbook; ICD 203;
Tetlock/Gardner, *Superforecasting*; Toulmin, *The Uses of Argument*.
