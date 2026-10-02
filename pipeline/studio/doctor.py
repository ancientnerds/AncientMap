"""`python -m pipeline.studio doctor [--fix-gpu]`: is this machine ready to run every studio step?

Each probe reports ok/failed with the reason; the command exits 1 when any probe fails.
Nothing is repaired or skipped here, with one exception the owner asked for (spec 4.11):
`--fix-gpu` pins Remotion's Chrome headless shell to the high-performance GPU (the Windows
per-app preference, pipeline.studio.capture.gpu.set_gpu_preference) before probing.

The GPU probes (spec 4.11: every GPU workload on the NVIDIA RTX 3080, never the integrated
AMD): nvidia-smi names the RTX 3080; the system ffmpeg encodes a test frame with h264_nvenc
and hevc_nvenc on GPU 0; CUDA loads for faster-whisper; the renderer of a headless Chrome
and of Playwright's headless Chromium shell (the platform take), each launched as the captures
launch it, names the NVIDIA; Remotion's headless shell exists and
carries the high-performance per-app preference. That preference does not prove the renderer Remotion's own browser gets (it draws
on the NVIDIA only with `gl: 'angle'`, SwiftShader by default, stream D's Task 19), so the
Remotion browser's renderer string is proven where it renders: every lint.ts, render.ts and
still.ts prints its `gpu:` lines and render.py refuses any that does not name the NVIDIA
(lint.ts runs first in every `episode render`, within seconds), and stream D's Task 22 proves
it first on the workstation. A green doctor therefore says the machine is set up; the first
lint says Remotion's browser uses the NVIDIA.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

from pipeline.studio import config, remote, sites
from pipeline.studio.blocks import load_registry
from pipeline.studio.errors import StudioError
from pipeline.studio.render import FONTS_DIR, VIDEO_DIR

GPU_NAME = "RTX 3080"


@dataclass(frozen=True)
class Probe:
    name: str
    ok: bool
    detail: str


def _tool(name: str, env: str) -> Probe:
    configured = os.environ.get(env, name)
    found = shutil.which(configured)
    return Probe(name, found is not None, found or f"{configured} not on PATH (set {env})")


def _module(name: str) -> Probe:
    ok = importlib.util.find_spec(name) is not None
    return Probe(f"python: {name}", ok, "importable" if ok else "not installed in this venv")


def _registry() -> Probe:
    try:
        blocks = load_registry()
    except StudioError as exc:
        return Probe("block registry", False, str(exc))
    return Probe("block registry", True, f"{len(blocks)} blocks")


def _ssh() -> Probe:
    try:
        proc = subprocess.run(
            ["ssh", *remote.SSH_OPTIONS, remote.SSH_HOST, "true"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return Probe("ssh ancientnerds", False, "no answer within 30 s")
    return Probe(
        "ssh ancientnerds", proc.returncode == 0, proc.stderr.strip()[-200:] or "reachable"
    )


def _node_modules() -> Probe:
    path = VIDEO_DIR / "node_modules"
    if not path.is_dir():
        return Probe("video/node_modules", False, "missing: run `npm ci` in video/")
    return Probe("video/node_modules", True, str(path))


def _site_export() -> Probe:
    """The repo-root site export the distribution dots resolve from (owner decision 15) and
    its age: I13 downloads the current one read-only from production (Q4) with
    `sites.DOWNLOAD`, whose `-R` sets the file's mtime to the export's Last-Modified."""
    path = sites.SITES_INDEX
    if not path.exists():
        return Probe(
            "site export", False, f"missing: download it from the repo root with {sites.DOWNLOAD}"
        )
    stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%d %H:%M UTC")
    return Probe("site export", True, f"{path} from {stamp}")


def _music() -> Probe:
    from pipeline.video.__main__ import single_audio

    music_dir = config.video_assets() / "music"
    track = single_audio(music_dir) if music_dir.is_dir() else None
    return Probe(
        "music bed", track is not None, str(track) if track else f"no single track in {music_dir}"
    )


def _nvidia_smi() -> Probe:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return Probe("nvidia-smi", False, "not on PATH: no NVIDIA driver")
    try:
        proc = subprocess.run(
            [exe, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return Probe("nvidia-smi", False, "no answer within 30 s")
    names = proc.stdout.strip()
    return Probe("nvidia-smi", GPU_NAME in names, names or "no GPU listed")


def _nvenc() -> Probe:
    """Both NVENC encoders really encode on GPU 0 (spec 4.11: `-gpu 0`, as the captures'
    capture/encode.py): gpu.nvenc_problem encodes one black frame with each."""
    from pipeline.studio.capture import gpu

    problem = gpu.nvenc_problem()
    if problem is not None:
        return Probe("NVENC", False, problem)
    return Probe("NVENC", True, " and ".join(gpu.NVENC_ENCODERS) + " encoded a test frame on GPU 0")


def _cuda() -> Probe:
    if importlib.util.find_spec("ctranslate2") is None:
        return Probe("CUDA for faster-whisper", False, "ctranslate2 is not installed")
    import ctranslate2

    count = ctranslate2.get_cuda_device_count()
    return Probe("CUDA for faster-whisper", count >= 1, f"{count} CUDA device(s)")


def _chrome_renderer(headless_shell: bool = False) -> Probe:
    """A headless Chrome as the captures launch it must draw on the NVIDIA; with `headless_shell`, the
    headless Chromium shell the platform take drives."""
    name = "headless shell renderer" if headless_shell else "chrome renderer"
    if importlib.util.find_spec("playwright") is None:
        return Probe(name, False, "Playwright is not installed in this venv")
    from playwright.sync_api import Error as PlaywrightError

    from pipeline.studio.capture import gpu

    try:
        renderer = gpu.require_nvidia(gpu.chrome_renderer(headless_shell), "doctor")
    except (StudioError, PlaywrightError) as exc:
        return Probe(name, False, str(exc))
    return Probe(name, True, renderer)


def _shell_renderer() -> Probe:
    return _chrome_renderer(headless_shell=True)


def gpu_probes() -> list[Probe]:
    from pipeline.studio.capture import gpu

    found = [_nvidia_smi(), _nvenc(), _cuda()]
    try:
        exe = gpu.remotion_browser(VIDEO_DIR)
    except StudioError as exc:
        found.append(Probe("remotion browser", False, str(exc)))
    else:
        preference = gpu.gpu_preference(exe)
        found.append(Probe("remotion browser", True, str(exe)))
        found.append(
            Probe(
                "remotion GPU preference",
                preference == gpu.HIGH_PERFORMANCE,
                preference or "not set: run `python -m pipeline.studio doctor --fix-gpu`",
            )
        )
    found.append(_chrome_renderer())
    found.append(_shell_renderer())
    return found


def probes() -> list[Probe]:
    assets = config.studio_assets()
    fonts = sorted(FONTS_DIR.glob("*.woff2"))
    return [
        Probe("studio assets", assets.parent.exists(), str(assets)),
        _tool("ffmpeg", "FFMPEG_BIN"),
        _tool("ffprobe", "FFPROBE_BIN"),
        Probe(
            "node",
            shutil.which("node") is not None,
            shutil.which("node") or "Node 22 is not on PATH",
        ),
        _node_modules(),
        _registry(),
        Probe("site fonts", bool(fonts), f"{len(fonts)} woff2 in {FONTS_DIR}"),
        _module("faster_whisper"),
        _module("mutagen"),
        _module("PIL"),
        _module("playwright"),
        _module("pipeline.studio.capture"),
        *gpu_probes(),
        Probe(
            "LYRA_MINIMAX_API_KEY",
            bool(os.environ.get("LYRA_MINIMAX_API_KEY")),
            "set" if os.environ.get("LYRA_MINIMAX_API_KEY") else "missing (main checkout .env)",
        ),
        _music(),
        _site_export(),
        _ssh(),
    ]


def cmd_doctor(args: argparse.Namespace) -> int:
    if args.fix_gpu:
        from pipeline.studio.capture import gpu

        exe = gpu.remotion_browser(VIDEO_DIR)
        gpu.set_gpu_preference(exe)
        print(f"fixed  Remotion browser {exe} pinned to the high-performance GPU")
    results = probes()
    for p in results:
        print(f"{'ok  ' if p.ok else 'FAIL'}  {p.name:24s} {p.detail}")
    return 0 if all(p.ok for p in results) else 1


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("doctor", help="check tools, keys, assets, the GPU and ssh")
    p.add_argument(
        "--fix-gpu",
        action="store_true",
        help="pin Remotion's browser to the NVIDIA (Windows per-app GPU preference) first",
    )
    p.set_defaults(func=cmd_doctor)
