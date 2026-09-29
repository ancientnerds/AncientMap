# Weekly Video Pipeline

> **See also:** the site-shorts pipeline (`python -m pipeline.video short`, vertical teasers per site,
> MiniMax narration + ffmpeg, no Remotion/ElevenLabs) is a separate product in the same package —
> spec in `docs/superpowers/specs/2026-09-16-site-shorts-prototype-design.md`. This weekly pipeline
> has no `ELEVENLABS_API_KEY` configured and has not been run in production (status 2026-09-16).
> Every rendered short is recorded in the `site_shorts` ledger (migration 0021,
> `pipeline/video/shorts_ledger.py`): card text + sha256, images on screen, voice, commit and the
> video's sha256, keyed by site id. The render step writes it and fails without it; the renders
> made before the ledger are entered by `scripts/backfill_site_shorts_ledger.py --apply`. A row
> starts as `withdrawn` when the site is retired at write time (its `scope_status`, read in the
> insert's transaction), otherwise as `rendered` - never by a period guess. A site retired later
> keeps its `rendered` row, so publishing must check the site's scope then. Neither the batch
> nor `short --site`/`--name` exports a retired site (E4, migration 0020).

> **Status (2026-09-29): no runner, no renderer.** The weekly pipeline's orchestrator became the
> site-Shorts production pipeline on 2026-09-17 (`465415e`: `python -m pipeline.video pipeline`), and
> its Remotion project in `video/` (the `WeeklyVideo` composition) was replaced by the studio renderer
> (plan D Task 1 of the studio build, `docs/superpowers/plans/2026-09-26-D-renderer-capture-video-mode.md`).
> The Python modules of phases 1-4 and 6 (`script_adapter.py`, `voiceover.py`, `asset_collector.py`,
> `timeline_builder.py`, `distributor.py`) stay in `pipeline/video/`, but nothing in the repository runs
> them, and no renderer reads the timeline `timeline_builder.py` writes. Long-form YouTube episodes are
> made by the studio: `docs/procedures/STUDIO.md`.

Automated "This Week in Archaeology" — transforms weekly articles into ~10-15 minute narrated YouTube videos.

## Architecture

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    WEEKLY VIDEO PIPELINE — Data Flow                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

  ┌─────────────────────────────────────────┐
  │  EXISTING LYRA PIPELINE                 │
  │  (runs weekly, already built)           │
  │                                         │
  │  YouTube videos → transcripts →         │
  │  summaries → NewsItems → NewsArticle    │
  └──────────────────┬──────────────────────┘
                     │
                     │ article_id
                     ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  PHASE 1: SCRIPT ADAPTER                     pipeline/video/script_adapter.py
 │                                                                          │
 │  Inputs:                          Outputs:                               │
 │  ├─ NewsArticle.content (md)      └─ video_script.json                   │
 │  ├─ Citation NewsItems (DB)          ├─ segments[ ]                      │
 │  ├─ UnifiedSite coords/meta            │  ├─ type: intro|story|transition│
 │  └─ WikiImage gallery URLs             │  ├─ narration: "spoken text..." │
 │                                        │  ├─ visuals.clip: {video_id,   │
 │  LLM: MiniMax-M2.5                    │  │    start, duration}          │
 │  (reuses llm_call() from config.py)   │  ├─ visuals.site_lat/lon       │
 │                                        │  └─ visuals.wiki_images[ ]     │
 │  Article prose ──LLM──▶ spoken         ├─ credits[ ]                    │
 │  narration with [N] citations          └─ sources[ ]                    │
 └─────────────────────────┬─────────────────────────────────────────────────┘
                           │
                           │ video_script.json
                           ▼
          ┌────────────────┴────────────────┐
          │                                 │
          ▼                                 ▼
 ┌─────────────────────────┐  ┌──────────────────────────────────┐
 │  PHASE 2: VOICEOVER     │  │  PHASE 3: ASSET COLLECTOR        │
 │  voiceover.py           │  │  asset_collector.py              │
 │                         │  │                                  │
 │  ElevenLabs API         │  │  Three asset types:              │
 │  /text-to-speech/       │  │                                  │
 │    {voice}/with-        │  │  ┌─ yt-dlp + FFmpeg ──────────┐  │
 │    timestamps           │  │  │  YouTube clips (≤15s each)  │  │
 │                         │  │  │  clips/{vid}_{start}.mp4    │  │
 │  Per segment:           │  │  └─────────────────────────────┘  │
 │  ├─ audio/segment_NN.mp3│  │                                  │
 │  └─ word_timings.json   │  │  ┌─ HTTP download ────────────┐  │
 │     [{word, start, end}]│  │  │  Screenshots from API       │  │
 │                         │  │  │  images/screen_NN.jpg       │  │
 │  ~8K chars/video        │  │  └─────────────────────────────┘  │
 │  $22/mo ElevenLabs      │  │                                  │
 │                         │  │  ┌─ Wikimedia Commons ────────┐  │
 │                         │  │  │  WikiImages for B-roll      │  │
 │                         │  │  │  site_gallery/*.jpg         │  │
 │                         │  │  └─────────────────────────────┘  │
 └────────────┬────────────┘  └──────────────┬───────────────────┘
              │                              │
              │ audio/* + word_timings.json   │ asset manifest
              └──────────────┬───────────────┘
                             │
                             ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  PHASE 4: TIMELINE BUILDER                pipeline/video/timeline_builder.py
 │                                                                          │
 │  Merges audio timing + assets into Remotion inputProps                   │
 │                                                                          │
 │  Per story segment, allocates frame budget:                              │
 │  ┌──────────┬──────────────────┬───────────────┬──────────────┐          │
 │  │Screenshot│  YouTube Clip    │  Wiki Images  │ Globe Fly-To │          │
 │  │  ~30%    │  ~40% (15s max)  │   ~30%        │   3s         │          │
 │  │Ken Burns │  + lower-third   │  Ken Burns    │   SLERP      │          │
 │  └──────────┴──────────────────┴───────────────┴──────────────┘          │
 │                                                                          │
 │  Output: timeline.json (1920×1080 @ 30fps)                              │
 │  ├─ segments[].startFrame, durationFrames                               │
 │  ├─ segments[].visuals[].src, startFrame, endFrame                      │
 │  ├─ segments[].wordTimings[] (for subtitles)                            │
 │  └─ segments[].lowerThird (site name, period, country)                  │
 └─────────────────────────┬─────────────────────────────────────────────────┘
                           │
                           │ timeline.json + audio/* + clips/* + images/*
                           ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  PHASE 5: RENDERER — REMOVED                                             │
 │                                                                          │
 │  The WeeklyVideo composition that read this timeline.json is deleted.    │
 │  video/ now holds the studio renderer, which reads the studio's own      │
 │  timeline.json (pipeline/studio/timeline.py), not this one. See the      │
 │  section "Renderer" below.                                               │
 └─────────────────────────┬─────────────────────────────────────────────────┘
                           │
                           │ (no final.mp4: nothing renders this timeline)
                           ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  PHASE 6: YOUTUBE DISTRIBUTOR              pipeline/video/distributor.py  │
 │                                                                          │
 │  YouTube Data API v3 (resumable upload)                                  │
 │  ├─ Title: "Archaeology News: {headline} | {date_range}"                │
 │  ├─ Description: auto-generated chapters + source links + credits        │
 │  ├─ Tags: archaeology, site names, countries                            │
 │  ├─ Category: Education (27)                                            │
 │  ├─ Privacy: PRIVATE → review → PUBLIC                                  │
 │  └─ Custom thumbnail                                                    │
 └───────────────────────────────────────────────────────────────────────────┘
```

## Orchestrator

There is none. `pipeline/video/orchestrator.py` is the site-Shorts production pipeline since
2026-09-17 (`465415e`; `python -m pipeline.video pipeline --limit N | --names-file FILE`), and the
weekly command `python -m pipeline.video.orchestrator --article-id=<id>` with its `--dry-run`,
`--skip-render` and `--skip-upload` flags no longer exists.

## Renderer

The weekly Remotion project (`WeeklyVideo`, `IntroSequence`, `StorySegment`, `GlobeFlyTo`,
`TransitionWipe`, `OutroSequence` and their helpers under `video/src/`) was never rendered and is
deleted. `video/` now holds the studio renderer: Remotion 4.0.529 with every `@remotion/*` package
pinned to that exact version, the compositions `Episode` and `Thumbnail`, and the scripts `lint.ts`,
`render.ts` and `still.ts`, driven by `python -m pipeline.studio episode render`. It reads the studio's
`timeline.json` (`pipeline/studio/timeline.py`: 60 fps, scenes of registered NERV blocks), a different
format from the weekly one below. Setup, the GPU rule and the render steps are in
`docs/procedures/STUDIO.md`; the design is spec section 4.8 of
`docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md`.

## File Structure

```
pipeline/video/            # only the weekly modules; the other files there are the site Shorts
├── __init__.py
├── script_adapter.py      # Article markdown → narration script JSON
├── voiceover.py           # ElevenLabs TTS + word timing
├── asset_collector.py     # yt-dlp clips + screenshots + WikiImages
├── timeline_builder.py    # Merge timing + assets → the weekly timeline.json (no renderer reads it)
├── distributor.py         # YouTube Data API upload (not wired)
└── prompts/
    └── narration_adapt.txt  # LLM prompt: article prose → spoken narration
```

## The Bridge: timeline.json

Python (Phases 1-4) generates `timeline.json`. It was the input of the deleted `WeeklyVideo`
composition; no renderer reads this format any more. `pipeline/video/timeline_builder.py` still writes
it.

```json
{
  "fps": 30,
  "width": 1920, "height": 1080,
  "totalDurationFrames": 27000,
  "segments": [
    {
      "type": "intro",
      "startFrame": 0,
      "durationFrames": 240,
      "audio": "audio/segment_00.mp3",
      "wordTimings": [{"word": "This", "start": 0.0, "end": 0.15}, ...],
      "titleText": "This Week in Archaeology",
      "dateRange": "February 10-16, 2026"
    },
    {
      "type": "story",
      "startFrame": 330,
      "durationFrames": 1350,
      "audio": "audio/segment_01.mp3",
      "wordTimings": [...],
      "visuals": [
        {"type": "screenshot", "src": "images/screen_01.jpg", "startFrame": 0, "endFrame": 255},
        {"type": "clip", "src": "clips/abc123_245.mp4", "startFrame": 255, "endFrame": 705,
         "attribution": {"channel": "World of Antiquity", "title": "Gobekli Tepe 2026 Update"}},
        {"type": "wiki_image", "src": "images/gobekli_aerial.jpg", "startFrame": 705, "endFrame": 1050},
        {"type": "globe_flyto", "startFrame": 1050, "endFrame": 1350,
         "targetLat": 37.223, "targetLon": 38.922, "siteName": "Gobekli Tepe"}
      ],
      "lowerThird": {"siteName": "Gobekli Tepe", "period": "Pre-Pottery Neolithic", "country": "Turkey"}
    }
  ]
}
```

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `LYRA_ANTHROPIC_API_KEY` | Yes | MiniMax-M2.5 for script adaptation |
| `ELEVENLABS_API_KEY` | Yes | TTS voiceover generation |
| `ELEVENLABS_VOICE_ID` | Yes | Selected narrator voice |
| `ELEVENLABS_MODEL_ID` | No | Default: `eleven_multilingual_v2` |
| `YOUTUBE_TOKEN_PATH` | For upload | OAuth token for YouTube Data API |

## Cost Estimate

| Item | Monthly |
|------|---------|
| ElevenLabs Creator plan | $22 |
| MiniMax-M2.5 for script adaptation | ~$1 |
| Remotion Lambda (4 renders) | ~$0.40 |
| YouTube Data API | Free |
| yt-dlp + FFmpeg | Free |
| **Total** | **~$24/month** |

## Legal Compliance (Per Video)

- Each clip is under 15 seconds
- Each clip has simultaneous AI narration (not just playing source audio)
- Source audio lowered/muted under narration
- On-screen lower-third attribution for every clip (channel name + video title)
- Video description includes all source links with timestamps
- Overall video is 60%+ original content by runtime
- If a creator objects, remove their content and blacklist channel

## Verification

The weekly checklist ran the removed orchestrator and rendered `WeeklyVideo`; neither exists. What
still applies to the weekly modules is the static check:
`./.venv/Scripts/python.exe -m ruff check pipeline/video/`. The checks of `video/` (`npx tsc --noEmit`,
`npx vitest run`, the smoke render) belong to the studio renderer: `docs/procedures/STUDIO.md`.
