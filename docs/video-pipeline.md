# Weekly Video Pipeline

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
 │  PHASE 5: REMOTION RENDERER                           video/ (TypeScript)│
 │                                                                          │
 │  ┌─────────────┐  ┌───────────────────────────────────────────────────┐  │
 │  │ WeeklyVideo  │  │  Composition Sequence:                           │  │
 │  │ (main comp)  │  │                                                  │  │
 │  │              │  │  ┌─────────────┐                                 │  │
 │  │  Reads       │  │  │IntroSequence│ Title card + date range         │  │
 │  │  timeline    │  │  └──────┬──────┘                                 │  │
 │  │  .json as    │  │         ▼                                        │  │
 │  │  inputProps  │  │  ┌─────────────┐ ┌──────────────────────────┐    │  │
 │  │              │  │  │ GlobeFlyTo  │→│     StorySegment         │    │  │
 │  │              │  │  │ (SLERP      │ │  screenshot → clip →     │    │  │
 │  │              │  │  │  @remotion/ │ │  wiki images + narration │    │  │
 │  │              │  │  │  three)     │ │  + LowerThird overlays   │    │  │
 │  │              │  │  └─────────────┘ └──────────────────────────┘    │  │
 │  │              │  │         │              ↕ (repeats per story)     │  │
 │  │              │  │         ▼                                        │  │
 │  │              │  │  ┌──────────────┐                                │  │
 │  │              │  │  │TransitionWipe│ "Meanwhile, in Turkey..."      │  │
 │  │              │  │  └──────┬───────┘                                │  │
 │  │              │  │         ▼                                        │  │
 │  │              │  │  ┌──────────────┐                                │  │
 │  │              │  │  │OutroSequence │ Credits scroll + website CTA   │  │
 │  │              │  │  └──────────────┘                                │  │
 │  └─────────────┘  └───────────────────────────────────────────────────┘  │
 │                                                                          │
 │  Output: final.mp4 (1080p, h264, ~10-15 min)                           │
 └─────────────────────────┬─────────────────────────────────────────────────┘
                           │
                           │ final.mp4 + thumbnail.png
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

```
python -m pipeline.video.orchestrator --article-id=42
```

| Flag | Runs | Purpose |
|------|------|---------|
| `--dry-run` | Phase 1 only | Print script JSON, verify structure |
| `--skip-render` | Phases 1-4 | Generate assets, no video render |
| `--skip-upload` | Phases 1-5 | Render video, no YouTube upload |
| _(none)_ | Phases 1-6 | Full pipeline, upload to YouTube |

File: `pipeline/video/orchestrator.py`

## File Structure

```
pipeline/video/
├── __init__.py
├── script_adapter.py      # Article markdown → narration script JSON
├── voiceover.py           # ElevenLabs TTS + word timing
├── asset_collector.py     # yt-dlp clips + screenshots + WikiImages
├── timeline_builder.py    # Merge timing + assets → Remotion inputProps
├── distributor.py         # YouTube Data API upload
├── orchestrator.py        # End-to-end pipeline runner
└── prompts/
    └── narration_adapt.txt  # LLM prompt: article prose → spoken narration

video/                     # Remotion project (TypeScript)
├── package.json
├── remotion.config.ts
├── tsconfig.json
└── src/
    ├── index.ts            # Remotion entry point
    ├── Root.tsx            # Composition registry
    ├── WeeklyVideo.tsx     # Main composition (sequences all segments)
    ├── types.ts            # Timeline JSON schema types
    ├── compositions/
    │   ├── IntroSequence.tsx
    │   ├── StorySegment.tsx
    │   ├── GlobeFlyTo.tsx       # Ported from useFlyToAnimation.ts
    │   ├── ClipWithAttribution.tsx
    │   ├── TransitionWipe.tsx
    │   └── OutroSequence.tsx
    ├── components/
    │   ├── LowerThird.tsx       # Channel/site attribution overlay
    │   ├── Globe3D.tsx          # Three.js globe for @remotion/three
    │   └── KenBurns.tsx         # Pan/zoom effect on still images
    └── utils/
        └── timing.ts            # Frame/time conversion helpers
```

## The Bridge: timeline.json

Python (Phases 1-4) generates `timeline.json`. Remotion (Phase 5) consumes it. This is the contract between the two stacks.

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

## Verification Checklist

1. `python -m pipeline.video.orchestrator --article-id=X --dry-run` — verify script JSON
2. Check ElevenLabs audio quality + word timing accuracy for first video
3. `npx remotion studio` in `video/` — preview compositions with test data
4. `npx remotion render WeeklyVideo --props=timeline.json` — render locally
5. Verify globe fly-to animation renders at 30fps
6. Check lower-third attribution over clips
7. Upload test video as PRIVATE, verify chapters/description
8. Full pipeline: `python -m pipeline.video.orchestrator --article-id=X`
9. `npx tsc --noEmit` in `video/`
10. `python -m ruff check pipeline/video/`
