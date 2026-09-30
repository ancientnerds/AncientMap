"""The capture side of the studio's GPU rule (spec 2026-09-26 section 4.11).

The workstation is a hybrid laptop: the NVIDIA GeForce RTX 3080 Laptop GPU (the only
CUDA device, index 0) and an integrated AMD Radeon. Every Chrome the captures drive
runs with CHROMIUM_GPU_ARGS; without them Chrome draws on the AMD (measured
2026-09-26: Playwright headed and headless, Puppeteer headed all reported
"ANGLE (AMD, AMD Radeon(TM) Graphics ...)"). Each capture then reads the WebGL
renderer of the page it drives (RENDERER_JS) and require_nvidia() aborts unless it
names the NVIDIA. The renderer string is recorded in the manifest as the event
{"t": 0, "name": "gpu", "label": <renderer>} (gpu_event), because the manifest
contract (plan C C7) has no other free field.

Remotion's own browser (video/scripts) proves its renderer the same way; Remotion
takes no Chromium flags, so `python -m pipeline.studio doctor --fix-gpu` (plan C) can pin
its headless shell to the high-performance GPU through the per-app preference of Windows
(HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences, "GpuPreference=2;"), with
remotion_browser(), gpu_preference() and set_gpu_preference() below (the value keeps
Windows' other flags). nvenc_problem() tells the doctor and the tests whether NVENC encodes
run here, from a one-frame encode per encoder on GPU 0; chrome_renderer() is the doctor's
probe of Chrome with the captures' GPU flags.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pipeline.studio.capture.manifest import CaptureError, event
from pipeline.video.media import FFMPEG_BIN

CHROMIUM_GPU_ARGS = [
    "--use-angle=d3d11",
    "--force_high_performance_gpu",
    "--force-high-performance-gpu",
    "--enable-gpu-rasterization",
    "--ignore-gpu-blocklist",
]
RENDERER_JS = """() => {
  const canvas = document.createElement('canvas')
  const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
  if (!gl) return ''
  const info = gl.getExtension('WEBGL_debug_renderer_info')
  return info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : ''
}"""
NOT_NVIDIA = re.compile(r"AMD|Radeon|SwiftShader|Basic Render|llvmpipe|Intel", re.IGNORECASE)
GPU_PREFERENCES_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
# A value there is a list of name=value; flags: Windows keeps others beside GpuPreference
# (read on the workstation, 2026-09-30: "AppStatus=4;", "GpuPreference=1; ").
GPU_PREFERENCE = "GpuPreference"
HIGH_PERFORMANCE = f"{GPU_PREFERENCE}=2;"
NVENC_ENCODERS = ("h264_nvenc", "hevc_nvenc")
# One black 256x144 frame (NVENC's smallest HEVC frame is larger than 64x36).
NVENC_PROBE_INPUT = [
    FFMPEG_BIN,
    "-hide_banner",
    "-v",
    "error",
    "-f",
    "lavfi",
    "-i",
    "color=c=black:s=256x144:r=1",
    "-frames:v",
    "1",
]
NVENC_PROBE_TIMEOUT_S = 30
HEADLESS_SHELL = Path(
    "node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/"
    "chrome-headless-shell.exe"
)


def require_nvidia(renderer: str, where: str) -> str:
    """The renderer string when it names the NVIDIA; anything else aborts the capture."""
    if "NVIDIA" not in renderer or NOT_NVIDIA.search(renderer):
        raise CaptureError(
            f"{where}: Chrome draws on {renderer or 'no WebGL renderer'!r}, not the NVIDIA GPU "
            "(spec 4.11); run `python -m pipeline.studio doctor`"
        )
    return renderer


def gpu_event(renderer: str) -> dict[str, Any]:
    """The manifest event that records which GPU drew the capture."""
    return event(0, "gpu", label=renderer)


def nvenc_problem() -> str | None:
    """Why NVENC encodes cannot run on GPU 0 of this machine, or None when they can.

    Proven by a one-frame encode with each encoder on `-gpu 0`, as the captures and the
    render encode: Windows ffmpeg builds list the NVENC encoders on machines that cannot run
    them. A failed or hanging encode is the problem it reports."""
    if shutil.which("nvidia-smi") is None:
        return "nvidia-smi not found: no NVIDIA driver, so no NVENC"
    if shutil.which(FFMPEG_BIN) is None:
        return f"{FFMPEG_BIN} not found on PATH"
    for encoder in NVENC_ENCODERS:
        try:
            proc = subprocess.run(
                [*NVENC_PROBE_INPUT, "-c:v", encoder, "-gpu", "0", "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=NVENC_PROBE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return (
                f"{encoder}: {FFMPEG_BIN} did not finish a one-frame encode within "
                f"{NVENC_PROBE_TIMEOUT_S} s"
            )
        if proc.returncode != 0:
            # at -v error the first line is the cause ("No capable devices found"); the
            # lines after it are ffmpeg giving up
            first = (proc.stderr or "").strip().splitlines()[:1] or ["no message"]
            return f"{encoder} cannot encode on GPU 0 (exit {proc.returncode}): {first[0]}"
    return None


def remotion_browser(video_dir: Path) -> Path:
    """The Chrome headless shell Remotion renders with (downloaded into video/node_modules)."""
    exe = video_dir / HEADLESS_SHELL
    if not exe.is_file():
        raise CaptureError(
            f"{exe} does not exist: run `npx remotion browser ensure` in {video_dir}"
        )
    return exe


def _flags(value: str) -> dict[str, str]:
    """The name=value; flags of a UserGpuPreferences value, in their order."""
    flags: dict[str, str] = {}
    for item in value.split(";"):
        if not item.strip():
            continue
        name, sep, flag = item.partition("=")
        if not sep or not name.strip():
            raise CaptureError(
                f"the Windows GPU preference {value!r} is not a list of name=value; flags"
            )
        flags[name.strip()] = flag.strip()
    return flags


def _stored_preference(exe: Path) -> str | None:
    """The whole UserGpuPreferences value of `exe`, or None when Windows keeps none."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, GPU_PREFERENCES_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, str(exe))
    except FileNotFoundError:
        return None
    return str(value)


def gpu_preference(exe: Path) -> str | None:
    """The Windows per-app GPU preference of `exe` as "GpuPreference=<n>;" (HIGH_PERFORMANCE
    pins the NVIDIA), read among the other flags Windows keeps in the value, or None."""
    stored = _stored_preference(exe)
    flags = _flags(stored) if stored is not None else {}
    return f"{GPU_PREFERENCE}={flags[GPU_PREFERENCE]};" if GPU_PREFERENCE in flags else None


def set_gpu_preference(exe: Path) -> None:
    """Pin `exe` to the high-performance GPU (the NVIDIA) for the current Windows user,
    keeping the other flags Windows stores for it."""
    import winreg

    stored = _stored_preference(exe)
    flags = _flags(stored) if stored is not None else {}
    flags[GPU_PREFERENCE] = "2"
    value = "".join(f"{name}={flag};" for name, flag in flags.items())
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, GPU_PREFERENCES_KEY) as key:
        winreg.SetValueEx(key, str(exe), 0, winreg.REG_SZ, value)


def chrome_renderer() -> str:
    """The WebGL renderer of a headless Chrome with the GPU flags every capture passes
    (CHROMIUM_GPU_ARGS; the platform take's Chrome runs headed with them).

    The doctor's probe (plan C Task 26): ok when require_nvidia() accepts the string. It
    tells the doctor the flags reach the NVIDIA here; every capture still proves the
    renderer of the Chrome it drives (the "gpu" event).
    """
    from playwright.sync_api import sync_playwright  # local-only dependency

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=CHROMIUM_GPU_ARGS)
        page = browser.new_page()
        page.goto("about:blank")
        renderer = str(page.evaluate(RENDERER_JS))
        browser.close()
    return renderer
