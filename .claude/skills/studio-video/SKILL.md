---
name: studio-video
description: Use when making a YouTube episode or slice from a Theo paper or topic with the local studio (python -m pipeline.studio episode), when an episode step (check, voice, capture, timeline, render, package, thumbnail) refuses, or when the owner reports a manual YouTube upload that must be recorded with register-youtube.
---

# Studio video: from case file to upload package

## Overview

The studio turns a verified case file into a frame-exact NERV video, rendered by Remotion on
the NVIDIA RTX 3080, and an upload package. Claude writes the case file and the script; the code
validates, narrates, captures, compiles, renders and packages.

**The run does not stop for the owner before the final package** (owner #9): `review.html` is a
table for the owner, not a gate. The owner reviews the package, uploads it by hand (#10) and
decides which full episodes are made (#11); do not start a full episode on your own.

Run every command from the checkout root as `./.venv/Scripts/python.exe -m pipeline.studio …`,
written `studio …` below. Exit 0 = ok, 1 = a check failed (`episode check`, `episode voice`,
`doctor`), 2 = a `StudioError` (message on stderr). The episode lives in
`<STUDIO_ASSETS>/episodes/<slug>/`.

## Before the first step

- `studio doctor` reports every probe ok. Once per machine, after
  `cd video && npm ci && npx remotion browser ensure`: `studio doctor --fix-gpu`. A probe that
  finds the AMD, software rendering, no NVENC or no CUDA is a setup error to fix: never a CPU or
  software path.
- The site export is current (distribution dots, a Mapbox take's `country`). From the root of
  the checkout the studio runs in:
  `curl -sfR --create-dirs -o public/data/sites/index.json https://ancientnerds.com/data/sites/index.json`
  (`doctor` reports its age).
- Captures drive headed Chrome: keep the display awake and unlocked for the whole capture step.

## Steps

1. `studio episode init <slug> --topic A|B|C|D [--format full|slice] [--paper <request id>
   [--paper-slug <slug>]] [--music auto|none|<file>] [--music-credit '<credit>']`.
   `--paper` reads the published slug from the paper workspace; `--paper-slug` is needed only
   when this machine did not record the publish. `--music auto` takes the single file in
   `video-assets/music/`; every music bed needs `--music-credit`. Then fill `title_candidates`
   (the first becomes the YouTube title; 1-100 characters, no `<` `>`) and `tags` in
   `episode.json`.
2. **REQUIRED SUB-SKILL: studio-casefile.** Build `casefile.json` and `media/`, verify the
   evidence (workflow `studio-casefile-verify`) and crop-check the markers (`markers-export` →
   workflow `studio-marker-check` → `markers-import`).
3. Write `script.json`: its shape is the docstring of `pipeline/studio/script.py`, its rules are
   below.
4. `studio episode check <slug>`: fix every error. `deferred` lists checks that wait for the
   voice or the captures; they run then.
5. `studio episode review <slug>` writes `review.html`. Do not wait for it.
6. `studio episode voice <slug>`: the Shorts narrator (MiniMax), word timings on the NVIDIA. It
   refuses below 10 % of the MiniMax 5-hour window. Exit 1 lists what the real timings broke
   (hook length, chapter length); fix the script and run it again (unchanged beats are not
   narrated again).
7. `studio episode capture <slug> [--only <id>,<id>]`, then `studio episode check <slug>` again:
   nothing may stay deferred.
8. `studio episode timeline <slug>` compiles `timeline.json`.
9. `studio episode render <slug>`: recompiles the timeline, runs the layout lint (refuses on any
   violation), renders on `h264_nvenc`, sets -14 LUFS, renders the three thumbnail candidates,
   audits, and records the ledger row `studio_episodes` in production over ssh.
10. `studio episode package <slug>` writes `package/`: the MP4, the SRT, `description.txt`,
    `titles.txt`, `thumbnail_{1,2,3}.jpg` with their 3840 masters, `youtube.json`,
    `evidence_timestamps.json`.
11. **Stop: hand the package to the owner** (path, the three thumbnails, the titles). If the
    owner wants another thumbnail frame: `studio episode thumbnail <slug> --candidate <K>
    --frame <N>` (a frame that cannot show the answer), then `studio episode package <slug>`.
12. After the owner uploaded by hand and names the video id, the uploaded title and the
    thumbnail candidate set on YouTube (or the A/B winner):
    `studio episode register-youtube <slug> --youtube-id <id> --title '<uploaded title>'
    --published-at <ISO 8601 with timezone> --poster <K>`. `--poster` is always required. With a
    paper, it proves the registration (dry run, upload of `thumbnail_<K>.jpg` as the paper
    page's poster, dry run), writes the ledger, then applies. If the apply fails after the
    ledger write, run exactly the `studio paper register-video …` command the error prints.

## Script rules (`episode check` enforces them; the renderer's lint re-checks)

- **Full-episode spine** (slices exempt): hook beats first, a ClaimBoard, a Meter, an
  EvidenceCard or SourceViewer, the roles `twist`, `verdict`, `change_mind` in that order, and a
  closing ShareCard. Chapters start at the first beat; a full episode has at least 3, each at
  least 10 s.
- **ShareCard is the end card**: only the last beat, the one place the link appears in the picture.
- **Hook**: at most 32 s; burned-in captions exist only there. A hook word, upper-cased with its
  punctuation, has at most 24 characters (`HOOK_LINE_MAX_CHARS`).
- **Glyph rule** (#32): only drawn strings are checked (the registry's `drawn` props, capture
  credits and place and pin labels, hook captions, chapter titles, credit lines, thumbnail
  teasers), and each character also in upper case: `µ` is refused (write `micrometre`), so are
  `Ḫ Ḥ Ṣ Ṭ Ṛ Ṃ Ṇ Ḍ ʾ ʿ`, U+2010-2012 and `‰` (write `Hattusa`). An original quote inside a
  captured source page and the page's own title are never drawn; a QuoteCard's quote is.
- `display` differs from `spoken` only in the spelling of numbers and units. Every factual beat
  lists evidence ids that are `verified` in the case file.
- Claims on a board are `pending` in the case file; each is introduced, followed by an evidence
  beat and then a `status` cue.
- **Platform moments**: 3-5 in a full episode, 5-15 s each, only where the platform answers a
  question (never an advert).
- Map content carries its in-frame credit (MapboxTopdown, MapboxFlyover, PlatformClip).
- **Infographics are linear only** (#31): BarChart has no `scale`, UnitGrid up to 1:400, beyond
  that ScaleZoom. A bar or ScaleZoom end with a case-file quantity id shows exactly its value
  and unit.
- Case-file data enters props only as `{"$ref": id}`, captures only as `{"$capture": id}`.
- No title card and no agent or character block exists.
- **Thumbnails** (#24, #25): exactly 3 `{beat, at, text}`, `at` in [0, 1) of the beat. `text` is
  a 2-4 word teaser (a question or riddle) without a verdict word (SUPPORTED, REFUTED, WEAKENED,
  CONFIRMED, DEBUNKED, PROVEN, TRUE, FALSE). Never the answer: not in a twist, verdict or
  change_mind beat, not after the first status other than `pending` or the first meter move.

## Captures (`captures` in script.json)

Each spec shows only verified case-file data: places at the case file's coordinates under its
names, verified quotes, verified paper anchors. The recorders refuse unknown keys. Clips are
HEVC on NVENC; every manifest's first event is `gpu`, the renderer the take drew on.

| Spec | Block | Keys |
|---|---|---|
| `kind: "platform"` | PlatformClip | `target` (`local`\|`production`), `hud` (0.5-2), `actions`: `pause_rotation`, `search {q}`, `click_result {title}`, `fly_wait {s}`, `zoom {to}`, `open_details {title}`, `measure {a, b}`, `toggle_layer {label}`, `proximity {at}`, `filter {mode, label}`, `wait {s}`. `measure`/`proximity` points are case-file places. **Never `toggle_layer` `Satellite`** (refused; satellite shows in the details page or a Mapbox take) |
| `kind: "globe"`, `scene: "flyto"` / `"places"` | GlobeShot | flyto: `lat`, `lng`, `distance`, `empire`, `rotate_s`, `zoom_s`, `duration_s`, `place {id, label}`; places: `lead_s`, `interval_s`, `duration_s`, `places` (1-12 labelled), optional sweep `sweep_lng_deg`, `cam_lat`, `cam_lng_from`, `distance` |
| `kind: "globe"`, `scene: "distribution"` | GlobeShot | `duration_s`, `places` (0-12 labelled case-file places), `site_ids`: curated `ancient_nerds` sites only (#15, Q11), 1-500 points in all. No other take has a `site_ids` key |
| `kind: "globe"`, `scene: "mapbox_flyin"` / `"mapbox_orbit"` | MapboxFlyover | centred on a case-file place (`name`, `lat`, `lng`, `duration_s`; flyin `orbit_zoom`; orbit `zoom`, `pitch`, `bearing_from`, `bearing_to`). Optional `country` = the site export's country of that place's site (the place carries `site_id`). A fly-in takes up to ~20 min |
| `kind: "source"` | SourceViewer | `{url, quote}` = the verified quote of a case-file item, or `{paper: <paper slug>, anchor: ev-NN}` = the `paper_anchor` of a verified item. A paywalled or login page cannot be captured: use a QuoteCard |
| `kind: "mapbox_topdown"` | MapboxTopdown | `center {lat, lng}`, `zoom`, `bearing`, `style` (`satellite-v9`\|`satellite-streets-v12`), `width`, `height`, `pins` (case-file places) |

## Recovery

| Symptom | Do |
|---|---|
| `episode check` errors | fix `script.json` or the case file; never edit `timeline.json` |
| the timeline refuses a stale voice | `episode voice` again |
| lint violations (`render/lint_report.txt`) | fix the script props (no new voice or captures), render again |
| render audit failed (`render/audit.json`, `package/FAILED.json`) | fix the cause (a clip frozen over 4 s: cut to a card), render again |
| a capture hangs or fails with the display asleep | wake and unlock it, `episode capture <slug> --only <id>` |
| voice refuses on the MiniMax quota | wait for the 5-hour window; never another plan or model |

## Stop conditions

- **Stop at the final package** and hand it to the owner: the only release gate. Claude never
  uploads.
- **Stop and report** when `doctor` stays red, when evidence the episode needs cannot be
  verified, or when a step could pass only by bending a rule (a thumbnail that shows the answer,
  a Satellite toggle, a log scale, a coordinate the case file lacks).
- **Do not stop** for a script approval, `review.html` or a choice between candidates.

## Never

- Upload to YouTube or wire an upload: the upload is manual.
- Render, capture or transcribe on the AMD or the CPU.
- Edit derived files: `timeline.json`, `voice/`, `captures/*.json`, `render/`, `package/`.
- Mark evidence verified or a marker checked by hand (skill studio-casefile).
