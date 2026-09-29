"""Globe and Mapbox takes (pipeline/studio/capture/globe.py); the recorder itself is faked."""

import json
import subprocess
from contextlib import nullcontext
from pathlib import Path

import pytest

from pipeline.studio.capture import globe
from pipeline.studio.capture.gpu import nvenc_problem
from pipeline.studio.capture.manifest import CREDIT_MAPBOX_STREETS, CaptureError

NVIDIA = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)"
NVENC_PROBLEM = nvenc_problem()
needs_nvenc = pytest.mark.skipif(NVENC_PROBLEM is not None, reason=str(NVENC_PROBLEM))

FLYTO = {
    "id": "g1",
    "kind": "globe",
    "scene": "flyto",
    "lat": 34.0067,
    "lng": 36.2033,
    "distance": 1.35,
    "empire": "roman",
    "rotate_s": 1.5,
    "zoom_s": 2.0,
    "duration_s": 5,
    "place": {"id": "p1", "label": "Baalbek"},
}
PLACES = {
    "id": "g2",
    "kind": "globe",
    "scene": "places",
    "places": [
        {"id": "p2", "label": "Giza", "lat": 29.98, "lng": 31.13},
        {"id": "p3", "label": "Athens", "lat": 37.97, "lng": 23.73},
        {"id": "p1", "label": "Baalbek", "lat": 34.0, "lng": 36.2},
    ],
    "lead_s": 0.8,
    "interval_s": 0.6,
    "duration_s": 6,
}
DISTRIBUTION = {
    "id": "g3",
    "kind": "globe",
    "scene": "distribution",
    "duration_s": 12,
    "places": [
        {"id": "p1", "label": "Baalbek", "lat": 34.0, "lng": 36.2},
        {"id": "d1", "lat": -13.16, "lng": -72.55},
    ],
}
FLYIN = {
    "id": "m1",
    "kind": "globe",
    "scene": "mapbox_flyin",
    "name": "Baalbek",
    "lat": 34.0067,
    "lng": 36.2033,
    "country": "Lebanon",
    "orbit_zoom": 15.5,
    "duration_s": 8,
}
ORBIT = {
    "id": "m2",
    "kind": "globe",
    "scene": "mapbox_orbit",
    "name": "Baalbek",
    "lat": 34.0067,
    "lng": 36.2033,
    "zoom": 16.5,
    "pitch": 60,
    "bearing_from": 20,
    "bearing_to": 110,
    "duration_s": 6,
}
WORK = Path("C:/ep/captures/g1.rec")


def tracks(pixels: dict, frames: int) -> dict:
    """points.json of a fixed pose: each place at one pixel (or hidden) in every frame."""
    return {pid: [None if px is None else list(px)] * frames for pid, px in pixels.items()}


def test_every_scene_has_a_recorder_scene_and_credits():
    assert globe.RECORDER_SCENES == {
        "flyto": "studio-globe-flyto",
        "places": "studio-globe-places",
        "distribution": "studio-globe-places",
        "mapbox_flyin": "studio-mapbox-flyin",
        "mapbox_orbit": "studio-mapbox-orbit",
    }
    assert globe.CREDITS["flyto"] == [] and globe.CREDITS["distribution"] == []
    assert globe.CREDITS["mapbox_flyin"] == [CREDIT_MAPBOX_STREETS]


def test_flyto_input_and_events():
    inp = globe.scene_input(FLYTO, WORK)
    assert inp == {
        "scene": "flyto",
        "duration_s": 5.0,
        "frames_dir": "C:/ep/captures/g1.rec/frames",
        "renderer_path": "C:/ep/captures/g1.rec/renderer.json",
        "lat": 34.0067,
        "lng": 36.2033,
        "distance": 1.35,
        "empire": "roman",
        "rotate_s": 1.5,
        "zoom_s": 2.0,
        "places": [{"id": "p1", "lat": 34.0067, "lng": 36.2033}],
        "points_path": "C:/ep/captures/g1.rec/points.json",
    }
    frames = globe.expected_frames(5)
    # the target drifts in from the corner during the fly-to and sits at the centre on arrival
    track = [[1500.0, 900.0]] * 150 + [[960.0, 540.0]] * (frames - 150)
    events = globe.take_events(FLYTO, inp, {"p1": track})
    assert events[:3] == [
        {"t": 0.0, "name": "rotate"},
        {"t": 1.5, "name": "zoom"},
        {"t": 3.5, "name": "arrive", "x": 960.0, "y": 540.0},
    ]
    place = events[3]
    assert {k: v for k, v in place.items() if k != "track"} == {
        "t": 3.5,
        "name": "place",
        "x": 960.0,
        "y": 540.0,
        "target": "p1",
        "label": "Baalbek",
    }
    assert len(place["track"]) == frames - 210
    plain = {k: v for k, v in FLYTO.items() if k != "place"}
    plain_inp = globe.scene_input(plain, WORK)
    assert "points_path" not in plain_inp
    assert [e["name"] for e in globe.take_events(plain, plain_inp, None)] == [
        "rotate",
        "zoom",
        "arrive",
    ]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"distance": 1.05}, "distance=1.05 outside"),
        ({"duration_s": 3.5}, r"rotate_s \+ zoom_s \+ 0.5 s hold"),
        ({"duration_s": 31}, "duration_s=31.0 outside"),
        ({"lat": 95}, "not a coordinate"),
        ({"lat": "34"}, "g1: lat must be a number"),
        ({"empire": ""}, "empire must be"),
        ({"empire": "atlantis"}, "empire must be null or an empire id"),
        ({"emprie": "roman"}, r"unknown keys \['emprie'\] for scene flyto"),
        ({"place": {"id": "p1"}}, "place must be"),
        ({"scene": "street-view"}, "scene must be one of"),
    ],
)
def test_flyto_rejects_bad_specs(changes, message):
    with pytest.raises(CaptureError, match=message):
        globe.scene_input({**FLYTO, **changes}, WORK)


def test_places_pose_and_events_use_the_pixels_the_page_reported():
    inp = globe.scene_input(PLACES, WORK)
    assert (inp["scene"], inp["sweep_lng_deg"]) == ("places", 0.0)
    assert inp["places"] == [
        {"id": "p2", "lat": 29.98, "lng": 31.13},
        {"id": "p3", "lat": 37.97, "lng": 23.73},
        {"id": "p1", "lat": 34.0, "lng": 36.2},
    ]
    assert inp["points_path"] == "C:/ep/captures/g1.rec/points.json"
    assert 1.2 <= inp["distance"] <= 2.44
    frames = globe.expected_frames(6)
    points = tracks({"p2": (900.0, 700.0), "p3": (500.0, 400.0), "p1": (1100.0, 520.0)}, frames)
    events = globe.take_events(PLACES, inp, points)
    assert [(e["target"], e["label"], e["t"], e["x"], e["y"], len(e["track"])) for e in events] == [
        ("p2", "Giza", 0.8, 900.0, 700.0, frames - 48),
        ("p3", "Athens", 1.4, 500.0, 400.0, frames - 84),
        ("p1", "Baalbek", 2.0, 1100.0, 520.0, frames - 120),
    ]


def test_places_hidden_outside_the_band_or_too_late_are_rejected():
    inp = globe.scene_input(PLACES, WORK)
    frames = globe.expected_frames(6)
    with pytest.raises(CaptureError, match="p3 is not visible in the take"):
        globe.take_events(PLACES, inp, tracks({"p2": (900, 700), "p3": None, "p1": (1, 1)}, frames))
    # the first real places take drew Giza at y 946: its label would sit under the controls
    low = tracks({"p2": (1232.2, 946.5), "p3": (823, 426), "p1": (1100, 520)}, frames)
    with pytest.raises(CaptureError, match=r"draws place p2 at \(0\.64, 0\.88\) of the frame"):
        globe.take_events(PLACES, inp, low)
    short = tracks({"p2": (900, 700), "p3": (500, 400), "p1": (1100, 520)}, 10)
    with pytest.raises(
        CaptureError, match="points.json holds 10 points for place p2, the take has 360"
    ):
        globe.take_events(PLACES, inp, short)
    # checked before the take: lead_s + 2 * interval_s = 10.8 s > 6 s
    with pytest.raises(CaptureError, match="p1 would light up after the take ends"):
        globe.scene_input({**PLACES, "interval_s": 5.0}, WORK)
    with pytest.raises(CaptureError, match=r"interval_s=0.05 outside 0.1..5.0"):
        globe.scene_input({**PLACES, "interval_s": 0.05}, WORK)


def test_a_sweep_moves_the_camera_and_each_pin_follows_its_track():
    spec = {
        **PLACES,
        "places": PLACES["places"][:1],
        "lead_s": 0.5,
        "sweep_lng_deg": 120,
        "cam_lat": 30,
        "cam_lng_from": 0,
        "distance": 2.2,
    }
    inp = globe.scene_input(spec, WORK)
    assert (inp["cam_lat"], inp["cam_lng"], inp["distance"], inp["sweep_lng_deg"]) == (
        30.0,
        0.0,
        2.2,
        120.0,
    )
    frames = globe.expected_frames(6)
    # behind the globe until frame 40, left of the label band until frame 60, then moving right
    track = [None] * 40 + [[100.0, 500.0]] * 20 + [[300.0 + f, 500.0] for f in range(frames - 60)]
    (place,) = globe.take_events(spec, inp, {"p2": track})
    assert (place["t"], place["x"], place["track"][0]) == (1.0, 300.0, [300.0, 500.0])
    assert len(place["track"]) == frames - 60 and place["track"][-1] == [599.0, 500.0]
    with pytest.raises(CaptureError, match="belong to a sweep"):
        globe.scene_input({**PLACES, "cam_lat": 30}, WORK)


def test_a_world_distribution_turns_the_whole_globe_once():
    inp = globe.scene_input(DISTRIBUTION, WORK)
    assert (inp["scene"], inp["sweep_lng_deg"], inp["distance"]) == ("places", 360.0, 2.44)
    assert inp["places"] == [
        {"id": "p1", "lat": 34.0, "lng": 36.2},
        {"id": "d1", "lat": -13.16, "lng": -72.55},
    ]
    # the camera starts opposite the places' mean longitude, at the midpoint of their
    # lowest and highest latitude, where one turn shows both
    assert inp["cam_lat"] == pytest.approx(10.42)
    assert inp["cam_lng"] == pytest.approx(161.82, abs=0.01)
    frames = globe.expected_frames(12)
    near = [None] * 100 + [[960.0, 500.0]] * (frames - 100)
    far = [None] * 500 + [[1500.0, 1000.0]] * (frames - 500)
    pin, dot = globe.take_events(DISTRIBUTION, inp, {"d1": far, "p1": near})
    assert (pin["target"], pin["label"], pin["t"]) == ("p1", "Baalbek", round(100 / 60, 3))
    # an unlabelled place is a dot: no label, and the label band does not apply to it
    assert "label" not in dot and (dot["t"], dot["x"], dot["y"]) == (
        round(500 / 60, 3),
        1500.0,
        1000.0,
    )
    with pytest.raises(CaptureError, match="places must list 1-500 places"):
        globe.scene_input({**DISTRIBUTION, "places": []}, WORK)
    with pytest.raises(CaptureError, match="place ids must be unique"):
        globe.scene_input({**DISTRIBUTION, "places": DISTRIBUTION["places"][:1] * 2}, WORK)


def test_a_distribution_dot_is_a_site_id_without_a_label():
    # owner decision 15: plan C resolves a distribution's site_ids from the site export
    # into unlabelled places {id, lat, lng}; each becomes a dot, its site id the target
    site = "be81c1a6-5d0c-4f7e-9a51-3c2d7e8f9a10"
    spec = {
        **DISTRIBUTION,
        "places": [DISTRIBUTION["places"][0], {"id": site, "lat": 37.2231, "lng": 38.9224}],
    }
    inp = globe.scene_input(spec, WORK)
    assert inp["places"][1] == {"id": site, "lat": 37.2231, "lng": 38.9224}
    frames = globe.expected_frames(12)
    seen = [None] * 200 + [[700.0, 400.0]] * (frames - 200)
    pin, dot = globe.take_events(spec, inp, {site: seen, "p1": [[960.0, 500.0]] * frames})
    assert pin["target"] == "p1" and pin["label"] == "Baalbek"
    assert (dot["name"], dot["target"], dot["t"], dot["x"], dot["y"]) == (
        "place",
        site,
        round(200 / 60, 3),
        700.0,
        400.0,
    )
    assert "label" not in dot and len(dot["track"]) == frames - 200


def test_the_distribution_camera_shows_the_outlying_places_too():
    # ten dots near 48 N and one on Rapa Nui: their mean latitude (41.2) would keep the
    # Rapa Nui dot 68.3 degrees away, beyond the horizon (65.8) for the whole turn
    north = [{"id": f"n{i}", "lat": 48.0, "lng": -10.0 + 5 * i} for i in range(10)]
    rapa_nui = {"id": "s1", "lat": -27.1, "lng": -109.35}
    inp = globe.scene_input({**DISTRIBUTION, "places": [*north, rapa_nui]}, WORK)
    assert inp["cam_lat"] == pytest.approx(10.45)
    for place in inp["places"]:
        assert abs(place["lat"] - inp["cam_lat"]) <= globe.DISTRIBUTION_DOT_REACH_DEG
    # a labelled place far south of the dots: the midpoint (2.5) would draw its pin below
    # the label band, so the camera moves south to the nearest latitude that shows it there
    dots = [{**n, "lat": 45.0} for n in north]
    pin = {"id": "p9", "label": "Far south", "lat": -40.0, "lng": -72.55}
    inp = globe.scene_input({**DISTRIBUTION, "places": [*dots, pin]}, WORK)
    assert inp["cam_lat"] == -14.0


def test_a_distribution_one_turn_cannot_show_is_refused_before_the_take(tmp_path):
    spec = {
        **DISTRIBUTION,
        "places": [
            {"id": "n1", "lat": 70.0, "lng": 20.0},
            {"id": "s1", "lat": -66.0, "lng": 140.0},
        ],
    }
    with pytest.raises(
        CaptureError,
        match=r"g3: places \['n1', 's1'\] cannot face the camera in one turn of the globe; "
        "split the distribution",
    ):
        globe.record_globe(tmp_path, spec)
    assert not (tmp_path / "captures").exists()


def test_mapbox_inputs():
    flyin = globe.scene_input(FLYIN, WORK)
    assert (flyin["name"], flyin["country"], flyin["orbit_zoom"]) == ("Baalbek", "Lebanon", 15.5)
    assert [e["name"] for e in globe.take_events(FLYIN, flyin, None)] == ["space", "zoom", "orbit"]
    orbit = globe.scene_input({**ORBIT, "country": None}, WORK)
    assert "country" not in orbit and orbit["bearing_to"] == 110.0
    with pytest.raises(CaptureError, match="at least 4.6 s"):
        globe.scene_input({**FLYIN, "duration_s": 4}, WORK)
    with pytest.raises(CaptureError, match=r"unknown keys \['pitch'\] for scene mapbox_flyin"):
        globe.scene_input({**FLYIN, "pitch": 60}, WORK)


def test_recorder_command_records_landscape_at_60fps():
    cmd = globe.recorder_command(
        "npm", "studio-globe-flyto", Path("C:/ep/in.json"), Path("C:/ep/rec")
    )
    assert cmd == [
        "npm",
        "run",
        "video:record",
        "--",
        "studio-globe-flyto",
        "--fps",
        "60",
        "--input",
        "C:/ep/in.json",
        "--out",
        "C:/ep/rec",
    ]
    assert "--portrait" not in cmd


def test_frames_are_counted_like_the_recorder_scenes():
    assert globe.expected_frames(5) == 300
    assert globe.expected_frames(3.51) == 211
    # JS Math.round rounds 304.5 up; Python's round() would give 304
    assert globe.expected_frames(5.075) == 305


def test_record_globe_validates_before_starting_anything(tmp_path):
    with pytest.raises(CaptureError, match="takes kind 'globe'"):
        globe.record_globe(tmp_path, {**FLYTO, "kind": "globe-flyto"})
    with pytest.raises(CaptureError, match="distance"):
        globe.record_globe(tmp_path, {**FLYTO, "distance": 3})
    assert not (tmp_path / "captures").exists()


class FakeRecorder:
    """Stands in for `npm run video:record`: writes what the scene would (frames, renderer, points)."""

    frames = 300
    returncode = 0
    renderer = NVIDIA

    def __init__(self, cmd, log):
        from PIL import Image

        assert cmd[:5] == ["npm", "run", "video:record", "--", "studio-globe-flyto"]
        inp = json.loads(Path(cmd[cmd.index("--input") + 1]).read_text(encoding="utf-8"))
        Path(inp["renderer_path"]).write_text(
            json.dumps({"renderer": self.renderer}), encoding="utf-8"
        )
        frames = Path(inp["frames_dir"])
        frames.mkdir(parents=True)
        for i in range(self.frames):
            Image.new("RGB", (1920, 1080), (i % 255, 40, 80)).save(frames / f"f{i:06d}.jpg")
        points = {p["id"]: [[960.0, 540.0]] * self.frames for p in inp["places"]}
        Path(inp["points_path"]).write_text(json.dumps(points), encoding="utf-8")

    def wait(self, timeout):
        return self.returncode


@pytest.fixture
def workstation(monkeypatch):
    """The workstation parts of a take the tests replace: npm on PATH and the awake display."""
    monkeypatch.setattr(globe, "require_tool", lambda name: "npm")
    monkeypatch.setattr(globe, "display_awake", nullcontext)


@needs_nvenc
def test_record_globe_encodes_the_exact_frames_and_cleans_up(tmp_path, monkeypatch, workstation):
    monkeypatch.setattr(globe, "start_recorder", FakeRecorder)
    manifest = globe.record_globe(tmp_path, FLYTO)
    assert manifest["path"] == "captures/g1.mp4" and (tmp_path / manifest["path"]).is_file()
    assert (manifest["fps"], manifest["duration_s"], manifest["width"], manifest["height"]) == (
        60,
        5.0,
        1920,
        1080,
    )
    assert manifest["events"][0] == {"t": 0.0, "name": "gpu", "label": NVIDIA}
    place = manifest["events"][-1]
    assert manifest["credits"] == [] and place["label"] == "Baalbek" and len(place["track"]) == 90
    assert not (tmp_path / "captures" / "g1.rec").exists()


def test_a_take_drawn_on_another_gpu_fails(tmp_path, monkeypatch, workstation):
    class OnAmd(FakeRecorder):
        frames = 2
        renderer = (
            "ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001681) Direct3D11 vs_5_0 ps_5_0, D3D11)"
        )

    monkeypatch.setattr(globe, "start_recorder", OnAmd)
    with pytest.raises(CaptureError, match="g1: recorder: Chrome draws on .*AMD.*not the NVIDIA"):
        globe.record_globe(tmp_path, FLYTO)


def test_a_take_with_missing_frames_fails_before_the_encode(tmp_path, monkeypatch, workstation):
    class Short(FakeRecorder):
        frames = 250

    monkeypatch.setattr(globe, "start_recorder", Short)
    with pytest.raises(CaptureError, match="the take has 250 frames, expected 300"):
        globe.record_globe(tmp_path, FLYTO)


def test_an_encoder_failure_names_the_tool_and_its_stderr(tmp_path, monkeypatch, workstation):
    def broken(frames_dir, fps, out):
        raise subprocess.CalledProcessError(
            1,
            ["C:/ffmpeg/bin/ffmpeg.exe", "-i", "f%06d.jpg"],
            stderr="No NVENC capable devices found\n",
        )

    monkeypatch.setattr(globe, "start_recorder", FakeRecorder)
    monkeypatch.setattr(globe, "sequence_to_mp4", broken)
    with pytest.raises(
        CaptureError, match=r"g1: ffmpeg.exe failed \(exit 1\): No NVENC capable devices found"
    ) as err:
        globe.record_globe(tmp_path, FLYTO)
    assert isinstance(err.value.__cause__, subprocess.CalledProcessError)


def test_a_failed_recorder_points_at_its_log(tmp_path, monkeypatch, workstation):
    class Failed(FakeRecorder):
        frames = 1
        returncode = 1

    monkeypatch.setattr(globe, "start_recorder", Failed)
    with pytest.raises(CaptureError, match=r"recorder failed \(exit 1\); see .*recorder.log"):
        globe.record_globe(tmp_path, FLYTO)
