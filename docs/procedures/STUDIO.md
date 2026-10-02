# Studio runbook: the Claude paper write and the video studio

Theo researches on the VPS and stops at a dossier (status `researched`). A local Claude Code session
then writes, checks and publishes the paper through gated VPS CLIs (the paper studio), and turns a
published paper into a YouTube episode (the video studio). This runbook says how to set the
workstation up, how the two sessions run, what every gate checks, how to correct a published paper,
and how to recover when a step fails.

Binding sources: the spec `docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md`, the
owner decisions in `docs/superpowers/plans/2026-09-26-owner-questions.md` (#1-#32, Q1-Q17), the build
index `docs/superpowers/plans/2026-09-26-00-index.md` and the four stream plans beside it. Where this
file and the code disagree, the code is right and this file is stale: fix it.

## 0. State on 2026-10-01

- **Read the release state from production, do not assume it.** The release deploy (index item I8)
  applies migrations 0025 (`theo_paper_publications`) and 0026 (`studio_episodes`) and ships the modules
  `pipeline.lyra.theo_publish`, `pipeline.lyra.theo_dossier` and `pipeline.studio.ledger_cli` in the API
  image. Every step that reaches production needs them: `paper list`, `pull`, `publish`, `correct`,
  `register-video`, the ledger write at the end of `episode render`, and `episode register-youtube`.
  Before the first such step of a session, read both from the VPS (read-only):
  `ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c \"SELECT filename FROM applied_migrations WHERE filename LIKE '0025%' OR filename LIKE '0026%'\""`
  must list both files, and
  `ssh ancientnerds "docker exec ancient_nerds_api python -c 'import pipeline.lyra.theo_publish, pipeline.lyra.theo_dossier, pipeline.studio.ledger_cli'"`
  must exit 0. The `commit` field of `ssh ancientnerds "curl -s http://localhost:8000/"` names the
  commit the API image was built from. If a migration is missing or an import fails, the release deploy
  has not run or not finished: stop and report it. Do not apply a migration or copy a module to the VPS
  by hand.
- **Theo is stopped.** The VPS `.env` has `THEO_WORKER_DISABLED=1` since about 18:20 UTC on
  2026-09-26, set on the owner's behalf by another session (owner-questions #2 is moot, and Q1 keeps
  the worker off); the worker idles (`scripts/run_theo_worker.py`) and 24 batch rows are `paused`. No
  new `researched` row arrives until the owner restarts Theo.
- **Committed:** both studios, the renderer `video/`, all four capture recorders
  (`pipeline/studio/capture/`: `sources.py`, `mapbox.py`, `platform.py` and `globe.py`, with the four
  entry points of `capture/__init__.py`), the skills `.claude/skills/theo-write`, `studio-video` and
  `studio-casefile` (integration item I2) and the workflows `.claude/workflows/theo-claim-check.js`,
  `theo-image-check.js`, `studio-casefile-verify.js` and `studio-marker-check.js` (I3). The skills hold
  the step-by-step session; this runbook holds the background, the gates and the recovery.
- **Workstation proofs:** on 2026-10-01 `doctor` reported every probe ok, `npm run test:gpu` passed
  (19 tests in 3 files, about 330 s; measured 2026-10-02) and one real CUDA float16 transcription ran (section 1.3). The
  smoke render (plan D Task 22) and the real captures (plan D Task 36) have run on this workstation;
  they run again after any change to `video/` or `pipeline/studio/capture/` (index I8, step 1).

## 1. Setup (once per workstation)

### 1.1 What the machine needs

- The owner's hybrid laptop: NVIDIA GeForce RTX 3080 Laptop GPU (the only CUDA device, index 0) and an
  integrated AMD Radeon that the studio never uses (spec 4.11, section 8).
- Node 22 on `PATH`; `ffmpeg` and `ffprobe` with `hevc_nvenc` and `h264_nvenc` on `PATH` (or named by
  `FFMPEG_BIN` / `FFPROBE_BIN`).
- The repo venv `.venv` (in a worktree a junction into the main checkout) with the local-only
  packages: Playwright (in no requirements file: `pip install playwright`; 1.58.0 is installed),
  faster-whisper, mutagen, Pillow, python-dotenv.
- `ssh ancientnerds` with key authentication: the studio runs ssh with `BatchMode=yes`
  (`pipeline/studio/remote.py`), so a password prompt fails instead of waiting.
- The main checkout's `.env`, which `python -m pipeline.studio` loads (`config.load_env`; a worktree
  has no `.env` of its own): `VITE_MAPBOX_ACCESS_TOKEN` for the captures (never print it) and
  `LYRA_MINIMAX_API_KEY` for the narration.
- The main checkout's `video-assets/music/` holds exactly one track when an episode uses
  `--music auto`.
- `ancient-nerds-map/node_modules` (the local site the platform takes record, and the recorder).
- An awake, unlocked Windows display for every capture (section 9.2).

### 1.2 Steps

From the root of the checkout the studio runs in:

```bash
(cd video && npm ci && npx remotion browser ensure)
./.venv/Scripts/python.exe -m pip install playwright         # only when doctor names it missing
./.venv/Scripts/python.exe -m playwright install chrome      # the Chrome channel the captures drive
./.venv/Scripts/python.exe -m pipeline.studio doctor --fix-gpu   # once per machine, after `browser ensure`
curl -sfR --create-dirs -o public/data/sites/index.json https://ancientnerds.com/data/sites/index.json   # section 11
./.venv/Scripts/python.exe -m pipeline.studio doctor
```

`doctor --fix-gpu` pins Remotion's headless shell to the high-performance GPU and then probes; a plain
`doctor` only probes. Both print one `ok` or `FAIL` line per probe and exit 1 when any probe fails
(section 8). `video/node_modules` is a real install per checkout (plan D Task 1); `npm ci` again
after `video/package-lock.json` changes.

### 1.3 CUDA for the word timings

`episode voice` times every word with faster-whisper on `device="cuda", device_index=0,
compute_type="float16"` (`voice.whisper_words`). `doctor` only counts CUDA devices (ctranslate2 sees
one); it does not load cuBLAS or cuDNN. Before the first real episode, prove one transcription:

```bash
./.venv/Scripts/python.exe -c "from pathlib import Path; from pipeline.studio.voice import whisper_words; print(len(whisper_words(Path('<an mp3 with speech>'))))"
```

It prints a word count (measured 2026-10-01 on this workstation: a 24-word Shorts narration came back
as 24 words in 7 s). If a CUDA library fails to load, install the missing NVIDIA library, pinned
(spec 4.11), and run the probe again. Never switch the studio to the CPU: the site Shorts keep their
CPU defaults, the studio passes its device explicitly.

### 1.4 Where the studio writes

`STUDIO_ASSETS` defaults to `<main checkout>/video-assets/studio` (gitignored); the main checkout is
the parent of git's common dir, so a session in a worktree writes into the same tree. The environment
variable `STUDIO_ASSETS` overrides it (the tests do). Workspaces: `papers/<request_id>/` and
`episodes/<slug>/`. The studio never writes into the repo, with one exception you run by hand: the site
export of section 11.

## 2. Running the studio

```bash
./.venv/Scripts/python.exe -m pipeline.studio paper   {list,pull,number,check,claims-export,claims-import,images-export,images-import,bundle,publish,correct,register-video}
./.venv/Scripts/python.exe -m pipeline.studio episode {init,markers-export,markers-import,check,review,voice,capture,timeline,render,thumbnail,package,register-youtube}
./.venv/Scripts/python.exe -m pipeline.studio doctor [--fix-gpu]
```

- Run from the checkout root with the repo venv. `--help` on any command lists its flags.
- Output is JSON on stdout, UTF-8 whatever the console code page; `doctor` prints one `ok` or `FAIL`
  line per probe instead.
- Exit codes: 0 success; 1 a check or gate failed (`paper check`, `episode check`, `episode voice`,
  `doctor`); 2 a `StudioError`, whose message (`error: ...` on stderr) says what to fix. A traceback
  is a bug, not an operating state.
- Production is reached only through ssh plus `docker exec -i ancient_nerds_api python -m <module>`
  for three modules (`remote.ALLOWED_MODULES`: `theo_dossier`, `theo_publish`, `ledger_cli`), and
  through scp into `/var/www/ancientnerds/public/data/research-images/<request_id>/`, verified byte for
  byte with `sha256sum`. Production credentials never leave the VPS. Nothing retries automatically.
- Every model judgement is Claude's, made in the session or by a workflow, and handed to the code as
  files. No studio code calls an LLM. The one paid call is the narration: `episode voice` sends each
  beat's `spoken` text to MiniMax's speech model (`speech-2.8-hd`, the Shorts narrator) after a quota
  check.

## 3. The paper session (`/theo-write`)

The owner starts the weekly session by hand with `/theo-write` (owner decision 4; no scheduler).
The skill `.claude/skills/theo-write/SKILL.md` runs these steps. Workspace:
`<STUDIO_ASSETS>/papers/<request_id>/` (file list in `pipeline/studio/paper/workspace.py`).

| # | Step | Result |
|---|---|---|
| 1 | `paper list` | `theo_dossier list` unchanged: the `researched` rows, oldest first (the writing queue) |
| 2 | `paper pull ID` | `dossier.json.gz`, `texts/<source_id>.txt` (the archived texts), `brief.md` |
| 3 | Claude writes `draft.md`, `paper_meta.json`, `evidence.json` | as `brief.md` says: cite with `[S:<12-hex id>]`, no images, no title line, no References |
| 4 | `paper number ID` | `sources.json` (`[N]` -> source id) and `paper.md` with `# Title`, `[N]` and References |
| 5 | `paper claims-export ID`, the theo-claim-check workflow, `paper claims-import ID` | the claim check (section 4.2) |
| 6 | Claude writes `images/opportunities.json` (4-10 entries), then `paper images-export ID`, the theo-image-check workflow, `paper images-import ID` | the image check (section 4.3) |
| 7 | `paper check ID` | `check_report.json`; exit 1 names the failing gates (section 4.1) |
| 8 | `paper bundle ID` | `bundle.json` from a passing check |
| 9 | `paper publish ID` | uploads the images, dry-runs, applies; writes `publish_outcome.json` and `published_bundle.json` |

- Fix a failing check in `draft.md`, `evidence.json` or `paper_meta.json`, then repeat from step 4.
  A claim-check task is keyed by the hash of its prompt, so only the changed paragraphs get new tasks;
  an old answer never vouches for a changed paragraph.
- `paper bundle` refuses unless `check_report.json` passed and the paper, `evidence.json` and
  `paper_meta.json` are what that check hashed. `paper publish` sends `bundle.json` as it is and refuses
  one older than the paper (`bundle.json is stale`: run `paper bundle` again).
- Publishing is automatic: the skill applies when every gate passes (spec 0). Every `paper publish`,
  the `--dry-run` too, first uploads the bundle's selected images to production's
  `research-images/<request_id>/` (verified byte for byte with `sha256sum`; the files are named after
  their content, so repeating is safe) and then dry-runs. `--dry-run` stops there and records the dry
  run in `publish_outcome.json`.
- The owner notice goes out on the apply: a `thinking_log` `run_event` `paper_published`. The Discord
  embed is sent only while `DISCORD_WEBHOOK_URL` is set, and it is unset (owner decision 5), so the
  outcome's `side_effects.notify` reads `{"discord": false}` normally.
- A first publish sets `published_by = 'Theo'` and `result_json.writer = {model: "claude-opus-5-5",
  tool: "claude-code", research_model: "MiniMax-M3", published: "automatic", human_review: false}`.
  The page then shows the evidence anchors `#ev-NN` and the disclosure line (spec 3.7).
- Pages are cached for 1800 s and the public API for 600 s (Redis); a change can take that long to
  show.
- `paper publish` refuses a public paper ("change it with `paper correct`", section 5) and a rewrite
  workspace (`dossier_from.json`: it goes out through `paper correct ID --republish`).

## 4. Gates and checks

### 4.1 The paper gates (`paper check`, `pipeline/studio/paper/gates.py`)

A paper is publishable only when every gate passes. Nothing repairs it; the local check is the only
place a paper gets fixed.

| Gate | Passes when |
|---|---|
| 1 `artifact` | `theo_citations.validate_paper_artifact(report)` passes |
| 2 `structure` | 1-2 hook paragraphs under the title (no heading), 2-4 investigation sections, `Connecting the Dots`, `The Other Side`, `What We Actually Know`, References, in this order; a blank line after every heading; 5,000-7,500 prose words |
| `meta` | title (at most 80 characters, 4-12 words) and card description (at most 400 characters) follow the house rules |
| 3 `references` | every `[N]` resolves in `sources.json`, and every source id is in the dossier |
| 4 `specifics` | every person, date, measurement, quote, title and institution of a cited paragraph is found in the texts of the sources that paragraph cites (a TDM-reserved source: the live text the claim check saved) |
| 5 `coherence` | every multi-word title term appears in the prose, and the claim check's coherence task finds no numeric conflict |
| 6 `evidence` | `evidence.json` passes the publish gate's own validator (`theo_publishing.check_evidence`: seven keys, `ev-NN` ids, `verdict: "supported"`, each anchor opens exactly one paragraph), then every quote occurs verbatim in its source's archived or live text |
| `page_anchors` | the paper page's own resolver finds every `#ev-NN` in the HTML the page serves |
| 7 `claims` | every claim-check task has an accepted `supported` answer |
| 8 `images` | every embedded image was checked `meaningful` or `weak` and carries licence, attribution, source URL and caption; the file exists; the paper embeds exactly the selected images |
| 9 `hero` | `hero_picker.pick_hero_image` finds a banner among the checked images |
| 10 `quality` | the quality score passes only when gates 1-9 pass and `quality_gate_passed` agrees |

`theo_publish` on the VPS runs its own gates again on every call (section 12.2) and never repairs
either: a local pass that the VPS refuses is a bug in one of the two.

### 4.2 The claim check (`paper claims-export` / `claims-import`)

Every handoff (claims, images, markers) uses the same seam (`pipeline/studio/handoff.py`):

- `tasks.jsonl` (every current task), `pending.jsonl` (tasks without an accepted answer),
  `prompts/<task_id>.txt` (the exact prompt; its sha256 is the task's `prompt_sha256`).
- The workflow answers `pending.jsonl` into `verdicts.jsonl`, one JSON object per line, echoing
  `task_id` and `prompt_sha256`, with `answered_by` set.
- The import validates the whole file and merges it into `accepted.json`. A successful import moves
  the file to `verdicts.imported-<NNNN>.jsonl`, so the next round starts from no file. A refused file
  stays in place, nothing of it merged: correct or replace it and import again.

Tasks (`claims_check/`): one per `evidence.json` entry (`evidence`), one per cited prose paragraph
(`paragraph`), and one per paper with two or more measurements (`coherence`). A task's `cited[]`
lists each source with the reference number `n` its marker shows, its `url`, and its `text_path`
(`texts/<id>.txt`, or null when the archive holds no text).

The theo-claim-check workflow gives every task one verifier, and every `supported` answer an
adversarial skeptic whose id goes into `skeptic_by`. An answer is `{task_id, prompt_sha256, verdict:
supported|partly|unsupported|source_missing, quote, quote_source_id, explanation, fix_suggestion,
answered_by, skeptic_by}`. The import checks by machine, never trusting the answer:

- a `supported` answer has a `skeptic_by` that is not empty, names a `quote_source_id` that is one of
  the task's cited sources, and quotes verbatim from the text of that source;
- a TDM-reserved source (`text_status: tdm_reserved`, `text_path` null) is cited like any source and
  read live (owner decision 16): the verifier fetches its `url` and saves the exact text it read to
  `claims_check/live/<source_id>.txt` (`URL: <url>`, `Fetched: <ISO-8601 UTC>`, an empty line, the
  text). Every verdict except `source_missing` needs that file for every cited TDM-reserved source.
  The file stays local: it is never uploaded or archived. An evidence quote may come from it (Q9).

No machine checks which statement a quote proves, or whether the marker `[n]` that follows that
statement names the source quoted: a `supported` answer whose quote is verbatim from a cited source
that is not the statement's own passes the import. That a statement counts as supported only by the
source its own marker names is the rule of the verifier's prompt (`CLAIM_CHECK_INSTRUCTIONS`) and the
judgement of the verifier and the skeptic alone. Nor does the import check who `skeptic_by` names.

`partly` and `unsupported` block the publish until the paper is fixed and checked again.
`source_missing` (an unfetchable source, or a TDM-reserved page that is unreachable or lacks the
passage) means: re-source the claim or remove it.

### 4.3 The image check (`paper images-export` / `images-import`)

Claude names 4-10 image opportunities in `images/opportunities.json` (`{id, anchor_text, subject,
queries}`, the anchor inside a `##` section, never the hook). The export gathers candidates (the
dossier's image pool plus fresh searches through `image_fetcher.fetch_candidates`, which asks Wikimedia
Commons, Wikidata, the Met and Europeana; its Library of Congress, Getty, Louvre and PAS connectors are
flagged `available = False` and answer nothing), filters them with `image_gates.metadata_gate_passes`, deduplicates, keeps at most 8 per opportunity, downloads
them into `images/candidates/` and exports one task per candidate. `export_report.json` records what
became of every candidate.

The theo-image-check workflow looks at every image and answers `{task_id, prompt_sha256, verdict:
meaningful|weak|misleading|off_topic, depicts, subject_box: [x, y, w, h] | null, caption,
answered_by}` (caption at most 120 characters). The import takes, per opportunity, the first
`meaningful` candidate (then the first `weak` one, captioned as an illustration) that has licence,
attribution and source URL and is not already in the paper, re-encodes it as
`images/selected/s<sha8>_<name>.jpg` and has `paper number` embed it. It refuses while
`opportunities.json` or `draft.md` changed since the export: run `paper images-export` again.

### 4.4 The case-file and marker checks (video)

- **Case file** (studio-casefile-verify workflow): it works on `episodes/<slug>/casefile.json` directly,
  without the CLI. For every evidence item not yet `verified` it checks the statement against its
  source and writes `verification = {status: verified|refuted|unverified, by, at, method}` (`method` is
  the route), leaving every other key untouched. The routes: `papers/<request_id>/evidence.json` when
  `paper_anchor` is set; the archived or saved live text of `source.source_id` in that paper workspace
  (`texts/<id>.txt`, `claims_check/live/<id>.txt`); otherwise the verbatim `source.quote` at
  `source.url`, read live. `episode check` then lets a script use only `verified`
  evidence.
- **Markers** (`episode markers-export`, the studio-marker-check workflow, `episode markers-import`):
  every marker is checked on a crop of its image (`markers_check/crops/<mk>.png`, the box plus a 10 %
  margin) and on the whole image with the box outlined (`context/<mk>.png`); the verdict is `hits` or
  `misses`. `episode check` reports every marker without an accepted `hits` for its current image
  bytes, box and label, so a changed box or picture needs a new check. A picture with markers must
  carry no EXIF rotation.

## 5. Corrections and legacy rewrites

A public paper changes only through `paper correct`, which runs `theo_publish --correct`: first a dry
run, then the apply. Every correction appends at least one entry to the page's corrections log
(`--text T [--evidence-id ev-NN]`, or `--entries FILE` with `[{text, evidence_id?}]`), dated today
(UTC) unless `--date YYYY-MM-DD` says otherwise; a date lies between the publication day and today.
Every record goes to `papers/<id>/corrections/<stamp>.json` with `body_sha256`, the sha256 of the
exact bytes sent.

| Kind | Command | Sends | Notice |
|---|---|---|---|
| Log entry only | `paper correct ID --text T` | `corrections_append` | none |
| Text correction of a studio paper | `... --with-report` | the re-checked `report` and `evidence` | none |
| Full republish of a studio paper | `... --republish` | `bundle.json`'s `result` | `paper_published` |
| Small fix of a legacy paper | `... --report-file FILE` | `report` | none; the stored writer stays |
| Full Claude rewrite of a legacy paper's text | `... --report-file FILE --rewrite` | `report` and `rewrite: true` | `paper_published`; the page shows the Claude disclosure line |
| Rewrite from a fresh Theo run | `paper pull ID --dossier-from RUN`, the session of section 3, then `paper correct ID --text T --republish` | `result` and, on the first republish, `dossier_request_id: RUN` | `paper_published`; RUN ends `cancelled` |

- `--with-report` cannot change the images, the title or the card description: they must equal
  `published_bundle.json`. A change there is a `--republish`.
- A republish keeps the slug, `published_at` and `published_by`: a founder-published paper keeps its
  founder as publisher (owner decisions 17 and 19; 7 of the 31 public papers carry a founder's name).
  It keeps the stored corrections log: the studio sends `result.corrections: []` and theo_publish
  refuses a filled one (Q3).
- Every evidence id published before must stay, unless a correction entry names it (then it is
  retired). A retired id is never reused.
- A legacy paper is one of the 31 M3 papers published before the studio. Its `--report-file` starts
  from the `content` field of `https://ancientnerds.com/api/v1/research/<slug>` and must pass
  `validate_paper_artifact` locally. `paper correct` needs no pulled workspace for it.
- The rewrite basis is the owner's choice per paper (owner decision 18): a fresh Theo run
  (`--dossier-from`) or the stored text (`--report-file --rewrite`). `theo_dossier export` serves only
  3 of the 31 public papers; the other 28 have no dossier.
- Measured read-only on 2026-09-26 (plan A C5): 10 of the 31 public papers fail the quality recompute
  with their stored text. For 9 of them the audit of the stored text fails (uncited paragraphs,
  non-Latin script): a text correction whose report passes `validate_paper_artifact` passes, a
  log-only correction fails. `mogollon-pithouse-sites-across-the-upper-gila` also carries a stored
  `undefined_title_terms = 1` and changes only through a full republish.
- In a `--dossier-from` workspace, `paper pull` refuses RUN unless its export is `researched`. The
  republish's `dossier_source` gate checks RUN again, and the apply closes RUN in the same transaction:
  `status = 'cancelled'`, `error_message = 'dossier used by the republish of <ID>'` (Q10). RUN then
  leaves `theo_dossier list` and the unwritten-dossier cap.

A video joins a paper through `paper register-video ID --youtube-id X --title T --published-at ISO
--timestamps FILE [--poster FILE]` (`episode register-youtube` calls the same steps, section 6; FILE is
`episodes/<slug>/package/evidence_timestamps.json`, the poster `package/thumbnail_<K>.jpg`): a dry run
without the poster, the verified upload of the poster JPEG as `research-images/<ID>/video_<youtube_id>.jpg`,
a dry run with it, then the apply. Without `--poster` the page keeps the posterless player. The first
dry run refuses a video the paper already shows (gate `duplicate`), so repeating a registration whose
outcome is unknown is safe.

## 6. The video session (`studio-video`, `studio-casefile`)

The skills `.claude/skills/studio-video/SKILL.md` and `studio-casefile/SKILL.md` run these steps
without an owner stop before the final package (owner decision 9). The owner decides on full
episodes (owner decision 11); acceptance (c) renders the Baalbek claim-5 slice only. Workspace:
`<STUDIO_ASSETS>/episodes/<slug>/` (file list in `pipeline/studio/episode.py`).

1. `episode init SLUG --topic A|B|C|D [--format full|slice] [--paper ID [--paper-slug S]]
   [--music auto|none|FILE] [--music-credit C]`. With `--paper`, the slug comes from the paper's
   `publish_outcome.json` when it records a successful publish from this machine; otherwise
   `--paper-slug` is required. A music bed needs its credit line.
2. Claude writes `casefile.json` and puts the checked stills into `media/`; the studio-casefile-verify
   workflow verifies the evidence (section 4.4).
3. `episode markers-export SLUG`, the studio-marker-check workflow, `episode markers-import SLUG`.
4. Claude writes `script.json` (spec 4.3 plus `captures`, `thumbnails`), and fills `title_candidates`
   and `tags` in `episode.json`.
5. `episode check SLUG`: exit 1 on errors. Checks that need a capture or the voice are reported as
   deferred and run once those exist.
6. `episode review SLUG` writes `review.html`, the owner's script table. It is not a release gate.
7. `episode voice SLUG`: narrates every beat whose spoken text, voice or speed changed (MiniMax
   `speech-2.8-hd`, the Shorts narrator), then times the display words on CUDA. It refuses below 10 %
   of MiniMax's 5-hour window, which Theo shares; it does not guard the weekly budget.
8. `episode capture SLUG [--only id,id]`: records the captures the script declares (section 9).
9. `episode timeline SLUG`: compiles `timeline.json` (prints its length). `episode render` compiles it
   again itself.
10. `episode render SLUG`: the per-render public dir, the layout lint, the Remotion render on the
    NVIDIA, -14 LUFS, the three thumbnail candidates, the audit, and the ledger row in
    `studio_episodes` (over ssh). The package's description is built right after the timeline is
    compiled, so one over YouTube's 5,000 bytes stops the episode there, before the hours of
    rendering, not at `episode package`.
11. `episode package SLUG` writes `package/`: `<slug>.mp4`, `<slug>.srt`, `description.txt`
    (at most 5,000 bytes, no `<` or `>`), `titles.txt`, `thumbnail_<K>.jpg` (1280x720, under 2 MB)
    with its `thumbnail_<K>_3840.png` master for K = 1, 2, 3, `youtube.json` and
    `evidence_timestamps.json`.
12. The owner reviews the final package (the only release gate). A candidate can be taken from
    another frame: `episode thumbnail SLUG --candidate K --frame N`, then `episode package SLUG` again.
13. The owner uploads by hand (owner decision 10: no OAuth token, upload off) and picks the title and
    the thumbnail test on YouTube.
14. `episode register-youtube SLUG --youtube-id X --title '<the uploaded title>' --published-at
    <ISO with timezone> --poster K`: K is the candidate set on YouTube or the A/B winner, and becomes
    the paper page's video poster (owner decision 13, Q2; required even without a paper). It proves
    the paper registration (dry run, poster upload, dry run), marks the ledger row published, then
    applies the registration.

Rules the checks enforce (script, case file, captures):

- A script uses only `verified` evidence. `display` differs from `spoken` only in how numbers and units
  are spelled (`pipeline/studio/spoken.py`; case is ignored, but only an upper-case Roman numeral is a
  number). The check accepts, spoken then display: a digit with a magnitude word (`six million` /
  `6 million`, `one point five million` / `1.5 million`, `four and a half metres` / `4.5 m`), the British
  `hundred and` (`two hundred and fifty thousand` / `250,000`; where the words allow two readings the
  display may show either), years (`nineteen sixty-six` / `1966`), ordinals and duration compounds
  (`twenty-first` / `21st`, `a thirty-second exposure` / `a 30-second exposure`), decades and centuries
  (`the nineteen-sixties` / `the 1960s`, `the twenty-tens` / `the 2010s`, `the fifteen hundreds` /
  `the 1500s`, `the two thousands` / `the 2000s`), regnal and Roman numerals I-XXXIX in either direction
  (`Ramesses the Second` / `Ramesses II`, `World War Two` / `World War II`), ranges (`twelve to fifteen
  metres` / `12–15 m`), dates (`June the twenty-first` / `June 21`, `the twenty-first of December` /
  `21 December`) and units (`square metres` / `m²`, `two millimetres` / `2 mm`, `twenty-three degrees` /
  `23°`, `fifteen per cent` / `15%`). Anything else is an error that names the first differing token.
- Hook beats total at most 32 s; burned-in captions only in the hook; one hook word has at most 24
  characters in upper case, punctuation included (`HOOK_LINE_MAX_CHARS`).
- Every string a block draws has a `maxLength` in the registry, the measured capacity of its box (a
  lower third's title 21 characters, a block's `title` 41 (a ListCard's 39), the end card's `headline`
  40, a card's `statement` 100 and `quote` 220, an evidence source's `title` 66 and `locator` 24,
  ...), so that `episode check` refuses text the render lint would refuse. Text set in upper-case
  Orbitron (those titles and the headline) is the widest the studio draws, about 0.89 em per character
  for a real site name where prose takes 0.76, so these boxes are proved with the widest real site
  names, not with prose: with prose the lower third held 24 characters and 7 of 50 real names of 19-24
  characters overflowed it (`Sacsayhuaman Walls Cusco`, 781 px of 716), while of the 139 real names of
  21 characters none does and `Normanton Down Barrows` (22) does. A hook beat is drawn under the
  captions on a stage 140 px shorter, where some boxes hold less: the registry also records
  `hookMaxLength` / `hookMaxItems` (an EvidenceCard `statement` 68 and `quote` 120, a QuoteCard
  `quote` 230, at most 5 claims, 4 list items, 6 bars, 2 unit groups, no Meter `note`; each the
  strictest layout of its block) and `episode check` applies them to a beat flagged `hook` (the
  renderer's block checks, to a scene a hook caption is on screen in).
  `video/test/gpu/capacity.gpu.ts` proves it on the workstation by linting every block on both stages
  with every drawn string at its limit (the hook stage at its hook capacity) and the widest real site
  names in every lower third; `video/test/fixtures/capacity-limits.json` and
  `capacity-hook-limits.json` pin the limits it held for, and CI fails when the registry differs;
  `lower-third-names.json` holds the real names a lower third was measured with (the widest that fit,
  which the same test lints clean, and the ones that overflow, which `episode check` now refuses). Not
  covered by a static limit: free-standing labels (a scale object, a diagram element, a timeline
  event, a map pin), which take the room the script gives them; the render lint judges a crowded
  scene.
  Text composed of several fields has a limit on the whole line, not on its parts
  (`video/src/blocks/composed.ts`, mirrored by `pipeline/studio/blocks.py` `composed_errors`, pinned by
  `video/test/fixtures/composed-limits.json`); the block checks refuse a longer line before any browser
  starts, and `capacity.gpu.ts` lints lines of exactly the limit with real hosts, locators and quotes:
  - **BarChart value text** (digits plus unit, with thousands separators and every decimal the value
    has): at most 14 characters for a single value, 16 for a range. `unit` is at most 6 characters,
    but what fits is the whole text: `1,000-1,650 tonnes` (18) is refused, `1,000-1,650 tons` (16),
    `100-165 tonnes` (14), `125,000 tonnes` (14), `1,250 tonnes` and `19.6-20.5 metres` fit. For a
    range with a 4-digit value, the unit has at most 4 characters; with a 3-digit value, 6.
  - **EvidenceCard source line** (`host // tier N // locator // paper #anchor`, the host without
    `www.`): at most 72 characters beside an image, 86 without. The locator limit of 24 therefore
    holds only for a host of up to 12 characters (`jstor.org`, `dainst.org`); beside an image,
    `researchgate.net` leaves 20, `onlinelibrary.wiley.com` 13 and `pubmed.ncbi.nlm.nih.gov` 13
    characters of locator (with `tier 1` and an anchor like `ev-01`).
  - **QuoteCard** meta line (`locator // host // tier N`): at most 94 characters; the work line
    (`attribution, title`) is bounded by its own fields (32 + 2 + 43 = 77, the box holds exactly that).
  When a card is refused for its source line, shorten the case file's locator (or move the card
  to a layout without an image); the host is the source's. An edited locator resets the item to
  `unverified` (re-run `studio-casefile-verify`).
- No title card and no agent block. The ShareCard is the end card: the last beat only.
- A full episode has 3-5 platform moments (a slice any number); every platform moment, in either
  format, lasts 5-15 s.
- Chapters, in every format: the first starts at 0:00, they start at distinct beats in order, and each
  lasts at least 10 s; a full episode has at least 3.
- Every scene showing map content (MapboxTopdown, MapboxFlyover, PlatformClip) carries an in-frame credit
  that holds `© Mapbox` or `© OpenStreetMap`: the beat's own `visual.credit`, or the credits its capture
  recorded (`© Mapbox © Maxar`, `© Mapbox © OpenStreetMap © Maxar`).
- Clip stills (owner Q16): a GlobeShot or MapboxFlyover scene holds one still picture for at most 4 s,
  the render audit's limit, and `episode check` refuses a longer planned hold before the render (once
  the voice and the take exist). The picture changes while the take's camera moves: a fly-to until its
  arrival; a fixed-pose places take (no `sweep_lng_deg`) and an orbit whose start and end bearing are
  equal never move; a sweep, a distribution's turn, a fly-in and a turning orbit move until the take
  ends. From the stop the picture holds to the scene's end. A GlobeShot pin lighting up does not count
  as a change of picture (estimated at 0.03-0.07 against the audit's 0.05 threshold, so the audit sees
  it on a dark globe and misses it on a lighter one), and a platform take, the live page, is judged only
  by the render audit (section 7, "Audit failed").
- Exactly 3 thumbnail candidates, each a teaser of 2-4 words with no verdict word, at a frame that
  cannot show the answer (never inside a twist, verdict or "what would change our mind" beat, never at
  or after the first verdict cue or meter move).
- Distribution dots are `site_ids` of curated `ancient_nerds` sites (owner decision 15, Q11): 1-500
  points, at most 12 of them labelled case-file places. Any other source's id is refused.
- A Mapbox fly-in or orbit's `country` is the site export's country of its place, which must carry a
  `site_id`.
- Platform takes never toggle the `Satellite` base map (owner correction 2026-09-26; satellite shows in
  the details page or a Mapbox take).
- Infographics are linear only: UnitGrid up to 1:400, ScaleZoom beyond (owner decision 31). A BarChart
  bar or a ScaleZoom end bound to a case-file quantity shows exactly its value.
- Picture rules (owner, 2026-09-26): markers only after a crop check, no measuring lines on oblique
  photos (use a ScaleDrawing), comparisons state their basis, no on-screen agents.
- Drawn strings obey the glyph rule (section 10).

## 7. Recovery

- **Exit 1 of `theo_publish`:** the error names the failing gates; fix the paper and run the step
  again from `paper check`.
- **Exit 2:** theo_publish refused the input (the message names the cause). Usually the studio built a
  payload the VPS does not accept: a bug in the studio or in theo_publish, not an operator fix. The
  exception is `research request <id> does not exist`: the id given is wrong, fix it.
- **Exit 3:** the row changed between read and write; nothing was committed. Run `paper check`, then
  the step again.
- **Exit 4, a timeout, no JSON or an unexpected exit (`RemoteOutcomeUnknown`):** the write may have
  committed. Never run it again blind. For `paper publish` and `paper correct` the error prints the
  adoption procedure (`publish.unknown_outcome_steps`):
  1. Read the newest journal row, read-only:
     ```bash
     ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c \"SELECT id, action, slug, bundle_sha256, side_effects FROM theo_paper_publications WHERE request_id = '<id>' ORDER BY id DESC LIMIT 1\""
     ```
  2. Compare its `bundle_sha256` with the hash recorded before the write: `publish_outcome.json`
     `bundle_sha256` for a publish, `corrections/<stamp>.json` `body_sha256` for a correction.
  3. Equal: the write committed; never run it again. After a publish or a `--republish`, copy
     `bundle.json` byte for byte to `published_bundle.json` by hand, before any new `paper bundle`.
     After a publish, `episode init --paper` takes the row's slug as `--paper-slug`.
  4. `side_effects` NULL: IndexNow, Qdrant and the owner notice did not run. The nightly reindex
     covers Qdrant; report the missing notice to the owner.
  5. Another hash: nothing committed; run the step again from its dry run.
- **`register-youtube` failed after the ledger write:** the error prints the `paper register-video`
  command that finishes the registration. Run it, with `./.venv/Scripts/python.exe` for the printed
  `python`; its first dry run refuses a registration that did commit (`duplicate` gate).
- **A ledger write without an answer** is `RemoteOutcomeUnknown` too (`episode render`: `--record`;
  `episode register-youtube`: `--publish`). Read the row of the video's sha256 before running the step
  again; the hash is `row.video_sha256` of `render/ledger.json`, or `sha256sum render/<slug>.mp4` when
  the render stopped before it wrote that file:
  ```bash
  ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c \"SELECT slug, status, youtube_id, published_at FROM studio_episodes WHERE video_sha256 = '<sha256>'\""
  ```
  After a `--publish`, `status = published` with the `youtube_id` means it committed: finish the
  registration on the paper with the `paper register-video` command of section 5 (`episode
  register-youtube` finds no `rendered` row any more); `rendered` means nothing committed, run
  `episode register-youtube` again.
- **Stale voice:** `episode timeline` and `render` refuse `voice/<beat>.mp3 is stale; run episode
  voice` (or `is missing`) when a beat's spoken text, the voice or the speed changed. `episode voice`
  narrates only those beats again (and pays only for them); a changed display text is only re-timed.
  A beat edited since its voice counts as estimated (not measured by the old `voice/words.json`)
  until it is voiced again: `episode check` lists it under `deferred` (`voice/<beat>.mp3 is stale`),
  so a hook, platform moment, chapter or clip scene that the old durations had broken never stops
  `episode voice` from measuring the new text. Its estimate still counts for the hook length and the
  platform moments, as before the first voice.
  A transcription that fails (`the display words cannot be timed against voice/<beat>.mp3`) keeps the
  narration already paid for, and that beat counts as estimated too (`voice/words.json` is written
  last, so it still holds the old duration): run `episode voice` again, it times the beat without
  narrating it twice.
- **A capture on a sleeping display:** headed Chrome stops drawing, and the take waits for a frame
  that never comes. The captures hold the display awake while they run, but cannot wake one that is
  already off or locked, and the recorder scenes fail within 30 s without a frame. Unlock the display
  and record again (`episode capture SLUG --only <id>`). A retake first removes the capture's stored
  manifest, so a failed take counts as not recorded.
- **Port in use:** a take refuses a port that answers (`port 5198 is in use ... netstat -ano |
  findstr :5198`): a dev server left by an interrupted take, or another session's capture. Stop that
  process, then record again. The recorder (`ancient-nerds-map/video/record.ts`) uses port 5199 and
  starts Vite with `--strictPort` too.
- **Lint violations:** `episode render` stops after `lint.ts` (`lint.ts exited 1; see
  render/lint_report.txt`). Each violation is one JSON line `{"type": "layout-violation", "frame",
  "a", "b", "reason"}` with reason `overflow` (text clipped by its box), `outside-safe` (text outside
  the title-safe area), `offscreen` (a marker leaves the frame), `controls` (under YouTube's player
  controls) or `overlap`. Fix the script props (shorter text, another marker, another block) and render
  again; fixing props never makes the voice stale.
- **Audit failed:** `episode render` stops with `render audit failed [...]; see render/audit.json`
  (format, exact duration, black frames, frozen clip runs over 4 s, loudness, true peak). `episode
  package` then writes `package/FAILED.json` with the reasons and stops. Fix the cause (a frozen take:
  cut to a card or record again) and render again. A still picture the script plans (a fly-to's hold
  after its arrival, a fixed pose, an orbit that does not turn) never gets this far: `episode check`
  refuses it first (owner Q16, section 6). What reaches the audit is a live platform take that stalls.
  An audit whose black-frame or frozen-run probe decoded no frames fails too (`ffmpeg decoded no frames
  of ...`) instead of passing unmeasured.
- **"timeline.json changed since the render"** or **"render/<slug>.mp4 is not the audited render":**
  run `episode render` again; `episode package` builds only from the audited render of the current
  timeline, and refuses a script, case file, word timings or music file edited after the render
  (`<file> changed since the render`; `episode thumbnail` checks timeline.json and script.json): the
  SRT, the hook sentence, the evidence lines and the credits would describe another video. Titles,
  tags and the wording of the music credit may change after it.
- **A killed or failed node step** removes `render/bundle/` and `render/raw.mp4.parts/` itself; a
  node script that times out is killed with its whole process tree.
- **A render page closed or crashed (owner Q17):** `lint.ts`, `render.ts` and `still.ts` watch the pages
  of the browser they proved on the NVIDIA. When one is closed from outside (someone closes the render
  tab) or crashes, the run is cancelled at once and fails with `render.ts exited 1; see
  render/render_log.txt`, whose stderr says `a render page of the proved browser was closed from
  outside mid-render` or `... crashed mid-render; the render was cancelled at once (owner decision
  Q17)`. Before Q17 such a render could hang until Remotion's 123 s ready timeout, or Remotion could
  replace the browser with one that was never proved. Nothing is wrong with the script: render again.
- **MiniMax below 10 % of the 5-hour window:** `episode voice` refuses; wait for the window to refill.
- **A refused handoff import:** the verdicts file stays in place and the error lists every problem;
  correct or replace it, then import again.

## 8. The GPU rule and `doctor`

Owner rule (spec 4.11): every GPU workload runs on the NVIDIA RTX 3080, never on the integrated AMD.
A run that would land on the AMD or on software rendering fails loudly instead.

- **Chrome for captures** runs with `--use-angle=d3d11 --force_high_performance_gpu
  --force-high-performance-gpu --enable-gpu-rasterization --ignore-gpu-blocklist`
  (`capture/gpu.py`). Without them Chrome drew on the AMD (measured 2026-09-26).
- **Remotion's browser** takes no Chromium flags: `doctor --fix-gpu` sets the Windows per-app
  preference `GpuPreference=2;` under `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` for its
  headless shell. The renderer draws on the NVIDIA only through ANGLE.
- **Proof, not assumption:** every capture, and every `lint.ts`, `render.ts` and `still.ts` run, reads
  WebGL's `UNMASKED_RENDERER_WEBGL` in the page it drives and stops unless it names the NVIDIA. The
  node scripts print one `gpu: <renderer>` line per browser (see `render/lint_report.txt`,
  `render_log.txt`, `still_<K>_log.txt`), and `render.py` refuses any other. The manifest of every
  browser capture (source page, platform, globe, Mapbox fly-in and orbit) starts with the event
  `{"t": 0, "name": "gpu", "label": <renderer>}`; a `mapbox_topdown` still comes from the Static Images
  API without a browser, so its manifest holds only its `pin` events. The render ledger's `renderer`
  column holds the render browser's string. The expected string is `ANGLE (NVIDIA, NVIDIA GeForce RTX 3080
  Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)`.
- **Encoding** runs on NVENC with `-gpu 0`: `hevc_nvenc` for capture clips, `h264_nvenc` for the
  render. There is no software encode path.
- **Transcription** runs on CUDA device 0 in float16 (section 1.3).

`doctor` probes: the studio assets root, `ffmpeg`, `ffprobe`, `node`, `video/node_modules`, the block
registry, the site fonts, the Python modules (faster_whisper, mutagen, PIL, playwright, the capture
package), `nvidia-smi` naming the RTX 3080, NVENC (both encoders encode a test frame on GPU 0), CUDA
for faster-whisper, Remotion's browser and its GPU preference, the renderer of a headless Chrome
launched as the captures launch it, `LYRA_MINIMAX_API_KEY`, the music bed, the site export and its
age, and `ssh ancientnerds`. A green
`doctor` says the machine is set up; the first `lint.ts` of an `episode render` says Remotion's browser
really uses the NVIDIA.

Checks only the workstation can run (CI never proves the capture and render path): `npm run test:gpu`
in `video/` (3 files, 19 tests: the layout lint in a real browser on the NVIDIA, every block at its
length limits, real quotes, source lines and bar values at exactly their limits, and a crashed and a closed render tab that each cancel the run at once, owner Q17;
about 330 s, measured 2026-10-02), the
smoke render (plan D Task 22), real captures (plan D Task 36), `doctor`, and the CUDA transcription.
What CI does prove of `video/` is section 13.

## 9. Captures

`episode capture` hands each capture spec of `script.json` to its recorder and stores the manifest as
`captures/<id>.json` with `spec_sha256`, the hash of the resolved spec: a manifest whose spec changed
since counts as not recorded.

| Kind | Recorder | Output |
|---|---|---|
| `source` | `capture/sources.py`: Playwright on the NVIDIA, the quote found in the text readers see and highlighted, banners hidden; also our paper page scrolled to `#ev-NN` | a still; credit `Source page: <ASCII host>` (our paper page: none) |
| `mapbox_topdown` | `capture/mapbox.py`: an exact Mapbox Static frame with pins projected onto their objects | a still; `© Mapbox © Maxar` (`satellite-v9`) or `© Mapbox © OpenStreetMap © Maxar` (`satellite-streets-v12`) |
| `platform` | `capture/platform.py`: the real site in headed Chrome, CDP screencast, fast NERV cursor | an HEVC clip; `© Mapbox © OpenStreetMap © Maxar` |
| `globe` | `capture/globe.py` through the recorder `npm run video:record` (`studio-globe-flyto`, `studio-globe-places`, `studio-mapbox-flyin`, `studio-mapbox-orbit`) | an HEVC clip; our vector globe has no credit, a Mapbox take has the Mapbox credit |

### 9.1 The local site and the recorder

A platform take with `target: local` runs `npm run dev -- --port 5198 --strictPort` in
`ancient-nerds-map/` with `VITE_DEV_API_TARGET=https://ancientnerds.com` and `VIDEO_RECORD=1` (no file
watching, no reload mid-take); the page is `globe.html?demo=1&video=1&hud=<scale>`. It reads the site
data from the checkout's `public/data/` (section 11). `target: production` needs the deployed
`?video=1` mode: without it the page never gets ready and the take fails after 120 s (plan D Task 30).
`local_site()` refuses a port that already answers and counts the site as ready only when its own Vite
announces the port (section 7); the recorder uses port 5199 with `--strictPort`. Every Playwright
capture blocks the site's Umami tracker (`/pulse.js`), so no take counts as a visit.

### 9.2 An awake, unlocked display

Headed Chrome draws only while the Windows display is on. The first studio Mapbox fly-in
(2026-09-26) hung for 15 minutes when the display slept; with the display throttled, a 5-second
globe take crawled for 7 minutes. The captures hold the display awake (`vite.display_awake`,
`SetThreadExecutionState`) but cannot wake it. Keep it on and unlocked for the whole capture run.

### 9.3 Why capture clips are HEVC

Remotion decodes a clip with Chrome's `VideoDecoder` through Mediabunny. `h264_nvenc` writes no VUI
`bitstream_restriction`, so Mediabunny assumes the largest reorder depth and the decoder holds its
frames back: every render over an `h264_nvenc` clip timed out ("Timeout while extracting frame at time
0.1sec"), while `libx264` and `hevc_nvenc` clips rendered (measured 2026-09-26, Remotion 4.0.529).
`libx264` is a software encoder, which the GPU rule forbids; an HEVC stream always carries its reorder
count (0 here). So every clip is `hevc_nvenc` on GPU 0: BT.709 limited range, a constant 60 fps, a
keyframe every second, no B-frames, tag `hvc1`, faststart (`capture/encode.py`). Decoding then relies
on Chrome's hardware HEVC decoding on the RTX 3080: a machine without it cannot render the captures.
The rendered episode itself is H.264 (`h264_nvenc`).

### 9.4 How long a Mapbox fly-in takes

A Mapbox fly-in waits for its tiles on every frame: a 5-second take took 17 minutes on 2026-09-26.
Budget up to about 20 minutes per fly-in and do not interrupt it. The recorder may run 10 minutes
plus 6 s per frame (`record_timeout_s` in `capture/globe.py`): 40 minutes for a 5-second fly-in,
190 minutes for a 30-second take. A scene whose renderer is not the NVIDIA stops at its first frame.

### 9.5 Platform takes: the action vocabulary

The `actions` of a platform take are `pause_rotation`, `search {q}`, `click_result {title}`,
`fly_wait {s}`, `zoom {to}`, `open_details {title}`, `measure {a, b}`, `toggle_layer {label, empire?}`,
`proximity {at}`, `filter {mode, label}` and `wait {s}` (`ACTIONS` and `OPTIONAL` of
`capture/platform.py`, pinned by a test). A platform or globe take lasts at most 30 s. The points of
`measure` and `proximity` are case-file places, clicked where the page itself draws them; every click
scrolls its target into view and fails the take when anything but the target (or, for a point, the map
canvas) would take it. `toggle_layer` clicks one toggle of the Layers panel and fails the take unless its
checkbox flips:

- never `Satellite` (owner correction 2026-09-26; satellite shows in the details page or a Mapbox take);
- `Empire Borders` only opens its window, so it needs `empire`, an id of
  `pipeline/historical_boundaries/empire_metadata.py`; the take draws it at its peak extent with the
  window's By Period timeline off. At most one per take (a second click closes the window); `empire` on
  any other toggle is refused;
- every `toggle_layer` belongs before the `zoom` into the Mapbox view: there the Layers panel disables
  its vector layers and `Labels` and an empire only tints the map, so a `toggle_layer` in that view fails
  the take before its click;
- `Geological Layers` and `Historical Routes` are refused: no action picks from their windows.

A Mapbox take's `country` must be the site export's country of its place and a name the site's country
table knows (the recorder refuses an unknown name and the take fails).

## 10. The glyph rule

Every string the video draws must lie in the code points the loaded brand font files map (`DRAWABLE`
in `video/src/theme/glyphs.ts`, generated from the files' cmaps; `pipeline/studio/glyphs.py` holds a
verbatim copy that the tests compare). A character outside it would render in a Windows system font.

- Only drawn strings are checked (owner decision 32): the props at each block's registry `drawn`
  paths, a capture's credits and its `place`/`pin` labels, hook captions, credit lines, chapter titles
  and thumbnail teasers. A QuoteCard's quote is drawn and must pass.
- Not checked: ids, paths, URLs, an original quote inside a captured source page, and a page's own
  `<title>` (kept in the capture's `page` event as a record, never drawn: SourceViewer and the credit
  show only the ASCII hostname, Q12).
- A character is checked in upper case too: `ƒ` draws as `Ƒ` and is refused; `µ` is refused as written
  (write `micrometre`).
- Refused as well (Q14): `Ḫ Ḥ Ṣ Ṭ Ṛ Ṃ Ṇ Ḍ Ṯ Ḏ Ẓ`, `ʾ ʿ`, the hyphens U+2010-2012 and `‰`. Write
  `Hattusa`, `Hathor`, `Krishna`.
- `episode check` names the refused character before voice and capture; `captures.py` refuses a
  manifest whose credit or label holds one; the renderer's `checkBlocks` refuses the same in `lint.ts`.

## 11. Site-export freshness

The distribution dots (owner decision 15), a Mapbox take's `country` and every local platform or globe
take read the repo-root export `public/data/sites/index.json` of the checkout the studio runs in. It is
gitignored and more than 360 MB. The main checkout's copy dates from 2026-03-26, before the 2026-09 sites
remediation corrected coordinates and retired 78 sites; this worktree's copy was downloaded on 2026-09-25
(`doctor` reports the age of the copy in the checkout it runs in). Before the first
capture that needs it, download the current export read-only from production, from the root of that
checkout (owner question Q4):

```bash
curl -sfR --create-dirs -o public/data/sites/index.json https://ancientnerds.com/data/sites/index.json
```

`--create-dirs` makes the gitignored directory, and `-R` keeps the server's Last-Modified as the file's
mtime, the age `doctor` reports (`sites.DOWNLOAD`). Never write into the main checkout from a worktree.
When the studio runs in the main checkout, refresh that checkout's copy the same way before its first
distribution capture (Q4 addendum). A changed export changes the resolved
spec, so the affected takes are recorded again.

## 12. Theo on the VPS

### 12.1 What Theo does now

Theo researches only. After the moderator, the `DossierHandler` stores the dossier in
`research_artifacts` (kinds `dossier`, `moderated`, `synthesis`, `debate`, `angle_findings`,
`specialist_analyses`, `citation_registry`, `image_candidate_pool`), runs archive completion (the full
texts of the sources moderated claims cite: Wikipedia, doi.org and YouTube transcripts included,
TDM-reserved sources skipped and recorded), and the worker ends the run as `researched` with
`result_json = {"dossier": <manifest summary>, "title": null}`. It writes a `thinking_log` event
`dossier_ready`; the owner list shows "Researched · awaiting write". Nothing is auto-published. The
four Theo host scripts are retired (owner decision 22).

### 12.2 The CLIs (API image)

```bash
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier list
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier export <id> [--texts all] > dossier.json.gz
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --dry-run < bundle.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --apply < bundle.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --correct [--dry-run] < correction.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --register-video [--dry-run] < video.json
```

The studio runs them for you (`paper list`, `pull`, `publish`, `correct`, `register-video`); run them
by hand only to inspect.

- `theo_dossier list` prints the `researched` rows with their dossier summary (JSON, oldest first).
  `export` writes gzip'd JSON to stdout (`--texts cited`, the default, carries the texts of the sources
  the moderated claims cite, `--texts all` those of every source); a run without a `dossier` manifest (e.g. 95fa3798) exports
  from its per-stage artifacts with `"legacy": true`. Exit codes: 0 ok, 1 no or incomplete dossier,
  2 bad request id.
- `theo_publish` reads one JSON object on stdin: `publish` `{version, request_id, writer, result}`;
  `correct` adds `corrections_append` and optionally `report`, `evidence`, `result`, `rewrite`,
  `dossier_request_id`; `register_video` `{version, request_id, writer, youtube_id, title,
  published_at, evidence_timestamps}` plus optionally `poster`. `request_id` is a canonical lowercase
  UUID. It prints one `PublishOutcome` JSON (`ok`, `action`, `slug`, `url`, `gates`, `side_effects`,
  `journal_id`) or `{"ok": false, "error": ...}`. Exit codes: 0 ok (a failed side effect is reported,
  not fatal), 1 a gate failed, 2 unusable input, 3 the row changed between read and write (nothing
  committed), 4 committed but the re-read row differs (side effects not run).
- Gates per action: `publish` = `status`, `shape`, `snapshot`, `artifact`, `quality`, `evidence`,
  `retention`, `images`, `page`; `correct` = `status`, `shape`, `retention`, `artifact`, `quality`,
  `evidence`, `images`, `page` (a full republish adds `snapshot`, and `dossier_source` with
  `dossier_request_id`); `register_video` = `status`, `shape`, `evidence_refs`, `duplicate`, `images`,
  `page`. A dry run of a publish on a public row answers `apply_allowed: false`.
- Side effects: a publish runs IndexNow, Qdrant and the owner notice; a correction re-runs IndexNow and
  Qdrant, plus the notice for a full republish and a `rewrite: true` text correction; a video
  registration runs IndexNow. Dry runs write nothing and notify nobody.

### 12.3 The journal and the guard

Every committed write inserts a row into `theo_paper_publications` (migration 0025: `action`
`publish|correct|register_video`, `slug`, `writer`, `bundle_sha256` = sha256 of the exact stdin
bytes, `gates`, `side_effects`; `request_id` `ON DELETE SET NULL`). Dry runs are not journalled.

A journalled paper (its `result_json` carries `evidence`, `videos`, `corrections` or `writer`,
`theo_publishing.JOURNALLED_PAPER_SQL`) changes only through `theo_publish`. The `result_json`
maintenance tools (`pipeline/lyra/backfill_hero_image.py`, `backfill_probative_images.py`,
`clean_image_titles.py`, `fix_source_urls.py`, `reflow_images.py`, `rewrite_image_captions.py`,
`scripts/apply_meaningful_gallery.py`, `repair_theo_citations.py`, `swap_theo_payload.py`) skip such a
paper, refuse it when a run names it, and never write onto one journalled after their read. The founder
approval (`POST /theo/research/{id}/approve`) answers 409 for a public row. The founder publish route
runs the page and anchor checks and stores `writer.published = "manual"`, `human_review: true` (Q7).
Any new writer of `result_json` must do the same: a stored paper whose extras do not validate answers
HTTP 500 on `/research/{slug}`.

### 12.4 Config knobs (`api/services/theo_config.py`, `pipeline/lyra/archive_completion.py`)

| Variable | Default | Meaning |
|---|---|---|
| `THEO_RUN_COST_PCT` | 9 | weekly-budget share of one research-only batch run |
| `THEO_RUN_EST_HOURS` | 11 | wall-clock estimate of one run while no research-only history exists |
| `THEO_MAX_UNWRITTEN_DOSSIERS` | 6 | the feeder stops enqueueing while this many rows are `researched` |
| `THEO_ARCHIVE_COMPLETION_MAX_S` | 1800 | time budget of archive completion; at most 2400 (below the worker's 2700 s stall guard) |
| `THEO_ARCHIVE_COMPLETION_CONCURRENCY` | 4 | parallel fetches of archive completion |
| `THEO_WORKER_DISABLED` | unset | `1` makes the worker idle (set on the owner's behalf since 2026-09-26) |
| `DISCORD_WEBHOOK_URL` | unset | the Discord copy of the owner notices; unset by owner decision 5 |

## 13. The renderer (`video/`) and its CI gates

`video/` is the Remotion 4.0.529 project; every `@remotion/*` package and every other dependency in
`video/package.json` is pinned to an exact version. `npm run studio` previews the demo timeline
(`remotion studio src/index.ts --public-dir ../ancient-nerds-map/public`). `episode render` and
`episode thumbnail` run `scripts/lint.ts`, `render.ts` and `still.ts` as `node --import tsx
scripts/<name>.ts` with `video/` as the working directory; they bundle into the episode's transient
`render/bundle/`. `video/src/blocks/registry.json` is generated (`npm run registry`) and read by
`pipeline/studio/blocks.py`; `tests/pipeline/studio/test_registry_contract.py` checks the studio's
mirrors of the renderer.

CI proves the part that needs no GPU:

- **`lint-video`** runs `npm ci`, `npx tsc --noEmit` and `npx vitest run` in `video/` on Linux whenever
  the `video` path filter of `.github/workflows/ci.yml` matches: `video/**`,
  `tests/pipeline/studio/golden_timeline.json`, the site's `tokens.css` and `colors.ts` and
  `ancient-nerds-map/public/fonts/**`. A red `lint-video` blocks the deploy, a skipped one does not. The
  pre-push hook runs the same two commands for a push to `main` that changes such a path.
- **`security-scan`** runs a blocking `npm audit --audit-level=critical` in `video/` (a change of
  `video/package.json` or `video/package-lock.json` starts the job). It is clean since vitest went from
  4.0.18 to 4.1.11 on 2026-09-30: 4.0.18 carried GHSA-5xrq-8626-4rwp (critical: with the Vitest UI
  server listening, an arbitrary file can be read and executed) and GHSA-82fw-gwwq-j7x9 (moderate, in
  `@vitest/mocker`). A critical advisory in the lockfile fails the deploy: bump that package, pinned
  exactly like the rest, and do not ignore the advisory.
- The `backend` filter also matches `video/src/blocks/registry.json`, `video/src/theme/glyphs.ts` and
  `video/src/captions.ts`, which the studio's Python contract tests read.
- `tests/pipeline/studio/test_workflows.py` runs the four workflows under `node` against canned agent
  answers (`workflow_harness.mjs`), so the backend tests need Node as the studio does.

What only the workstation proves is `npm run test:gpu` (section 8), the smoke render and the real
captures.
