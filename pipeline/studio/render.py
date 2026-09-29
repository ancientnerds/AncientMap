"""`episode render`: public dir -> lint -> Remotion render -> -14 LUFS -> stills -> audit -> ledger.

The renderer (video/, stream D) is driven through three node scripts, run with
`node --import tsx scripts/<name>.ts` in <repo>/video (that is, video/scripts/<name>.ts;
the tsx of video/node_modules, never an unpinned npx download):

    lint.ts   --timeline <abs timeline.json> --public-dir <abs dir>            exit != 0 on any
                                                                               layout violation
    render.ts --timeline <abs timeline.json> --public-dir <abs dir> --out <abs mp4>
    still.ts  --timeline <abs timeline.json> --public-dir <abs dir> --out-dir <abs dir>
              --candidate K [--frame N]
              writes thumbnail_<K>_3840.png (3840x2160) and thumbnail_<K>_1280.jpg (1280x720,
              < 2 MB): candidate K of timeline.json's `thumbnails` (its frame and teaser), at
              frame N instead when given (`episode thumbnail`)

lint.ts prints one JSON line {"type":"layout-violation","frame":N,"a":id,"b":id|null,
"reason":str} per violation to stderr; this module keeps stdout+stderr in
render/lint_report.txt and does not parse them. Every script prints `gpu: <WebGL renderer>`
for each browser it opens (spec 4.11): each must name the NVIDIA (capture.gpu.require_nvidia),
render.ts must report exactly one, and that string goes into the ledger row as `renderer`.

The per-render public dir (render/public/) holds hardlinks (copies across drives) of every
file the timeline references by `src` (voice/, captures/, media/, music/) plus every site
font from ancient-nerds-map/public/fonts as fonts/<file>.woff2. No absolute path ever
reaches a prop. The node scripts bundle into render/bundle/ and remove it again (transient);
a node script that times out is killed with its whole process tree (taskkill /T /F), and a
failed or killed step removes render/bundle/ and render.ts's render/raw.mp4.parts/.
Before timeline.json is rewritten, the previous render's outputs are removed, so a failed
render leaves nothing to package; ledger.json binds the audited render to its timeline
(`timeline_sha256`), which `episode package` and `episode thumbnail` check, and to its word
timings (`words_sha256`, the SRT's source), which `episode package` checks with the row's
script and case file hashes. The three
thumbnail candidates (owner decisions 24, 25) are rendered by one still.ts call each;
`episode thumbnail` re-renders one of them from another frame (render_thumbnail), under the
rule the compiled candidates obey (timeline.thumbnail_problem: never the answer).
Loudness: measured twice (shorts_render.measure_lufs), on the raw mix and on a lossless WAV of
it lifted by that gain through the true-peak limiter the shorts use; the limiter's residual is
added to the gain, and the audio is encoded once, at render.ts's AAC bitrate; no loudnorm.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.studio import config
from pipeline.studio.config import REPO
from pipeline.studio.episode import EpisodeWorkspace, load_all, load_json, require_valid
from pipeline.studio.errors import StudioError
from pipeline.studio.ledger_client import record_remote
from pipeline.studio.render_audit import audit
from pipeline.studio.timeline import build_timeline, thumbnail_problem

VIDEO_DIR = REPO / "video"
FONTS_DIR = REPO / "ancient-nerds-map" / "public" / "fonts"
LINT_TIMEOUT_S = 3600
RENDER_TIMEOUT_S = 6 * 3600
STILL_TIMEOUT_S = 900
#: The thumbnail candidates for YouTube's A/B test (owner decision 24), numbered as the
#: script's `thumbnails` and timeline.json's.
CANDIDATES = (1, 2, 3)
AUDIO_BITRATE = "320k"  # render.ts's AAC bitrate (video/scripts/render.ts AUDIO_BITRATE)
GPU_PREFIX = "gpu: "
#: What a failed or killed node script leaves in render/: the bundle (a copy of every asset,
#: because Remotion's bundle() copies the public dir on Windows) and render.ts's chunk parts.
TRANSIENT_DIRS = ("bundle", "raw.mp4.parts")

Runner = Callable[[str, list[str], int], subprocess.CompletedProcess[str]]


def thumbnail_files(candidate: int) -> tuple[str, str]:
    """What still.ts --candidate K writes into render/: the 3840x2160 master, the 1280 JPEG."""
    return (f"thumbnail_{candidate}_3840.png", f"thumbnail_{candidate}_1280.jpg")


THUMBNAILS = tuple(name for k in CANDIDATES for name in thumbnail_files(k))


def collect_srcs(value: Any) -> list[str]:
    """Every string under a "src" key, anywhere in the timeline."""
    if isinstance(value, dict):
        found = [value["src"]] if isinstance(value.get("src"), str) else []
        return found + [s for k, v in value.items() if k != "src" for s in collect_srcs(v)]
    if isinstance(value, list):
        return [s for v in value for s in collect_srcs(v)]
    return []


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if os.stat(src).st_dev == os.stat(dst.parent).st_dev:
        os.link(src, dst)
    else:
        shutil.copy2(src, dst)


def populate_public_dir(
    ws: EpisodeWorkspace, timeline: dict[str, Any], *, music_dir: Path, fonts_dir: Path
) -> list[str]:
    if ws.public_dir.exists():
        shutil.rmtree(ws.public_dir)
    ws.public_dir.mkdir(parents=True)
    placed: list[str] = []
    missing: list[str] = []
    for rel in dict.fromkeys(collect_srcs(timeline)):
        parts = Path(rel).parts
        if Path(rel).is_absolute() or ".." in parts:
            raise StudioError(f"timeline src {rel!r} is not a relative public-dir path")
        source = music_dir / Path(rel).name if parts[0] == "music" else ws.root / rel
        if not source.is_file():
            missing.append(rel)
            continue
        link_or_copy(source, ws.public_dir / rel)
        placed.append(rel)
    if missing:
        raise StudioError(f"files the timeline references are missing: {missing}")
    fonts = sorted(fonts_dir.glob("*.woff2"))
    if not fonts:
        raise StudioError(f"no site fonts in {fonts_dir}")
    for font in fonts:
        link_or_copy(font, ws.public_dir / "fonts" / font.name)
        placed.append(f"fonts/{font.name}")
    return placed


def run_node(script: str, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run video/scripts/<script>; on a timeout kill node with its whole process tree.

    Killing node alone would leave its Chrome headless shells and the Remotion compositor
    running on the NVIDIA, because none of node's `finally` blocks (bundle removal,
    browser.close) runs when it is killed.
    """
    node = shutil.which("node")
    if node is None:
        raise StudioError("node not found on PATH: the renderer needs Node 22")
    proc = subprocess.Popen(
        [node, "--import", "tsx", f"scripts/{script}", *args],
        cwd=VIDEO_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=True, capture_output=True
        )
        proc.communicate()
        raise StudioError(
            f"{script} did not finish within {timeout}s; its process tree was killed"
        ) from exc
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def _remove_transients(render_dir: Path) -> None:
    for name in TRANSIENT_DIRS:
        path = render_dir / name
        if path.exists():
            shutil.rmtree(path)


def normalize_loudness(raw: Path, out: Path) -> float:
    """Lift the mix to TARGET_LUFS with a single AAC encode; returns the gain applied.

    One gain into the limiter overshoots on uncompressed narration: the limiter's gain
    reduction lowers the integrated loudness. So the first gain is applied losslessly
    (render/loudness.wav), that result is measured, the residual is added, and only then is
    the audio encoded, once.
    """
    from pipeline.video.media import run_ffmpeg
    from pipeline.video.shorts_render import PEAK_LIMIT, TARGET_LUFS, gain_db, measure_lufs

    first = gain_db(measure_lufs(raw))
    probe = out.parent / "loudness.wav"
    run_ffmpeg(
        [
            "-i",
            str(raw),
            "-map",
            "0:a:0",
            "-af",
            f"volume={first:.2f}dB,alimiter=limit={PEAK_LIMIT}:level=false",
            "-c:a",
            "pcm_f32le",
            "-ar",
            "48000",
        ],
        probe,
    )
    gain = first + (TARGET_LUFS - measure_lufs(probe))
    probe.unlink()
    run_ffmpeg(
        [
            "-i",
            str(raw),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "copy",
            "-af",
            f"volume={gain:.2f}dB,alimiter=limit={PEAK_LIMIT}:level=false",
            "-c:a",
            "aac",
            "-b:a",
            AUDIO_BITRATE,
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
        ],
        out,
    )
    return gain


def _node_step(
    runner: Runner, script: str, args: list[str], timeout: int, report: Path
) -> list[str]:
    """Run one node script, keep its output in `report`; the renderer strings it printed,
    each checked to name the NVIDIA. A failed or killed script's transient dirs are removed."""
    from pipeline.studio.capture.gpu import require_nvidia

    try:
        proc = runner(script, args, timeout)
    except StudioError:
        _remove_transients(report.parent)
        raise
    report.write_text(
        f"$ {script} {' '.join(args)}\n{proc.stdout}\n{proc.stderr}", encoding="utf-8"
    )
    if proc.returncode != 0:
        _remove_transients(report.parent)
        raise StudioError(f"{script} exited {proc.returncode}; see {report}")
    return [
        require_nvidia(line[len(GPU_PREFIX) :].strip(), script)
        for line in proc.stdout.splitlines()
        if line.startswith(GPU_PREFIX)
    ]


def ledger_row(
    ws: EpisodeWorkspace,
    loaded_episode: dict[str, Any],
    script: dict[str, Any],
    timeline: dict[str, Any],
    video: Path,
    renderer: str,
) -> dict[str, Any]:
    from pipeline.video.shorts_ledger import current_commit, sha256_file

    paper = loaded_episode["paper"]
    return {
        "slug": ws.slug,
        "paper_request_id": paper["request_id"] if paper is not None else None,
        "topic_type": loaded_episode["topic_type"],
        "casefile_sha256": sha256_file(ws.casefile),
        "script_sha256": sha256_file(ws.script),
        "voice_id": script["voice"]["id"],
        "pipeline_commit": current_commit(),
        "video_sha256": sha256_file(video),
        "duration_s": round(timeline["durationInFrames"] / timeline["fps"], 3),
        "rendered_at": datetime.now(UTC).isoformat(),
        "renderer": renderer,
    }


def _common_args(ws: EpisodeWorkspace) -> list[str]:
    return ["--timeline", str(ws.timeline.resolve()), "--public-dir", str(ws.public_dir.resolve())]


def render_still(
    ws: EpisodeWorkspace, runner: Runner, candidate: int, frame: int | None = None
) -> list[str]:
    """still.ts for one thumbnail candidate (at `frame` when given): its two files in render/."""
    args = [*_common_args(ws), "--out-dir", str(ws.render_dir.resolve())]
    args += ["--candidate", str(candidate)]
    if frame is not None:
        args += ["--frame", str(frame)]
    report = ws.render_dir / f"still_{candidate}_log.txt"
    _node_step(runner, "still.ts", args, STILL_TIMEOUT_S, report)
    names = list(thumbnail_files(candidate))
    missing = [n for n in names if not (ws.render_dir / n).exists()]
    if missing:
        raise StudioError(f"still.ts did not write {missing}; see {report}")
    return names


def render_thumbnail(
    ws: EpisodeWorkspace, candidate: int, frame: int, *, runner: Runner = run_node
) -> dict[str, Any]:
    """`episode thumbnail`: re-render one candidate of the audited render from `frame`.

    Only still.ts runs. The frame obeys the rule of the compiled candidates (never inside a
    twist, verdict or change_mind beat, never at or after the first verdict cue); run
    `episode package` again afterwards. `episode package` hardlinks the candidate's render
    files into package/ and still.ts rewrites a file in place (Remotion's renderStill writes
    with fs.promises.writeFile: truncate, same inode), so the two files are removed first:
    the built package keeps the bytes the owner reviewed (and, for a candidate already set on
    YouTube, the poster `register-youtube --poster K` uploads) until `episode package` relinks.
    """
    from pipeline.video.shorts_ledger import sha256_file

    if candidate not in CANDIDATES:
        raise StudioError(f"--candidate must be one of {list(CANDIDATES)}")
    ledger = load_json(ws.render_dir / "ledger.json", "run `episode render` first")
    if not ws.timeline.exists() or sha256_file(ws.timeline) != ledger["timeline_sha256"]:
        raise StudioError("timeline.json changed since the render; run `episode render` again")
    timeline = load_json(ws.timeline, "")
    script = load_json(ws.script, "write script.json")
    roles = {b["id"]: b["role"] for b in script["beats"] if "role" in b}
    problem = thumbnail_problem(timeline, roles, frame)
    if problem is not None:
        raise StudioError(f"--frame {frame}: {problem}")
    music_dir = config.video_assets() / "music"
    populate_public_dir(ws, timeline, music_dir=music_dir, fonts_dir=FONTS_DIR)
    for name in thumbnail_files(candidate):
        (ws.render_dir / name).unlink(missing_ok=True)
    files = render_still(ws, runner, candidate, frame)
    return {"candidate": candidate, "frame": frame, "files": files, "next": "episode package"}


def render_episode(
    ws: EpisodeWorkspace,
    *,
    runner: Runner = run_node,
    loudness: Callable[[Path, Path], float] = normalize_loudness,
    auditor: Callable[[Path, dict[str, Any], Path], tuple[bool, list[Any]]] = audit,
    record: Callable[[dict[str, Any]], dict[str, Any]] = record_remote,
) -> dict[str, Any]:
    from pipeline.video.shorts_ledger import sha256_file

    loaded = load_all(ws)
    require_valid(loaded, final=True)
    # timeline.json is rewritten next: no output of an earlier render may outlive it, so a
    # render that fails from here on leaves nothing `episode package` could ship.
    for name in ("raw.mp4", f"{ws.slug}.mp4", *THUMBNAILS, "audit.json", "ledger.json"):
        (ws.render_dir / name).unlink(missing_ok=True)
    timeline = build_timeline(ws)
    music_dir = config.video_assets() / "music"
    populate_public_dir(ws, timeline, music_dir=music_dir, fonts_dir=FONTS_DIR)
    ws.render_dir.mkdir(parents=True, exist_ok=True)
    common = _common_args(ws)
    _node_step(runner, "lint.ts", common, LINT_TIMEOUT_S, ws.render_dir / "lint_report.txt")
    raw = ws.render_dir / "raw.mp4"
    renderers = set(
        _node_step(
            runner,
            "render.ts",
            [*common, "--out", str(raw.resolve())],
            RENDER_TIMEOUT_S,
            ws.render_dir / "render_log.txt",
        )
    )
    if len(renderers) != 1:
        raise StudioError(
            f"render.ts reported no single renderer: {sorted(renderers)}; see render_log.txt"
        )
    final = ws.render_dir / f"{ws.slug}.mp4"
    gain = loudness(raw, final)
    for candidate in CANDIDATES:
        render_still(ws, runner, candidate)
    ok, checks = auditor(final, timeline, ws.render_dir / "audit.json")
    if not ok:
        failed = [c.name for c in checks if not c.ok]
        raise StudioError(f"render audit failed {failed}; see render/audit.json")
    row = ledger_row(ws, loaded.episode, loaded.script, timeline, final, renderers.pop())
    outcome = record(row)
    ledger = {
        "row": row,
        "outcome": outcome,
        "timeline_sha256": sha256_file(ws.timeline),
        "words_sha256": sha256_file(ws.words),
    }
    (ws.render_dir / "ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return {"video": str(final), "gain_db": round(gain, 2), "video_sha256": row["video_sha256"]}
