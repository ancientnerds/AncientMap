# Projekt-Lektionen (AncientMap)

Migriert am 2026-09-20 aus dem Erfahrungsspeicher der Claude-Code-Zeit
(`~/.claude/projects/C--PythonProjects-AncientMap/memory/`, 92 Dateien, 2026-03-10 … 2026-09-19).
Diese Datei liegt im Repo, weil der alte Speicher außerhalb liegt und ein neuer Agent ihn
sonst nicht kennt. Quellen und Datum stehen jeweils dabei; Stand ist der 19.09.2026.

## Betrieb und Deploy

- **Ein Deploy kann „success" melden, ohne neu gebaut zu haben.** Nach jedem Deploy den
  `commit` im Health-Endpoint prüfen (`curl localhost:8000/`), nicht den grünen Haken.
  *(`reference-deployment-lessons`, 2026-09-17)*
- **Der Deploy rebuildet nur `api`.** Änderungen an `pipeline/` für Lyra brauchen ein
  manuelles `docker compose up -d --build lyra` auf dem VPS.
  *(`reference-deployment-lessons`, 2026-09-17)*
- **`pipeline/` läuft in ZWEI Images mit ungleichen Fähigkeiten.** `Dockerfile.lyra` kopiert
  nur `pipeline/`; dort gibt es kein `api`, kein `markdown`, kein `nh3`. Solche Imports
  gaten (`importlib.util.find_spec("api")`), sonst Crash-Loop.
  *(`reference-deployment-lessons`, 2026-09-17)*
- **Lyra-Boot-Migrationen laufen als EIN Transaction-Batch.** Ein Fehler rollt alle Spalten
  des Releases zurück und wiederholt sich bei jedem Boot.
  *(`project_lyra_migration_transaction`, 2026-05-25)*
- **LLM-SDK-Versionen deckeln** (z. B. `anthropic<1.0.0`). Ungepinnte Deploys ziehen Majors
  und brechen alle MiniMax-Aufrufe. *(`reference-deployment-lessons`, 2026-08-25)*
- **Nie `… | tail` hinter `gh run watch --exit-status` oder `ruff check`** — die Pipe
  maskiert den Exit-Code. *(`reference-deployment-lessons:10`, 2026-09-17)*
- **Betriebs-Fallen auf dem VPS:** Statik-Export braucht `-u root`; `docker exec -i` frisst
  stdin-geskriptete Eingaben; `docker logs --since` rechnet in Host-Lokalzeit (CEST), nicht
  UTC; `pkill -f` matcht die eigene SSH-Session (stattdessen PID-Dateien).
  *(`reference-deployment-lessons:44,47,48,59`, 2026-09-17)*

## Datenbank

- **Prod ist die einzige Wahrheit.** Es gibt keine lokale DB; Zugriff nur auf dem VPS über
  `docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c "…"`. Die Zugangsdaten
  sind user=`ancient_map`, db=`ancient_map` — **nicht** `ancientnerds`, **nicht**
  `ancient_nerds`, **nicht** `postgres`. *(`reference-deployment-lessons:29`,
  `reference_ssh_access:5`)*
- **NIE `TRUNCATE` / `DELETE CASCADE` auf `unified_sites`.** Nur gezieltes `DELETE` per
  `source_id`. Geschützt: `ancient_nerds`, `community`, `lyra`. *(`MEMORY.md:10`)*
- **`name_normalized` ist ein Postgres-Key**, berechnet als
  `left(lower(unaccent(name)),500)`. Jeder Namensvergleich bindet den ROHEN Namen und
  berechnet den Key in SQL mit demselben Ausdruck (`site_matcher._KEY_SQL`) — niemals in
  Python nachbauen. *(`reference-name-normalized-key`, 2026-09-15)*
- **Prod-Writes nach `commit()` in der DB nachzählen.** `session.expire_all()` verwirft
  ungeflushte ORM-Änderungen still. *(`project-verify-db-writes-after-commit`, 2026-09-15)*

## Frontend

- **Statische Daten liegen nur in `public/data/` (Repo-Wurzel).**
  `ancient-nerds-map/public/data/` darf nicht existieren. *(`MEMORY.md:12`; allein
  wiederholt in `.gitignore`)*
- **Der PWA-Service-Worker schluckt Nicht-`.html`-Pfade.** Jede Server-Route muss in
  `navigateFallbackDenylist` (`vite.config.ts`) stehen; `curl` sieht den Bug nicht.
  *(`reference-deployment-lessons:11`)*
- **Browser-Speicher nie im Render-Pfad** — sonst React-Hydration-Fehler 418 auf allen
  SSR-Seiten. Wächter: `render.test.tsx`. *(`reference-ssr-hydration-storage`, 2026-09-18)*
- **SitePopup: Das Verhalten der SEO-Seite hängt an `fullPage`, nie an `isStandalone`**
  (Overlays nutzen `isStandalone` ebenfalls).
  *(`feedback-sitepopup-standalone-is-not-the-seo-page`, 2026-09-10)*

## Inhalte und Scope

- **Das mittelalterliche Alte Welt ist als Scope verboten**, Amerika bis 1500 AD. Die Regel
  liegt als Prompt-LABEL (`summary.txt`, PERIOD SCOPE) vor, nicht als Datumscheck — nur
  1,45 % der Sites sind datiert. Sichtbarkeit ab `significance>=2`, Rückzug = HTTP 410.
  *(`project-medieval-scope-rule`, 2026-09-11)*
- **Jede Zitatstelle muss maschinell belegbar sein.** LLM setzt nie Zitationsnummern.
  *(`feedback_no_ai_slop`, 2026-04-08)*
- **Kein Fallback- und Defensiv-Code** — Ursache fixen oder `available=False` mit klarem
  Grund. *(`feedback_no_fallbacks`, 2026-04-13; auch in `CLAUDE.md`)*
- **MiniMax PAYG existiert nicht** — nie nennen, immer in der Quota planen. `total_tokens`
  unterschätzt etwa um Faktor 7; nur `probe_minimax_quota()` glauben.
  *(`minimax-max-vs-payg`, 2026-09-19)*
- **`card_description` ist der gesprochene Shorts-Text** — 904 Texte enthielten Zahlen, die
  nie im Generator-Input standen. `verify_descriptions.py` bestraft Hedging und wurde
  deshalb als Gate stillgelegt. *(`project-db-audit-weekend:30-33`, 2026-09-19)*

## Arbeitsweise

- **Alles erledigen, selbst erledigen** — nicht als Entscheidungsliste zurückgeben. Kleine
  Aufträge ohne Plan-Fanfare ausführen, den empfohlenen Weg gehen, nichts liegen lassen.
  *(`feedback_finish_everything` 2026-08-05, `feedback_stop_over_planning` 2026-04-24,
  `feedback_go_recommended_path` 2026-07-19)*
- **Kein `git reset`/`amend` auf `main`, kein blindes `stash pop`.** `ruff format` vor dem
  Push laufen lassen (Version wie in der CI). *(`feedback_git_dont_reset_shared_branches`
  2026-04-19, `feedback_git_stash_safety` 2026-06-12)*
- **Es ist ein gemeinsamer Working Tree.** Vor `git push` `git log origin/main..HEAD`
  prüfen; fremde Dateien nur anfassen, wenn `git status --porcelain <datei>` leer ist.
  *(`reference-deployment-lessons:59`)*
- **Bash-Heredocs fressen Backslashes** — Patch-Skripte nur mit dem Write-Werkzeug anlegen.
  *(`reference-heredoc-backslash-escapes`, 2026-09-16/17)*
- **Kein LLM-über-LLM zur Quellenprüfung** — für Zitat-Treue maschinell prüfen
  (Keyword-Matching). Das betrifft *Quellen*, nicht das Code-Review durch Prüfer.
  *(`feedback_no_ai_slop`)*

## Nicht mehr gültig

- `feedback_push_without_asking` (Push ohne Rückfrage bei grünen Gates): abgelöst durch den
  fail-closed Riegel `.githooks/pre-push` (2026-09-20).
- Tunnel-Annahmen (`psql -h localhost -p 15432` über Bitvise, `feedback_use_api_tunnel`):
  überholt, seit es keine lokale DB mehr gibt.
- Wegwerf-Container für Pin-Prüfungen (`docker run --rm python:3.12-slim`) und
  `docker compose up -d --build api` lokal: überholt (kein lokales Docker mehr).
- Etwa 15 als „abgeschlossen" markierte Projekt-Notizen (Theo-/SEO-/Bild-Pfade) — bei Bedarf
  im alten Speicher nachlesen, nicht hierher migriert.
