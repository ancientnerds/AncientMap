"""The capture side of the GPU rule (pipeline/studio/capture/gpu.py, spec 4.11)."""

import shutil
import subprocess
import sys
import types

import pytest

from pipeline.studio.capture import gpu
from pipeline.studio.capture.manifest import CaptureError

NVIDIA = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)"
AMD = "ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001681) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def test_only_the_nvidia_passes():
    assert gpu.require_nvidia(NVIDIA, "take") == NVIDIA
    for other in (
        AMD,
        "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
        "ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "",
    ):
        with pytest.raises(CaptureError, match="not the NVIDIA GPU"):
            gpu.require_nvidia(other, "take")


def test_the_renderer_is_recorded_as_a_gpu_event():
    assert gpu.gpu_event(NVIDIA) == {"t": 0.0, "name": "gpu", "label": NVIDIA}


def test_chrome_gets_the_flags_that_put_it_on_the_nvidia():
    assert gpu.CHROMIUM_GPU_ARGS[0] == "--use-angle=d3d11"
    assert "--force_high_performance_gpu" in gpu.CHROMIUM_GPU_ARGS
    assert "UNMASKED_RENDERER_WEBGL" in gpu.RENDERER_JS


def test_nvenc_is_proven_by_an_encode_on_gpu_0(monkeypatch):
    """Review of Task 24: a listing of the encoders proves nothing (Windows builds list the
    NVENC encoders on machines that cannot run them) and never touched `-gpu 0`, and a
    failing or hanging ffmpeg crashed the doctor with a raw subprocess error."""
    monkeypatch.setattr(gpu.shutil, "which", lambda name: None)
    assert gpu.nvenc_problem() == "nvidia-smi not found: no NVIDIA driver, so no NVENC"
    monkeypatch.setattr(gpu.shutil, "which", lambda name: f"/bin/{name}")
    runs: list[list[str]] = []
    failing: dict[str, str] = {}

    def run(cmd, **kwargs):
        runs.append(cmd)
        encoder = cmd[cmd.index("-c:v") + 1]
        if encoder in failing:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=failing[encoder])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(gpu.subprocess, "run", run)
    assert gpu.nvenc_problem() is None
    assert [cmd[cmd.index("-c:v") + 1] for cmd in runs] == ["h264_nvenc", "hevc_nvenc"]
    assert all(cmd[cmd.index("-gpu") + 1] == "0" for cmd in runs)
    # ffmpeg's answer for a GPU index NVENC cannot use (`-gpu 1` here, 2026-09-30)
    failing["hevc_nvenc"] = (
        "[hevc_nvenc @ 0000025f7a0358c0] No capable devices found\n"
        "[vost#0:0/hevc_nvenc @ 0000025f7a032e80] Error while opening encoder - maybe "
        "incorrect parameters such as bit_rate, rate, width or height.\n"
        "[out#0/null @ 0000025f7a021d40] Nothing was written into output file, because at "
        "least one of its streams received no packets.\n"
    )
    assert gpu.nvenc_problem() == (
        "hevc_nvenc cannot encode on GPU 0 (exit 1): "
        "[hevc_nvenc @ 0000025f7a0358c0] No capable devices found"
    )

    def hang(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(gpu.subprocess, "run", hang)
    assert gpu.nvenc_problem() == (
        f"h264_nvenc: {gpu.FFMPEG_BIN} did not finish a one-frame encode within 30 s"
    )


def test_remotion_browser_is_the_headless_shell_in_node_modules(tmp_path):
    with pytest.raises(CaptureError, match="npx remotion browser ensure"):
        gpu.remotion_browser(tmp_path)
    exe = tmp_path / gpu.HEADLESS_SHELL
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"exe")
    assert gpu.remotion_browser(tmp_path) == exe


class _FakeKey:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


REG_SZ = 1


def _fake_winreg(store, key_exists):
    """winreg with one key: HKEY_CURRENT_USER\\<GPU_PREFERENCES_KEY> (any other is an error).
    `store` maps a value name to (data, type)."""

    def key_at(root, path):
        assert (root, path) == ("HKCU", gpu.GPU_PREFERENCES_KEY)
        return _FakeKey(store)

    def open_key(root, path):
        if not key_exists:
            raise FileNotFoundError(path)
        return key_at(root, path)

    def query(key, name):
        if name not in key.store:
            raise FileNotFoundError(name)
        return key.store[name]

    def set_value(key, name, reserved, kind, value):
        key.store[name] = (value, kind)

    return types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        REG_SZ=REG_SZ,
        OpenKey=open_key,
        CreateKey=key_at,
        QueryValueEx=query,
        SetValueEx=set_value,
    )


def test_gpu_preference_reads_and_pins_the_high_performance_gpu(monkeypatch, tmp_path):
    exe = tmp_path / "chrome-headless-shell.exe"
    store: dict[str, tuple[str, int]] = {}
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store, key_exists=False))
    assert gpu.gpu_preference(exe) is None
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store, key_exists=True))
    assert gpu.gpu_preference(exe) is None
    gpu.set_gpu_preference(exe)
    assert store == {str(exe): ("GpuPreference=2;", REG_SZ)}
    assert gpu.gpu_preference(exe) == gpu.HIGH_PERFORMANCE == "GpuPreference=2;"


@pytest.mark.parametrize(
    ("stored", "preference", "pinned"),
    [
        # Windows keeps other flags in the same value (read on the workstation, 2026-09-30:
        # "AppStatus=4;", "GpuPreference=1; " with a trailing space)
        ("AppStatus=4;GpuPreference=2;", "GpuPreference=2;", "AppStatus=4;GpuPreference=2;"),
        ("SwapEffectUpgradeEnable=1;GpuPreference=1; ", "GpuPreference=1;", None),
        ("AppStatus=4;", None, "AppStatus=4;GpuPreference=2;"),
    ],
)
def test_the_gpu_preference_is_read_among_the_other_flags_windows_keeps(
    monkeypatch, tmp_path, stored, preference, pinned
):
    """Review of Task 24: the doctor compares the preference with HIGH_PERFORMANCE exactly,
    so a value that also carries another flag read as not pinned; pinning kept no flag."""
    exe = tmp_path / "chrome-headless-shell.exe"
    store = {str(exe): (stored, REG_SZ)}
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store, key_exists=True))
    assert gpu.gpu_preference(exe) == preference
    gpu.set_gpu_preference(exe)
    assert gpu.gpu_preference(exe) == gpu.HIGH_PERFORMANCE
    if pinned is not None:
        assert store[str(exe)] == (pinned, REG_SZ)
    assert store[str(exe)][0].count("GpuPreference=") == 1


def test_a_gpu_preference_windows_did_not_write_is_named(monkeypatch, tmp_path):
    exe = tmp_path / "chrome-headless-shell.exe"
    store = {str(exe): ("GpuPreference2", REG_SZ)}
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store, key_exists=True))
    with pytest.raises(CaptureError, match=r"'GpuPreference2' is not a list of name=value;"):
        gpu.gpu_preference(exe)


@pytest.mark.skipif(shutil.which("nvidia-smi") is None, reason="no NVIDIA driver on this machine")
def test_the_doctor_probe_finds_chrome_on_the_nvidia():
    pytest.importorskip("playwright")
    assert gpu.require_nvidia(gpu.chrome_renderer(), "doctor").startswith("ANGLE (NVIDIA")
