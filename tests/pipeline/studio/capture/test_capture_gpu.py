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


def test_nvenc_needs_the_driver_and_both_encoders(monkeypatch):
    monkeypatch.setattr(gpu.shutil, "which", lambda name: None)
    assert gpu.nvenc_problem() == "nvidia-smi not found: no NVIDIA driver, so no NVENC"
    monkeypatch.setattr(gpu.shutil, "which", lambda name: f"/bin/{name}")
    listing = " V....D h264_nvenc  NVIDIA NVENC H.264 encoder (codec h264)\n"
    monkeypatch.setattr(
        gpu.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=listing, stderr=""),
    )
    assert gpu.nvenc_problem() == f"{gpu.FFMPEG_BIN} lacks ['hevc_nvenc']"
    listing += " V....D hevc_nvenc  NVIDIA NVENC hevc encoder (codec hevc)\n"
    assert gpu.nvenc_problem() is None


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


def _fake_winreg(store, key_exists):
    def open_key(root, path):
        if not key_exists:
            raise FileNotFoundError(path)
        return _FakeKey(store)

    def query(key, name):
        if name not in key.store:
            raise FileNotFoundError(name)
        return key.store[name], 1

    def set_value(key, name, reserved, kind, value):
        key.store[name] = value

    return types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        REG_SZ=1,
        OpenKey=open_key,
        CreateKey=lambda root, path: _FakeKey(store),
        QueryValueEx=query,
        SetValueEx=set_value,
    )


def test_gpu_preference_reads_and_pins_the_high_performance_gpu(monkeypatch, tmp_path):
    exe = tmp_path / "chrome-headless-shell.exe"
    store: dict[str, str] = {}
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store, key_exists=False))
    assert gpu.gpu_preference(exe) is None
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store, key_exists=True))
    assert gpu.gpu_preference(exe) is None
    gpu.set_gpu_preference(exe)
    assert store == {str(exe): "GpuPreference=2;"}
    assert gpu.gpu_preference(exe) == "GpuPreference=2;"


@pytest.mark.skipif(shutil.which("nvidia-smi") is None, reason="no NVIDIA driver on this machine")
def test_the_doctor_probe_finds_chrome_on_the_nvidia():
    pytest.importorskip("playwright")
    assert gpu.require_nvidia(gpu.chrome_renderer(), "doctor").startswith("ANGLE (NVIDIA")
