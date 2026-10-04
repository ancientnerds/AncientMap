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
- **`GIT_DIR` schlägt `git -C` — jede `git`-Kommando, das ein Repository *nennt*, braucht eine
  Umgebung ohne `GIT_*`.** Git setzt `GIT_DIR` (und `GIT_WORK_TREE`/`GIT_INDEX_FILE`, wenn
  passend) selbst, wenn es `.githooks/pre-push` aufruft; der Hook exportiert nichts. Die
  Testsuite läuft in dieser Umgebung, also läuft sie in der des gepushten Checkouts: am
  2026-10-03 landete dadurch der `commit -m a` eines Tests mitten im Push auf dem Branch,
  stellte `a.txt` in den echten Index und ließ das Gate mit 24 Fehlern umfallen. Nach dem
  Test-Fix blieben 8 Fehler, weil **Produktionscode** umgeleitet wurde: `mcode.tree_state`
  (`git -C <repo> status`) sah den gepushten Baum und meldete „keine Änderung", und
  `write_gate4._git` (`git -C <LANE_N_REPO> merge-base`) las die Historie des falschen
  Repos („Not a valid commit name"). Fix: `pipeline/utils/git_env.py` — `run_git(repo, …)`
  für die Standardform, `env=own_env()` für Aufrufe mit eigenem `check=True`/Timeout;
  `tests/git_env.py` re-exportiert dieselbe Funktion, damit es nur eine Implementierung gibt.
  Vier Produktionsstellen nutzen sie: `pipeline/studio/mcode.py`, `pipeline/studio/config.py`,
  `pipeline/video/shorts_ledger.py`, `output/remediation/tools/write_gate4.py`.
  *(2026-10-03, Commits `4479abd` und der Nachfolger; Test `tests/pipeline/utils/test_git_env.py`)*
- **Betriebs-Fallen auf dem VPS:** `docker exec -i` frisst stdin-geskriptete Eingaben;
  `docker logs --since` rechnet in Host-Lokalzeit (CEST), nicht UTC; `pkill -f` matcht die
  eigene SSH-Session (stattdessen PID-Dateien).
  *(`reference-deployment-lessons:44,47,48,59`, 2026-09-17)*
- **Den Statik-Export nie mit `-u root` fahren** (die frühere Lektion „Statik-Export braucht
  `-u root`" war die Ursache, nicht die Lösung). Der Root-Lauf vom 2026-08-18 hat `sites/`,
  `sources.json`, `links.json` und `images/index.json` root-eigen hinterlassen; der
  Rebuild-Job läuft als uid 1000 und scheitert daran (Plan 9.4, gemessen 2026-09-25). Seit
  2026-09-25 verweigert `pipeline/static_exporter.py` den Lauf als root und nennt vor dem
  ersten Schreiben jede Datei, die er nicht schreiben kann. Abhilfe ohne sudo:
  `docker exec -u root ancient_nerds_api chown -R 1000:1000 /app/public/data/<pfad>`, dann
  `docker exec ancient_nerds_api python -m pipeline.static_exporter --no-library`.
  Die Export-Dateien sind gitignoriert und entstehen nur auf dem VPS; kein Commit, kein LFS.
  *(Phase 6, 2026-09-25)*
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
  database only, a card is reverted at the next boot. The order was the P5 sitting: pre-render the
  file from the plan, write through the journal in steps of 100, regenerate the file from production
  byte for byte, push, then 0 `[STARTUP] Card description overwritten` lines on both API
  containers. A red CI inside the sitting: `scripts/remediation/phase4/revert4.py --stamp-like
  'phase5:%'` plus `git revert` of the JSON commit. *(design entry [6], production_write,
  2026-09-23)* Lane WB's teaser cards keep the order: accepted journalled steps, then
  `mechanical/teaser.py card-file` renders the file from production, then the push - no other push
  and no API restart in between (`docs/procedures/CARD_DESCRIPTIONS.md` 5.5). Their undo - also
  for a red CI inside the sitting - rolls the steps back, closes them with `close-reverted` and
  renders the file back from production with `card-file`: never a `git revert`, so main's file is
  always the database's (5.5, 5.6). *(2026-09-26)*
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
- **Eine Precache-URL ohne 200 legt den Service Worker still.** Workbox installiert nur, wenn
  jede Precache-URL 200 liefert; sonst behält jeder Browser seinen alten Worker samt alter Seiten.
  `/site.html` antwortete ab 12.09. mit 404 (die API bedient die URL, die Datei ist nur SSR-Vorlage):
  zwei Wochen lang installierte kein Worker. Seiten, deren URL nginx an die API gibt, gehören in
  `src/pwa/precacheExclusions.ts` (Test liest die nginx-Config). Prüfen per DevTools-Protokoll
  (`ServiceWorker.workerErrorReported`), nicht per `curl`. *(2026-09-26, ac0ea0a)*
- **Browser-Speicher nie im Render-Pfad** — sonst React-Hydration-Fehler 418 auf allen
  SSR-Seiten. Wächter: `render.test.tsx`. *(`reference-ssr-hydration-storage`, 2026-09-18)*
- **SitePopup: Das Verhalten der SEO-Seite hängt an `fullPage`, nie an `isStandalone`**
  (Overlays nutzen `isStandalone` ebenfalls).
  *(`feedback-sitepopup-standalone-is-not-the-seo-page`, 2026-09-10)*

## Inhalte und Scope

- **Das mittelalterliche Alte Welt ist als Scope verboten**, Amerika bis 1500 AD, Ozeanien seit
  O7 (Eigentümer, 2026-09-26) ebenfalls bis 1500 AD (`pipeline/normalizers/dates.py`,
  `e3_region`: Land, ISO-Code oder „Region, Land“; Hawaii/Rapa Nui über Inselboxen). Die Regel
  liegt als Prompt-LABEL (`summary.txt`, PERIOD SCOPE) vor, nicht als Datumscheck — nur
  1,45 % der Sites sind datiert. Sichtbarkeit ab `significance>=2`, Rückzug = HTTP 410.
  *(`project-medieval-scope-rule`, 2026-09-11)*
- **Jede Zitatstelle muss maschinell belegbar sein.** LLM setzt nie Zitationsnummern.
  *(`feedback_no_ai_slop`, 2026-04-08)*
- **A Commons `thumburl` is no proof of a picture, and an original is no thumbnail.**
  `list=categorymembers&cmtype=file` lists every file of a category, and `prop=imageinfo` with
  `iiurlwidth` answers a JPEG page or frame for a PDF, a WebM or a DjVu and Commons' file-type icon
  for an MP3 or a FLAC (measured 2026-09-26): the MIME type decides what is a picture
  (`scripts/remediation/served_image/commons.py`, `picture_url`). Store the 1280 px rendering a
  check was shown, never the original - the first 12 originals of Category:Casa Grande Ruins
  National Monument are 9.0-20.1 MB each, and a TIFF original is no `<img>` source.
  *(WD2 review, 2026-09-26)*
- **Kein Fallback- und Defensiv-Code** — Ursache fixen oder `available=False` mit klarem
  Grund. *(`feedback_no_fallbacks`, 2026-04-13; auch in `CLAUDE.md`)*
- **MiniMax PAYG existiert nicht** — nie nennen, immer in der Quota planen. `total_tokens`
  unterschätzt etwa um Faktor 7; nur `probe_minimax_quota()` glauben.
  *(`minimax-max-vs-payg`, 2026-09-19)*
- **`thinking={"type":"disabled"}` hängt am Modell, nicht an der API** (live gemessen 2026-10-03,
  eine 64-Token-Anfrage je Modus über `pipeline.lyra.config._get_minimax_anthropic_client`):
  `MiniMax-M3` antwortet **200**, `MiniMax-M3.1-Flash-Preview` antwortet **400**
  `invalid_request_error` 2013 *"requires adaptive thinking; thinking.type=\"disabled\" (including
  reasoning.effort=none) is not allowed"*, `adaptive` auf M3.1 antwortet 200. Der Lean-Modus, der
  Denken als ~89 % des M3-Outputs kostet, existiert auf M3 und auf M3.1 nicht.
  **Eine Sonde ohne Modellnamen beweist nichts** - ohne `model` serviert der Endpoint `MiniMax-M3`,
  und die M3.1-Verweigerung ist unsichtbar (genau so war der erste Lauf dieser Messung).
  **Stand `main` (Deploy `896e9fc`, 2026-10-03):** `MINIMAX_MODEL` ist in keinem
  Produktionscontainer gesetzt, aber der **Code-Default ist `MiniMax-M3.1-Flash-Preview`** - es
  rechnet also jeder Call, ein Sparmodus existiert auf diesem Modell nicht. `THINKING_OFF` und alle
  `thinking={"type":"disabled"}`-Aufrufstellen sind im selben Commit aus den Prospector-Extraktern
  entfernt; in `pipeline/` und `api/` steht der String nur noch in Kommentaren. **Es 400t nichts.**
  *(`project_theo_pipeline` / `reference_minimax_m3_endpoint`, 2026-10-03; die Behauptung des
  Field-Fill-Agenten war für M3.1 richtig und ist inzwischen umgesetzt - siehe
  `output/remediation/AUDIT_LOG.md`)*
- **Fragen über Produktion gehören gegen `origin/main` gestellt**, nicht gegen den eigenen
  Checkout. Am 2026-10-03 lag `integrate/wave1` 284 Commits hinter `main`; eine Aussage über
  `MINIMAX_MODEL` aus diesem Baum war schlicht falsch, obwohl die Messung selbst stimmte. Immer
  `git show origin/main:<datei>`, und wenn der Unterschied eine Aussage trägt, dazuschreiben, gegen
  welchen Baum sie gemessen wurde.
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
- **Wikimedia sperrt einen User-Agent ohne Kontakt** (`403 Please respect our robot policy`,
  mit httpx gemessen 2026-09-26); die öffentliche Projekt-URL als Kontakt genügt
  (`AncientMapRemediation/1.0 (https://ancientnerds.com; research)` bekommt 200) — dafür braucht
  es keine personenbezogenen Daten. Eine Bot-Sperre wird nie umgangen (auch nicht über einen
  anderen TLS-Handshake): UNESCO WHC, Atlas Obscura, Britannica und Historic England antworten
  mit 403 und gelten als maschinell nicht lesbar. *(WD1-Review, `docs/procedures/FIELDS_WD1.md`,
  2026-09-26)*

## Studio (captures and renderer)

Runbook: `docs/procedures/STUDIO.md`.

- **The studio runs headless; headed Chrome needs an awake display.** The first studio Mapbox fly-in
  (2026-09-26, 11:41) hung for 15 minutes: the display slept and headed Chrome produced no animation
  frame. Since 2026-10-02 every studio Chrome is headless (owner requirement: no display), the
  display-awake guard is gone, and headless Chrome screencasts at the view's pixel size, so the platform
  take forces `--force-device-scale-factor=2` and caps at 2880x1620 (first headless take: 1920x1080).
  The recorder scenes still fail after 30 s without a frame (`NO_FRAME_MS`). Guard:
  `tests/pipeline/studio/test_no_display.py`; details in `docs/procedures/STUDIO.md` section 9.2.
  *(plan D Tasks 27 and 36, 2026-09-26; superseded 2026-10-02)*
- **Remotion's `bundle()` leaves a copy of the whole public dir in `%TEMP%`.** Its default output is a
  fresh `remotion-webpack-bundle-*` directory in the system temp dir that nothing deletes, and it
  copies the public dir, so every run left a copy of every capture on C: (67 such directories were in
  `%TEMP%` on 2026-09-29, from the build's verification runs). The studio's node scripts bundle into
  `render/bundle/` next to the public dir and delete it on success and failure (`withBundle`,
  `video/scripts/cli.ts`). Delete old `%TEMP%\remotion-webpack-bundle-*` directories by hand, and
  only while no render runs. *(plan D contract D4; build index I8 step 10, 2026-09-27)*
- **A dev server left on a capture port serves the take from an older checkout.** Windows does not
  end npm's children when the Python process dies, so an interrupted take leaves Vite running.
  Without `--strictPort` the next Vite moves to another port while the page still loads from the old
  server (with its file watcher off); an orphaned Vite on port 5199 once served takes that way
  without an error. `record.ts` (port 5199) and the studio's `local_site()` (port 5198) start Vite
  with `--strictPort`; `local_site()` also refuses a port that answers at any address of localhost
  (Vite binds only the first one, `::1` here) and counts the site as ready only when its own Vite
  announces the port. Find the stale server with `netstat -ano | findstr :5198`.
  *(`pipeline/studio/capture/vite.py`, commit `12f5832`, 2026-09-27)*
- **Ein `mcode`-Lauf, der über `cmd /c` startet, darf nicht mit `subprocess.run(timeout=…)`
  gebunden werden — der Kill trifft nur den Wrapper.** `subprocess.run` killt bei Timeout den
  Prozess, den es gestartet hat, und ruft danach `communicate()`; unter Windows läuft der Befehl
  über den Command Processor, und der `node`-Prozess darunter hält das geerbte Pipe-Ende offen,
  also blockiert `communicate()` **ohne jede weitere Frist**. Am 2026-10-03 kostete das das Studio
  3,5 Stunden (drei `node`-Kinder mit ~1 % CPU auf einem hängenden Provider-Socket); in 45 Sekunden
  mit reinem Python reproduziert: 5 s Timeout, bei 45 s noch blockiert, der Enkelprozess lebt nach
  dem Kill. Zwei Konsequenzen: Streams an **Dateien** binden und den **Prozessbaum** killen
  (`taskkill /T /F` bzw. `killpg`) — so arbeitet `pipeline/studio/mcode.py`; und wer über
  `cmd /c` startet, bekommt einen zusätzlichen Prozess, den man mitbedenken muss. Betrifft auch
  den Remediation-Fahrer `scripts/remediation/mcode_driver.py` (Stand 2026-10-03 noch nicht auf
  `main`); er entfernt in `run_git()` außerdem kein `GIT_*` (siehe „Betrieb und Deploy" oben).
  *(`pipeline/studio/mcode.py`, Messung `C:\tmp\studio_build\hangtest\probe.py`, 2026-10-03)*

## Nicht mehr gültig

- `feedback_push_without_asking` (Push ohne Rückfrage bei grünen Gates): abgelöst durch den
  fail-closed Riegel `.githooks/pre-push` (2026-09-20).
- Tunnel-Annahmen (`psql -h localhost -p 15432` über Bitvise, `feedback_use_api_tunnel`):
  überholt, seit es keine lokale DB mehr gibt.
- Wegwerf-Container für Pin-Prüfungen (`docker run --rm python:3.12-slim`) und
  `docker compose up -d --build api` lokal: überholt (kein lokales Docker mehr).
- Etwa 15 als „abgeschlossen" markierte Projekt-Notizen (Theo-/SEO-/Bild-Pfade) — bei Bedarf
  im alten Speicher nachlesen, nicht hierher migriert.
