"""Video production for Ancient Nerds content.

Two independent products live here:

* Weekly journal video (`orchestrator`, `script_adapter`, `voiceover`,
  `asset_collector`, `timeline_builder`, `distributor`): article → narrated
  1920×1080 YouTube video via ElevenLabs + Remotion. See docs/video-pipeline.md.
* Site shorts (`shorts_*`, `python -m pipeline.video short`): one vertical
  teaser per site from the card text, Commons originals and globe clips,
  narrated with the paper TTS path (MiniMax) and assembled with ffmpeg. Spec:
  docs/superpowers/specs/2026-09-16-site-shorts-prototype-design.md.

Every artefact lands under `video-assets/` at the repo root (shorts) or
`pipeline/video/output/` (weekly video); both are gitignored and never served,
so `public/data/` and the indexed pages stay untouched.
"""
