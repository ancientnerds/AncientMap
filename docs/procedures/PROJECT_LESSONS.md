# Projekt-Lektionen (AncientMap)

Migriert am 2026-09-20 aus dem Erfahrungsspeicher der Claude-Code-Zeit
(`~/.claude/projects/C--PythonProjects-AncientMap/memory/`, 92 Dateien, 2026-03-10 … 2026-09-19).
Diese Datei liegt im Repo, weil der alte Speicher außerhalb liegt und ein neuer Agent ihn
sonst nicht kennt. Quellen und Datum stehen jeweils dabei; Stand ist der 19.09.2026.

## Betrieb und Deploy

- **Ein Deploy kann „success" melden, ohne neu gebaut zu haben.** Nach jedem Deploy den
  `commit` im Health-Endpoint prüfen (`curl localhost:8000/`), nicht den grünen Haken.
  *(`reference-deployment-lessons`, 2026-09-17)*
- **Der Deploy baut nur, was der Diff berührt.** Eine Änderung unter `pipeline/` baut `api`
  **und** `lyra` neu (so seit `ea3f30a`, 2026-02-05); der Theo-Worker wird nur neu gebaut, wenn
  kein Lauf `running` ist. Die frühere Notiz „der Deploy rebuildet nur `api`, Lyra braucht ein
  manuelles `--build lyra`" war veraltet. *(`ci.yml`, deploy-Job, geprüft 2026-09-22)*
- **`pipeline/` läuft in ZWEI Images mit ungleichen Fähigkeiten.** `Dockerfile.lyra` kopiert
  nur `pipeline/`; dort gibt es kein `api`, kein `markdown`, kein `nh3`. Solche Imports
  gaten (`importlib.util.find_spec("api")`), sonst Crash-Loop.
  *(`reference-deployment-lessons`, 2026-09-17)*
- **Lyra-Boot-Migrationen laufen als EIN Transaction-Batch.** Ein Fehler rollt alle Spalten
  des Releases zurück und wiederholt sich bei jedem Boot.
  *(`project_lyra_migration_transaction`, 2026-05-25)*
- **"Idempotent" boot DDL still locks: ask the catalog first.** `ALTER TABLE … ADD COLUMN IF
  NOT EXISTS` and `ADD CONSTRAINT` take ACCESS EXCLUSIVE, `CREATE INDEX IF NOT EXISTS` takes
  SHARE — *before* PostgreSQL looks for the object. Lyra ran 76 schema statements on every
  start, 68 of them lock-taking with nothing to do, inside its one transaction, and held every
  lock until the final commit; the API ran 29 more (28 lock-taking) on api and api2 at every
  deploy. That deadlocked the deploy's library refresh on `news_items` twice (2026-09-22/23). Since 2026-09-23 every boot schema statement goes through
  `ensure()` (`pipeline/utils/boot_ddl.py`; lists in `_run_migrations` and `api/boot_schema.py`):
  a pg_catalog query decides, and the unchanged statement (still `IF NOT EXISTS`, for two booters
  racing) runs only when its object is missing. On an up-to-date schema a boot issues no DDL at
  all; on 2026-09-23 all 108 checks answered "present" on production (read-only). Lyra is still
  ONE transaction — the checks run inside it. New boot DDL goes through `ensure()`; a bare
  `conn.execute(text("ALTER …"))` fails `tests/pipeline/test_boot_ddl.py` (in `_run_migrations`
  and `API_BOOT_SCHEMA` the second boot must be DDL-free; `api/main.py` may hold no DDL string
  at all). The `ADD CONSTRAINT` duplicate handlers now run only when two booters race, so
  no ordinary boot exercises them; the same test file drives that race for every constraint of
  both paths. Moving code out of `api/main.py` and `_run_migrations` broke 22 line-number
  citations in code and docs, two of them printed in refusal texts at run time: cite code as
  `file.py::function`. *(2026-09-23)*
- **LLM-SDK-Versionen deckeln** (z. B. `anthropic<1.0.0`). Ungepinnte Deploys ziehen Majors
  und brechen alle MiniMax-Aufrufe. *(`reference-deployment-lessons`, 2026-08-25)*
- **Nie `… | tail` hinter `gh run watch --exit-status` oder `ruff check`** — die Pipe
  maskiert den Exit-Code. *(`reference-deployment-lessons:10`, 2026-09-17)*
- **Betriebs-Fallen auf dem VPS:** Statik-Export braucht `-u root`; `docker exec -i` frisst
  stdin-geskriptete Eingaben; `docker logs --since` rechnet in Host-Lokalzeit (CEST), nicht
  UTC; `pkill -f` matcht die eigene SSH-Session (stattdessen PID-Dateien).
  *(`reference-deployment-lessons:44,47,48,59`, 2026-09-17)*
- **Der Deploy scheitert am `git pull`, nicht an den Gates — drei Ursachen, je ein Deploy
  (2026-09-22):** (1) Eine Datei, die erst als ungetrackte Kopie auf den VPS kam und später
  committet wurde, blockiert den Merge („untracked working tree files would be overwritten“).
  (2) Ein root-eigenes Verzeichnis im Deploy-Baum (`output/`, seit März) bricht den Checkout
  **mittendrin** ab: HEAD bleibt alt, die Platte ist halb neu, und jeder weitere Pull scheitert
  an diesen Resten. Aufräumen: `git checkout -- .` plus genau die Dateien aus
  `git diff --name-only --diff-filter=A HEAD FETCH_HEAD` löschen, die auf der Platte liegen.
  (3) Vorab prüfen lässt sich beides auf dem VPS, ohne etwas zu ändern: `git fetch`, dann für jeden
  Pfad aus `git diff --name-only HEAD FETCH_HEAD` Kollision und Schreibrecht testen.
- **Shell-Skripte, die der VPS direkt ausführt, brauchen `100755` im Index.** Auf diesem
  Windows-Checkout ist `core.filemode=false`; `git add` speichert `100644`, und der Backup-Cron
  (`./00_backup_and_drill.sh`, ruft seine Geschwister per Pfad) wäre nach dem ersten Pull still
  gescheitert — der Cron hat kein `MAILTO`. Stagen mit `git add --chmod=+x`. *(2026-09-22)*
- **Lokal grün ist nicht CI-grün, wenn die Umgebungen auseinanderlaufen.** Die CI installiert
  pytest ungepinnt (9.1: Marker auf Fixtures sind ein Fehler) und nur `requirements-api.txt` +
  `requirements.lyra.txt` (kein geopandas); Frontend und VPS laufen auf Node 20 (jsdom ≥ 30
  verlangt Node 22.22+). Nachweis vor einem Push: sauberer Worktree ohne gitignorierte Daten, ein
  venv mit exakt der CI-Installationszeile, vitest unter `npx -p node@20`. *(2026-09-22)*

- **Agenten-Worktrees: keine Junctions auf geteilte Verzeichnisse, und vor dem Entfernen jede
  Junction lösen (2026-09-23).** `git worktree remove --force` ist unter Windows durch eine
  `.venv`-Junction (Worktree → Haupt-venv) in die echte venv gelaufen und hat sie bis zur ersten
  gesperrten DLL gelöscht: aiohttp, aiohappyeyeballs, aiofiles, die mypyc-Bibliotheken von
  black/mypy/tomli, pywin32 (`api` war nicht mehr importierbar). Repariert per
  `pip install --force-reinstall --no-deps` in den exakten Versionen. Prüfen, bevor man einem
  Worktree-Löschen traut: `Get-ChildItem -Attributes ReparsePoint` im Worktree, Junctions mit
  `cmd /c rmdir <link>` lösen (löscht nur den Link). Die venv prüft man an den `RECORD`-Dateien
  **und** mit `pip check` - ganz gelöschte Pakete sieht nur der zweite. Test- und
  Mutations-Ergebnisse aus dem Schadensfenster sind ungültig (jede Mutation liest dort als
  „gefangen“).
- **Ein Worktree kostet ~4,2 GB** (davon 2,3 GB `public/data`, auch ohne LFS-Inhalt). 44 parallele
  Worktrees haben C: am 2026-09-23 auf 0 Byte gebracht; Schreibvorgänge wurden abgeschnitten.
  Worktrees fertiger Workflows sofort entfernen (Junctions zuerst lösen), die Platte mit
  `df -h /c` beobachten, Mutation-Sweeps nie in einem Worktree laufen lassen, den ein anderer
  Agent gleichzeitig benutzt.

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
- **Card texts: the database first, the file second, in one sitting - never the file first.**
  Every API boot upserts `public/data/card_descriptions.json` into `card_stats`
  (`api/services/card_descriptions.py`). Pushed first, the file would write the cards without a
  journal and the journalled P5 write would then refuse every row with matched_0; written to the
  database only, a card is reverted at the next boot. The order is the P5 sitting of
  `docs/procedures/CARD_DESCRIPTIONS.md`: pre-render the file from the plan, write through the
  journal in steps of 100, regenerate the file from production byte for byte, push, then 0
  `[STARTUP] Card description overwritten` lines on both API containers. A red CI inside the
  sitting: `scripts/remediation/phase4/revert4.py --stamp-like 'phase5:%'` plus `git revert` of the
  JSON commit. *(design entry [6], production_write, 2026-09-23)*
- **A `db.html` batch upload from a stale export overwrites rewritten descriptions.**
  `POST /api/sites/batch-upload` sets `description = COALESCE(:description, description)`
  (`api/routes/sites.py:1686`) with no old-value condition and no journal row, so an export taken
  before the Phase-4 writes puts the March texts back over the sourced ones - and the provenance in
  `raw_data` then describes a text the row no longer holds (the pages stop disclosing it). The
  conditional old values make a concurrent chunk abort, and `verify_writes4.py`'s journal chain finds
  it afterwards; `db.html` is not used for curated sites until the Phase-6 export.
  *(design entry [6], failure_modes, 2026-09-23)*

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
