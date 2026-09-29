# Studio runbook: the Claude paper write and the video studio

Theo researches on the VPS and stops at a dossier (status `researched`). A local Claude Code session
then writes, checks and publishes the paper through gated VPS CLIs (the paper studio), and turns a
published paper into a YouTube episode (the video studio). This runbook says how to set the
workstation up, how the two sessions run, what every gate checks, how to correct a published paper,
and how to recover when a step fails.

Binding sources: the spec `docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md`, the
owner decisions in `docs/superpowers/plans/2026-09-26-owner-questions.md` (#1-#32, Q1-Q14), the build
index `docs/superpowers/plans/2026-09-26-00-index.md` and the four stream plans beside it. Where this
file and the code disagree, the code is right and this file is stale: fix it.

## 0. State on 2026-09-29

- **Built on `feat/studio`, not released.** Production runs `main`: it has neither migrations 0025
  (`theo_paper_publications`) and 0026 (`studio_episodes`) nor the modules `pipeline.lyra.theo_publish`,
  `pipeline.lyra.theo_dossier` and `pipeline.studio.ledger_cli`. Until the release (index item I8),
  every step that reaches production cannot run: `paper list`, `pull`, `publish`, `correct`,
  `register-video`, the ledger write at the end of `episode render`, and `episode register-youtube`.
- **Theo is stopped by the owner.** The VPS `.env` has `THEO_WORKER_DISABLED=1` since about
  18:20 UTC on 2026-09-26; the worker idles (`scripts/run_theo_worker.py`) and 24 batch rows are
  `paused`. No new `researched` row arrives until the owner restarts Theo (owner question Q1).
- **Not committed yet:** plan D Tasks 30-32, i.e. `pipeline/studio/capture/platform.py`,
  `pipeline/studio/capture/globe.py` and the four entry points of `pipeline/studio/capture/__init__.py`.
  Until they land, `episode capture` cannot record anything. Sections 6 and 9 describe platform and
  globe takes from plan D's definitions. Source-page captures (`capture/sources.py`) and Mapbox
  top-down frames (`capture/mapbox.py`) are committed.
- **Skills and workflows:** the skills `.claude/skills/theo-write`, `studio-video` and
  `studio-casefile` are committed (integration item I2). The workflows
  `.claude/workflows/theo-claim-check.js`, `theo-image-check.js`, `studio-casefile-verify.js` and
  `studio-marker-check.js` are item I3. The skills hold the step-by-step session; this runbook holds
  the background, the gates and the recovery.
- **Workstation proofs outstanding:** the smoke render (plan D Task 22) and the real captures (plan D
  Task 36) are re-run on the finished code before the release, and one real CUDA float16 transcription
  (section 1.3) has not run yet.

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

It prints a word count. If a CUDA library fails to load, install the missing NVIDIA library, pinned
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
- Output is JSON on stdout, UTF-8 whatever the console code page.
- Exit codes: 0 success; 1 a check or gate failed (`paper check`, `episode check`, `episode voice`,
  `doctor`); 2 a `StudioError`, whose message (`error: ...` on stderr) says what to fix. A traceback
  is a bug, not an operating state.
- Production is reached only through ssh plus `docker exec -i ancient_nerds_api python -m <module>`
  for three modules (`remote.ALLOWED_MODULES`: `theo_dossier`, `theo_publish`, `ledger_cli`), and
  through scp into `/var/www/ancientnerds/public/data/research-images/<request_id>/`, verified byte for
  byte with `sha256sum`. Production credentials never leave the VPS. Nothing retries automatically.
- Every model judgement is Claude's, made in the session or by a workflow, and handed to the code as
  files. No studio code calls a model API.

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
- `paper bundle` and `paper publish` refuse when the paper, `evidence.json` or `paper_meta.json`
  changed since the check, or when `bundle.json` no longer matches the paper.
- Publishing is automatic: the skill applies when every gate passes (spec 0). `paper publish ID
  --dry-run` stops after the dry run.
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

- a `supported` answer names its skeptic and quotes verbatim from the text of `quote_source_id`;
- a statement counts as supported only by the source its own marker `[n]` names;
- a TDM-reserved source (`text_status: tdm_reserved`, `text_path` null) is cited like any source and
  read live (owner decision 16): the verifier fetches its `url` and saves the exact text it read to
  `claims_check/live/<source_id>.txt` (`URL: <url>`, `Fetched: <ISO-8601 UTC>`, an empty line, the
  text). Every verdict except `source_missing` needs that file for every cited TDM-reserved source.
  The file stays local: it is never uploaded or archived. An evidence quote may come from it (Q9).

`partly` and `unsupported` block the publish until the paper is fixed and checked again.
`source_missing` (an unfetchable source, or a TDM-reserved page that is unreachable or lacks the
passage) means: re-source the claim or remove it.

### 4.3 The image check (`paper images-export` / `images-import`)

Claude names 4-10 image opportunities in `images/opportunities.json` (`{id, anchor_text, subject,
queries}`, the anchor inside a `##` section, never the hook). The export gathers candidates (the
dossier's image pool plus fresh searches in Commons, Europeana, Smithsonian, Met and NARA), filters
them with `image_gates.metadata_gate_passes`, deduplicates, keeps at most 8 per opportunity, downloads
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
  source (the verbatim `source.quote` at `source.url`, or `papers/<request_id>/evidence.json` when
  `paper_anchor` is set) and writes `verification = {status: verified|refuted|unverified, by, at,
  method}`, leaving every other key untouched. `episode check` then lets a script use only `verified`
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
--timestamps FILE [--poster FILE]` (`episode register-youtube` calls the same steps, section 6): a dry
run without the poster, the verified upload of the poster JPEG as
`research-images/<ID>/video_<youtube_id>.jpg`, a dry run with it, then the apply. Without `--poster`
the page keeps the posterless player.

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
    `studio_episodes` (over ssh).
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

- A script uses only `verified` evidence, and `display` differs from `spoken` only in how numbers and
  units are spelled.
- Hook beats total at most 32 s; burned-in captions only in the hook; one hook word has at most 24
  characters in upper case, punctuation included (`HOOK_LINE_MAX_CHARS`).
- No title card and no agent block. The ShareCard is the end card: the last beat only.
- A full episode has 3-5 platform moments of 5-15 s each (slices are exempt), at least 3 chapters,
  the first at 0:00, each at least 10 s.
- Every scene showing map content carries its in-frame credit (`© Mapbox © Maxar`, `© OpenStreetMap`).
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
- **Exit 2:** theo_publish refused the input (the message names the key). The studio built a payload
  the VPS does not accept: a bug in the studio or in theo_publish, never an operator fix.
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
  command that finishes the registration. Run it; its first dry run refuses a registration that did
  commit (`duplicate` gate).
- **A ledger write without an answer** is `RemoteOutcomeUnknown` too: read `studio_episodes` for the
  video's sha256 before running `episode render` again.
- **Stale voice:** `episode timeline` and `render` refuse `voice/<beat>.mp3 is stale; run episode
  voice` when a beat's spoken text, the voice or the speed changed. `episode voice` narrates only
  those beats again (and pays only for them); a changed display text is only re-timed.
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
  cut to a card or record again) and render again.
- **"timeline.json changed since the render"** or **"render/<slug>.mp4 is not the audited render":**
  run `episode render` again; `episode package` builds only from the audited render of the current
  timeline.
- **A killed or failed node step** removes `render/bundle/` and `render/raw.mp4.parts/` itself; a
  node script that times out is killed with its whole process tree.
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
  `render_log.txt`, `still_<K>_log.txt`), and `render.py` refuses any other. A capture manifest's first
  event is `{"t": 0, "name": "gpu", "label": <renderer>}`, and the render ledger's `renderer` column
  holds the render browser's string. The expected string is `ANGLE (NVIDIA, NVIDIA GeForce RTX 3080
  Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)`.
- **Encoding** runs on NVENC with `-gpu 0`: `hevc_nvenc` for capture clips, `h264_nvenc` for the
  render. There is no software encode path.
- **Transcription** runs on CUDA device 0 in float16 (section 1.3).

`doctor` probes: the studio assets root, `ffmpeg`, `ffprobe`, `node`, `video/node_modules`, the block
registry, the site fonts, the Python modules (faster_whisper, mutagen, PIL, playwright, the capture
package), `nvidia-smi` naming the RTX 3080, NVENC on GPU 0, CUDA for faster-whisper, Remotion's
browser and its GPU preference, the renderer of a headless Chrome launched as the captures launch it,
`LYRA_MINIMAX_API_KEY`, the music bed, the site export and its age, and `ssh ancientnerds`. A green
`doctor` says the machine is set up; the first `lint.ts` of an `episode render` says Remotion's browser
really uses the NVIDIA.

Checks only the workstation can run (CI never proves the capture and render path): `npm run test:gpu`
in `video/` (the layout lint in a real browser on the NVIDIA, about 70 s), the smoke render (plan D
Task 22), real captures (plan D Task 36), `doctor`, and the CUDA transcription.

## 9. Captures

`episode capture` hands each capture spec of `script.json` to its recorder and stores the manifest as
`captures/<id>.json` with `spec_sha256`, the hash of the resolved spec: a manifest whose spec changed
since counts as not recorded.

| Kind | Recorder | Output |
|---|---|---|
| `source` | `capture/sources.py`: Playwright on the NVIDIA, the quote found in the text readers see and highlighted, banners hidden; also our paper page scrolled to `#ev-NN` | a still; credit `Source page: <ASCII host>` (our paper page: none) |
| `mapbox_topdown` | `capture/mapbox.py`: an exact Mapbox Static frame with pins projected onto their objects | a still; `© Mapbox © Maxar` (`satellite-v9`) or `© Mapbox © OpenStreetMap © Maxar` (`satellite-streets-v12`) |
| `platform` | `capture/platform.py` (plan D Task 30, not committed): the real site in headed Chrome, CDP screencast, fast NERV cursor | an HEVC clip; `© Mapbox © OpenStreetMap © Maxar` |
| `globe` | `capture/globe.py` (plan D Task 31, not committed) through the recorder `npm run video:record` (`studio-globe-flyto`, `studio-globe-places`, `studio-mapbox-flyin`, `studio-mapbox-orbit`) | an HEVC clip; our vector globe has no credit, a Mapbox take has the Mapbox credit |

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
Budget up to about 20 minutes per fly-in and do not interrupt it. The recorder's limit per take is
90 minutes (`RECORD_TIMEOUT_S`, plan D Task 31).

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
remediation corrected coordinates and retired 78 sites; the worktree has none. Before the first
capture that needs it, download the current export read-only from production, from the root of that
checkout (owner question Q4):

```bash
curl -sfR --create-dirs -o public/data/sites/index.json https://ancientnerds.com/data/sites/index.json
```

`--create-dirs` makes the gitignored directory, and `-R` keeps the server's Last-Modified as the file's
mtime, the age `doctor` reports (`sites.DOWNLOAD`). Never write into the main checkout from a worktree.
Once `feat/studio` is merged and the studio runs in the main checkout, refresh that checkout's copy the
same way before its first distribution capture (Q4 addendum). A changed export changes the resolved
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
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier export <id> [--texts cited|all] > dossier.json.gz
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --dry-run < bundle.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --apply < bundle.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --correct [--dry-run] < correction.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --register-video [--dry-run] < video.json
```

The studio runs them for you (`paper list`, `pull`, `publish`, `correct`, `register-video`); run them
by hand only to inspect.

- `theo_dossier list` prints the `researched` rows with their dossier summary (JSON, oldest first).
  `export` writes gzip'd JSON to stdout; a run without a `dossier` manifest (e.g. 95fa3798) exports
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
| `THEO_WORKER_DISABLED` | unset | `1` makes the worker idle (set by the owner since 2026-09-26) |
| `DISCORD_WEBHOOK_URL` | unset | the Discord copy of the owner notices; unset by owner decision 5 |
